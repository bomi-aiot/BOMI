"""한 번의 대화 턴 동안 흐르는 상태, 그리고 SpeechProposal 의 형태.

어디에 위치하는가
    모든 그래프 노드가 이 dict 를 받고, 병합될 부분 dict 를 반환한다. 노드들이
    무엇에 대해 이야기할 수 있는지 알고 싶다면 이 파일이 전체 목록이다.

왜 하나의 평평한 dict 인가
    LangGraph 는 노드의 반환값을 하나의 state 객체에 병합한다. 덕분에 노드들이
    서로 독립적이다. 게이트는 핸들러를 import 하지 않고, 핸들러는 정제기를 import
    하지 않는다. 오직 이 키 이름들에만 합의한다. 그래서 그래프를 만들지 않고도
    노드 하나를 테스트할 수 있다.

한 dict 안에 두 가지 수명이 있다 — 사람들이 가장 많이 걸려 넘어지는 지점
    어떤 키는 한 턴만 산다        (user_input, response, sentences)
    어떤 키는 턴 사이에 살아남아야 한다 (last_spoke_at, silence_level, occupancy)

    두 번째 그룹이 유지되는 이유는 LangGraph 의 checkpointer 가 thread_id
    (= 어르신 id) 별로 state 를 저장하기 때문이다. 그리고 바로 그 이유 때문에
    checkpointer 는 서버 DB 가 아니라 로컬 SQLite 여야 한다. 매 턴 쓰기가 일어나므로
    턴마다 네트워크 왕복이 붙으면 지연 예산이 무너지고 오프라인에서는 아예 죽는다
    (CLAUDE.md §5).

    장기 사실 — 기억, 복약, 동의 — 은 여기 살지 않는다. 백엔드 DB 에 있고 `ctx` 로
    들어온다. 사실을 state 에 캐시하려는 유혹을 참아야 한다. 복약 스케줄의 진실이
    두 곳에 있는 것은 품질 문제가 아니라 안전 버그다.

참고
    CLAUDE.md §4 (용어), §5 (소유권), §6 (노드), §7 (게이트), §13 (barge-in)
"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages

# ─────────────────────────────────────────────────────────────────────────────
# 용어 경고  (CLAUDE.md §4)
#
# DB 가 "candidate" 라는 단어를 이미 소유하고 있다. `fact_candidate` 는 대화에서
# 추출된 사실 중, 확인·확정을 거쳐야 기록될 수 있는 미확정 사실이다.
#
# '제안된 발화'는 완전히 다른 것이며 여기서는 SpeechProposal 이라고 부른다.
# fact_candidate 행을 가리키는 경우가 아니면 변수명에 candidate 를 쓰지 않는다.
# ─────────────────────────────────────────────────────────────────────────────

# 어느 핸들러가 문장을 쓸 것인가.
Intent = Literal[
    "info",           # 사실 응답. 검색된 문서를 쓸 수 있다
    "companion",      # 안부, 잡담, 회상
    "schedule",       # 복약·일정 등록/조회/완료 처리
    "emotional",      # 듣기. T3 동의 질문을 큐에 넣을 수 있다
    "greeting",       # 현관 배웅/환영
    "onboarding",     # 계약 주도형 질문 세트
    "clarification",  # 계약 주도형 fact_candidate 재질의
]

Priority = Literal["critical", "high", "event", "clarification", "medium", "low", "ambient"]

Occupancy = Literal["HOME", "AWAY", "UNKNOWN"]

# Vision 은 프레임이 아니라 '지속시간을 만족한 전이'만 보낸다. RESTING 은 침묵을 설명한다.
RestState = Literal["RESTING", "AWAKE", "UNKNOWN"]


class SpeechProposal(TypedDict, total=False):
    """말하겠다는 '요청'. 발화 자체가 아니다.

    왜 직접 발화가 아니라 제안인가
        스케줄러, 침묵 사다리, 현관 센서, 재질의 흐름이 모두 로봇에게 무언가를
        말하게 하고 싶어 한다. 각자 직접 말하면 서로 겹쳐 떠들고, 새벽 3시에 떠들고,
        마지막 알림 5분 뒤에 또 떠든다. 그래서 제안만 하고 게이트가 중재한다
        (CLAUDE.md §7).

    필드
        intent:     어느 핸들러가 실제 문장을 쓸지.
        priority:   policy.PRIORITY_POLICY 의 키. 어떤 게이트를 건너뛸 수 있는지 결정.
        seed:       핸들러를 위한 힌트. '최종 문구가 아니다.' 핸들러는 여전히 실행되며
                    기억·날씨·복약 상태를 써서 다시 쓸 수 있다.
        expires_at: 이 시각(clock 기준)이 지나면 쓰레기가 된다. 선택 항목.
                    인사에는 있고(수십 초), 복약 알림에는 보통 없다. 복약은 사라지는
                    대신 나중에 다시 와야 하기 때문이다.
        origin:     로깅용 자유 태그. 예: "silence_ladder:2".
                    "왜 로봇이 새벽 3시에 말했는가"에 답할 수 있게 만든다.
        meta:       핸들러별 부가 정보(fact_candidate id, 질문 코드 등).
    """

    intent: Intent
    priority: Priority
    seed: str
    expires_at: float | None
    origin: str
    meta: dict


class ConvState(TypedDict, total=False):
    # ── 진입: 이 턴이 세 경로 중 어디에서 왔는가 (§6) ──
    #
    # "user_utterance" -> 어르신이 말했다. note_interaction 다음 safety_triage 로.
    #                     게이트를 절대 거치지 않는다. 우리에게 말을 건 사람에게
    #                     대답할 허락을 받을 필요는 없다.
    # "proactive"      -> 스케줄러나 침묵 사다리가 제안했다. 허락을 받아야 한다.
    # "door_event"     -> 현관 센서가 발동했다. occupancy 를 즉시 반영한 '다음에'
    #                     인사를 제안한다.
    trigger_type: Literal["user_utterance", "proactive", "door_event"]

    # 반응형 턴에서는 ASR 텍스트, 능동 턴에서는 이긴 제안의 seed.
    # 이름이 "user_input" 인 이유는 두 경우 모두 프롬프트 빌더가 이 값을 소비하기
    # 때문이다. 핸들러가 trigger_type 으로 분기할 필요가 없어진다.
    user_input: str

    # VAD 가 측정한 어르신 발화 길이(초). 맞장구("응")와 진짜 끼어들기를 구분하는 데
    # 필요하다. 텍스트만으로는 부족하다.
    user_input_duration_sec: float

    messages: Annotated[list, add_messages]

    # ── 게이트 (§7) ──
    proposals: list[SpeechProposal]
    gate_decision: Literal["speak", "silent"]
    # quiet hours 중에 인사가 통과할 때 설정된다. 말하되, 아주 짧게.
    terse: bool
    # 이긴 제안에서 복사해온다. 순수하게 로깅과 사후 튜닝을 위한 값.
    speech_origin: str

    # ── 안전 (§9, §10) ──
    safety_level: Literal["T1", "T2", "T3", "T4", "none"]
    # T1 일 때만 채워진다. outbox 로 넘기며, 프롬프트에는 절대 넣지 않는다.
    escalation: dict | None

    # ── 라우팅 ──
    intent: Intent
    # 로봇이 말하는 중 맞장구가 들어와서, 응답 없이 턴을 끝내야 할 때
    # note_interaction 이 설정한다. route_interaction 만 읽는다.
    is_backchannel: bool

    # ── 백엔드에서 온 컨텍스트 (§5, §8) ──
    #
    # mvp-erd.md §9 규칙에 따라 서버에서 조립된다. 프로필, 선호, 오늘 상태,
    # 최근 Raw 메시지, 관련 요약, 필터를 통과한 장기 기억, 동의된 돌봄 기록.
    # 로봇은 벡터 검색을 직접 하지 않는다.
    ctx: dict
    # 백엔드에 닿지 못해 로컬 읽기 캐시에서 가져왔을 때 True.
    # 이 경우 핸들러는 사실에 대해 단정적으로 말하지 않아야 한다.
    ctx_is_cached: bool

    # ── 출력 (§14) ──
    response: str
    # 문장 단위로 쪼갠 출력. 문장 경계가 곧 안전한 중단 지점이고, 그래서 같은 분할이
    # TTS 속도 조절과 barge-in 복구에 동시에 쓰인다 (§13).
    sentences: list[str]
    final_utterance: str | None   # None 은 "침묵을 선택했다"는 뜻

    # ── BARGE-IN (§13) ── 턴 사이에 유지된다
    #
    # speaking / spoken_prefix 에는 쓰는 주체가 '둘' 있다. 재생 스레드와 이 state.
    # 그래서 시스템에서 동기화 버그가 가장 나기 쉬운 값이다. 진행 상황의 권위는
    # 재생 스레드에 있고, 이 state 는 스냅샷으로 취급한다.
    speaking: bool
    spoken_prefix: str
    # 잘려나간 나머지. 원래 우선순위로 다시 제안될 준비가 된 상태.
    # 재큐 후에는 비운다. 단 생존 확인 프로브였다면 일부러 '버린다'.
    # 끼어든 것 자체가 이미 어르신이 살아있음을 증명했기 때문이다 (§13).
    interrupted_remainder: SpeechProposal | None

    # ── 턴 사이에 살아남아야 하는 런타임 값 ──
    last_spoke_at: float
    last_user_interaction_at: float
    # 침묵 사다리를 몇 칸 올라갔는가. 0 이면 이상 없음.
    silence_level: int

    # ── 환경: 세 개의 안전 신호 (§10) ──
    #
    # occupancy  -> 현관 센서에서: 어르신이 집에 있는가?
    # rest_state -> vision 에서: 쉬는 중인가 깨어 있는가?
    # voice      -> 여기 저장되지 않는다. last_user_interaction_at 이 그 역할이다.
    #
    # 침묵의 해석은 세 신호 모두에 달려 있다. HOME + AWAKE + 침묵이 의심스러운
    # 조합이고, HOME + RESTING + 침묵은 그냥 낮잠 자는 사람이다.
    occupancy: Occupancy
    occupancy_observed_at: float
    rest_state: RestState
    last_door_event: dict | None      # {"direction": "in"|"out", "ts": float}
    door_heartbeat_at: float             # 현관 라즈베리파이의 마지막 하트비트

    # 값싼 로컬 오디오 판정. 녹음하지 않고, 저장하지 않고, 전송하지 않는다 (§10).
    # {"someone_speaking": bool, "ambient_sound": bool}
    audio_ctx: dict


def initial_state(senior_id: str) -> ConvState:
    """콜드 스타트용 기본값.

    무엇을 하는가
        새 thread 가 시작할 때의 state 를 만든다. 어떤 노드도 첫 실행에서 키가
        없는 상황을 방어하지 않아도 되게 한다.

    누가 호출하는가
        bootstrap, 그리고 깨끗한 thread 가 필요한 테스트.

    주의사항
        occupancy 는 HOME 이 아니라 UNKNOWN 으로 시작한다. 현관 노드로부터 아직
        아무 소식도 못 들었고, 집에 있다고 가정하면 어쩌면 빈 집을 상대로 침묵
        사다리가 돌아간다. 보수적으로 추정하는 것이 UNKNOWN 값이 존재하는 이유다.
    """
    from bomi_ai_chat.clock import clock

    now = clock.now()
    return {
        "messages": [],
        "proposals": [],
        "safety_level": "none",
        "last_spoke_at": 0.0,
        "last_user_interaction_at": now,
        "silence_level": 0,
        "occupancy": "UNKNOWN",
        "occupancy_observed_at": 0.0,
        "rest_state": "UNKNOWN",
        "door_heartbeat_at": 0.0,
        "speaking": False,
        "spoken_prefix": "",
        "interrupted_remainder": None,
        "audio_ctx": {},
        "ctx": {},
        "ctx_is_cached": False,
    }
