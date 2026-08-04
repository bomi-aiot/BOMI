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

from bomi_ai_chat import policy

# "보미야"로 대화가 시작될 때, 녹음 전에 먼저 말하는 호출 응답.
# 사용자에게 '지금 들을 준비가 됐다'는 신호를 주고, 잘못 깨웠을 때도 바로 알아챌 수 있게
# 한다. 고정 문구이므로 필요하면 미리 합성해 캐싱할 수 있다.
WAKE_ACK_MESSAGE = "네, 말씀하세요."


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
