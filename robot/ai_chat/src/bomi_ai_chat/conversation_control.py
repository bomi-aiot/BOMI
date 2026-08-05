# robot/ai_chat/src/bomi_ai_chat/conversation_control.py
"""대화 세션 제어의 공용 도우미 — 레거시 파이프라인과 그래프 런타임이 함께 쓴다.

왜 별도 모듈인가
    "보미야로 대화를 시작하고, 호출에 응답하고, 언제 끝낼지"를 정하는 규칙은 두 실행
    경로(pipeline.py = 레거시, bootstrap.py = 그래프) 모두에 필요하다. 그런데 pipeline.py
    를 import 하면 무거운 LLM/STT/TTS 클라이언트까지 딸려온다. 그래서 policy 만 의존하는
    가벼운 공용 모듈을 둔다 — 마무리 판정과 호출 응답 문구가 한 곳에서만 정의된다.

무엇이 여기 있고 무엇이 없나
    여기: '언제 시작/끝낼지'의 규칙(마무리 문구 판정, 호출 응답 텍스트).
    여기 없음: 실제 오디오 I/O, LLM 호출, 그래프 실행. 그건 각 경로가 알아서 한다.

참고
    CLAUDE.md §14 (발화 규칙), §16 (LLM 예산)
"""

from __future__ import annotations

from enum import Enum

from bomi_ai_chat import policy

# "보미야"로 대화가 시작될 때, 녹음 전에 먼저 말하는 호출 응답.
# 사용자에게 '지금 들을 준비가 됐다'는 신호를 주고, 잘못 깨웠을 때도 바로 알아챌 수 있게
# 한다. 고정 문구이므로 필요하면 미리 합성해 캐싱할 수 있다.
WAKE_ACK_MESSAGE = "네, 말씀하세요."


class SessionState(str, Enum):
    """웨이크워드로 열리는 '리슨 세션'의 상태.

    왜 이제 와서 이름을 붙이는가
        bootstrap 의 대화 루프는 처음부터 이 다섯 상태를 오갔다 — 다만 이름 없이,
        중첩 while 루프의 '현재 위치'로만 존재했다. 이름이 없으니 세션 수명주기를
        오디오 장치 없이 테스트할 방법도, "지금 세션이 어느 상태였나"를 로그로
        남길 방법도 없었다 (docs/natural-conversation/current-state-audit.md §1.2).
        이 enum 과 아래 next_state() 는 그 암묵 상태를 명시화한 것이지 새 제어
        흐름이 아니다. 권위는 여전히 bootstrap 의 루프에 있다.

    상태의 의미
        IDLE        웨이크워드 대기. 어떤 발화도 처리하지 않는다(시나리오 A).
        LISTENING   세션 안에서 다음 발화를 기다린다. 웨이크워드는 필요 없다.
        PROCESSING  발화를 그래프에 태우는 중.
        RESPONDING  응답 재생 중(현재는 반이중 대기 — CLAUDE.md §13 배포 상태).
        ENDING      종료 사유가 확정됨. 정리 후 IDLE 로 돌아간다.
    """

    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    RESPONDING = "RESPONDING"
    ENDING = "ENDING"


# 세션 상태 전이표. (현재 상태, 이벤트) -> 다음 상태.
#
# 이벤트 이름은 bootstrap 의 루프가 실제로 겪는 사건과 1:1 이다:
#   wake_detected    웨이크워드 감지 (IDLE 에서만 의미가 있다 — 시나리오 A 의 게이트)
#   speech_captured  발화 시작이 감지되어 녹음이 확정됨
#   no_speech        onset 타임아웃(CONVERSATION_IDLE_TIMEOUT_SEC)까지 발화 없음
#   stt_empty        발화는 있었으나 STT 가 못 알아들음 -> 되묻지 않고 재리슨
#   turn_done        그래프 한 턴이 끝나 응답 재생이 시작됨
#   playback_done    응답 재생 완료(반이중 대기 종료)
#   farewell         마무리 문구 감지 (is_farewell) — 응답 재생이 끝난 '뒤'에 판정
#   interrupted      Ctrl+C 등 조작으로 세션만 종료
#   session_closed   종료 정리가 끝나 웨이크워드 대기로 복귀
_TRANSITIONS: dict[tuple[SessionState, str], SessionState] = {
    (SessionState.IDLE, "wake_detected"): SessionState.LISTENING,
    (SessionState.LISTENING, "speech_captured"): SessionState.PROCESSING,
    (SessionState.LISTENING, "no_speech"): SessionState.ENDING,
    (SessionState.LISTENING, "stt_empty"): SessionState.LISTENING,
    (SessionState.LISTENING, "farewell"): SessionState.ENDING,
    (SessionState.LISTENING, "interrupted"): SessionState.ENDING,
    (SessionState.PROCESSING, "turn_done"): SessionState.RESPONDING,
    (SessionState.RESPONDING, "playback_done"): SessionState.LISTENING,
    (SessionState.ENDING, "session_closed"): SessionState.IDLE,
}


def next_state(current: SessionState, event: str) -> SessionState:
    """세션 상태 전이 — 순수 함수. I/O 도, 시계도, 로그도 없다.

    무엇을 하는가
        전이표에 정의된 (상태, 이벤트) 조합이면 다음 상태를 돌려주고, 정의되지
        않은 조합이면 ValueError 를 던진다.

    왜 정의되지 않은 전이에서 요란하게 실패하는가
        "IDLE 인데 발화가 처리됐다"는 웨이크워드 게이트가 뚫렸다는 뜻이다. 조용히
        넘어가면 그 버그는 실기에서야 드러난다. 테스트에서 먼저 죽는 편이 낫다.
        단, 라이브 루프에서는 bootstrap._advance 가 이 예외를 잡아 로그만 남기고
        세션을 유지한다 — 상태 부기 실수로 로봇이 죽으면 안 되기 때문이다.

    누가 호출하는가
        bootstrap.run_conversation_loop / _run_graph_conversation (라이브),
        tests/test_conversation_session.py (세션 수명주기 회귀).
    """
    key = (current, event)
    if key not in _TRANSITIONS:
        raise ValueError(f"undefined session transition: {current.value} + {event}")
    return _TRANSITIONS[key]


def is_farewell(text: str) -> bool:
    """사용자 발화가 '대화를 그만하겠다'는 뜻인지 부분일치로 판단한다.

    무엇을 하는가
        발화에서 공백을 없앤 뒤, policy.CONVERSATION_FAREWELL_CUES 의 큐가 하나라도
        들어 있으면 True. "대화는 여기까지만 하자" -> "여기까지" 포함 -> True.

    왜 LLM 을 안 쓰나
        종료 판정에 생성 LLM 을 또 부르면 턴마다 왕복이 늘어 2초 예산이 무너진다
        (CLAUDE.md §16). 값싼 키워드 매칭으로 시작한다. 완벽하지 않으니 실제 녹취를
        보고 policy 의 큐 목록을 늘려야 한다.
    """
    normalized = text.replace(" ", "")
    return any(cue in normalized for cue in policy.CONVERSATION_FAREWELL_CUES)
