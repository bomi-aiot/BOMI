"""컨텍스트 조립 — 로봇과 백엔드 사이의 이음새.

어디에 위치하는가
    게이트/트리아지 계층과 핸들러 사이. 말하는 모든 턴이 여기를 지나면서 프롬프트를
    만들 재료를 모은다.

왜 로봇이 검색을 직접 하지 않는가
    사실은 백엔드 DB 에 있고, 백엔드는 이미 올바르게 검색하는 방법을 안다.
    선필터(senior_id, lifecycle ACTIVE, verification 이 REJECTED 아님, visibility)를
    적용하고, 유사도 x importance x 최근성으로 재정렬하고, 상위 몇 개만 돌려준다.
    이걸 로봇에서 다시 구현하면 하나의 정확성 핵심 규칙에 대한 구현이 두 개가 된다.

    역할 분담 (CLAUDE.md §5):
        백엔드 = '사실'과 '검색'의 권위
        로봇   = '타이밍'과 '전달'의 권위

절대 벡터 검색해서는 안 되는 것
    프로필, 복약, 일정, 회피 주제 목록. "내 약이 뭐야?"는 정확한 답이 필요하고,
    임베딩은 "혈압약"과 "혈당약"을 거의 동일하게 평가한다. 백엔드가 이미 두 종류의
    데이터를 분리해 두었으니, 전부를 하나의 유사도 질의로 요청해서 그걸 무너뜨리지
    않는다 (CLAUDE.md §8).

읽는 값   user_input, intent
쓰는 값   ctx, ctx_is_cached

db/ 와 backend_client/ 의 경계  ★ 혼동 주의
    db/medical_repository.py = 의료 '참조' 데이터 조회(병원·약국·의약품 허가).
        정확·지오 조회이며 RAG 가 아니다. 이 경로는 그대로 유지한다.
    backend_client/          = 어르신의 '사실과 기억'(프로필, memory, care_record).
        반드시 백엔드 API 를 통한다. ssh_tunnel 로 직접 조회하지 않는다.
    두 경로를 섞으면 검색 규칙(선필터·visibility·동의)이 두 곳에 구현된다.

참고
    CLAUDE.md §5 (소유권과 API 이음새), §8 (기억과 RAG 경계)
    docs/database/mvp-erd.md §9 (권위 있는 문맥 조립 레시피)
"""

from __future__ import annotations

import logging
import re

from bomi_ai_chat import policy
from bomi_ai_chat.backend_client import BackendContextClient
from bomi_ai_chat.graph import contract_dialogue
from bomi_ai_chat.state import ConvState

logger = logging.getLogger(__name__)

# 클라이언트를 지연 생성해 한 번만 만든다.
#
# 왜 모듈 최상단에서 만들지 않는가
#   생성 시점에 Settings 를 읽는다. import 시점에 읽으면 테스트가 환경변수를 바꾸기
#   전에 굳어버리고, .env 가 없는 환경에서는 import 자체가 실패한다.
_CLIENT: BackendContextClient | None = None


def _client() -> BackendContextClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = BackendContextClient()
    return _CLIENT


def set_client(client: BackendContextClient | None) -> None:
    """클라이언트를 교체한다. 테스트와 부트스트랩에서 쓴다."""
    global _CLIENT
    _CLIENT = client


def context_read(state: ConvState) -> dict:
    """이번 턴에 쓸 조립된 대화 문맥을 가져온다.

    무엇을 하는가
        mvp-erd.md §9 에 서술된 묶음을 백엔드에 요청한다.
          1. 프로필과 선호            (정확 조회)
          2. 오늘 상태                (복약 이행, 기분, 식사)
          3. 최근 Raw 메시지 6~12개   (conversation_message)
          4. 관련 요약                (conversation_summary)
          5. 필터를 통과한 장기 기억   (memory, 상위 3~10)
          6. 동의된 돌봄 기록          (care_record)
        실패하면 로컬 읽기 캐시로 대체하고 ctx_is_cached 를 세운다.

    왜 이 대체 경로가 중요한가
        없으면 연결이 한 번 끊기는 것만으로 로봇이 벙어리가 된다. 안전 기기에서 그것은
        최악의 실패 양상이므로, 대신 얕은 대화를 받아들인다. 캐시된 프로필과 기억
        몇 개면 로봇은 계속 말할 수 있고, 침묵 사다리는 미리 만들어둔 음성으로 계속
        동작한다 (CLAUDE.md §18).

    누가 호출하는가
        build.py — 말하는 모든 턴. 반응형이든 능동이든.

    무엇을 호출하는가
        backend_client.fetch_context. 실패 시 localstore.read_context_cache.

    반환값
        {"ctx": {...}, "ctx_is_cached": bool}

    주의사항
        - 이 호출은 지연 예산 '안에' 있다. top-k 는 policy.MEMORY_TOP_K 로 유지하고,
          압박 상황에서는 MEMORY_TOP_K_DEGRADED 로 내린다(policy.DEGRADATION_ORDER).
        - 문서(복지제도, FAQ)는 info 인텐트일 때'만' 요청한다. 잡담에 문서를 검색하면
          지연을 낭비하고 프롬프트를 오염시킨다.
        - ctx_is_cached 가 True 면 핸들러는 일정과 복약에 대해 단정적으로 말하지 않아야
          한다. 캐시는 낡았을 수 있고, 낡은 복약 정보를 단정적으로 말하는 것은 품질
          문제가 아니라 안전 문제다.
    """
    senior_id = state.get("senior_id")
    if not senior_id:
        # thread_id 가 곧 어르신 id 이므로 정상 경로에서는 항상 있다. 없다면 배선
        # 오류이고, 조용히 빈 문맥으로 넘어가면 "왜 로봇이 아무것도 기억 못 하나"를
        # 나중에 추적할 수 없다.
        logger.error("context_read called without senior_id; continuing with empty context")
        return {"ctx": {}, "ctx_is_cached": True}

    # 문서는 info 인텐트에서만 요청한다(§8). top-k 는 함수에 박지 않고 policy 에서 읽으며,
    # 성능 저하 모드에서는 낮춘 값이 들어온다(policy.DEGRADATION_ORDER).
    want_documents = state.get("intent") == "info"
    top_k = state.get("memory_top_k") or policy.MEMORY_TOP_K

    result = _client().fetch_context(
        senior_id,
        query=state.get("user_input", ""),
        conversation_id=state.get("conversation_id"),
        top_k=top_k,
        documents=want_documents,
    )
    return {"ctx": result.ctx, "ctx_is_cached": result.is_cached}


def classify_intent(state: ConvState) -> dict:
    """어느 핸들러가 문장을 쓸지 결정한다 — 로컬에서, LLM 호출 없이.

    무엇을 하는가
        인텐트가 이미 정해져 있으면 곧바로 반환한다. 그게 흔한 경우다. 게이트가 이긴
        제안에서 복사해 오므로 스케줄러·현관·재질의 턴은 이미 라벨이 붙어서 도착한다.
        자유 형식의 어르신 발화만 분류가 필요하다.

    왜 여기서 LLM 을 쓰지 않는가
        LLM 왕복 한 번은 500~1500ms 이고, STT 와 TTS 를 포함한 턴 전체에 약 2초밖에
        없다. 턴당 생성 호출 1회가 예산이다 (CLAUDE.md §16). 규칙으로 부족하다면
        왕복을 늘리지 말고 생성 호출에 분류를 합쳐서 JSON 으로 받는다.

    누가 호출하는가
        build.py, context_read 다음.

    반환값
        이미 알고 있으면 {}, 아니면 {"intent": ...}.

    주의사항
        - 순서가 중요하다. 대기 중인 계약 질문은 잡담보다 우선하지만, 어르신이 직접
          질문한 턴을 가로채서는 안 된다. 먼저 대답하고 나중에 재질의한다.
        - 한 대화에서 질의할 수 있는 fact_candidate 는 '하나'뿐이다. DB 계약 규칙이며,
          그것을 강제하는 곳은 백엔드(하나만 내려줌)와 contract_tick(한 대화에 한 번만
          제안)이다 (CLAUDE.md §12).
    """
    if state.get("intent"):
        return {}

    text = (state.get("user_input") or "").strip()
    if not text:
        # 발화가 없는데 인텐트도 없다면 말벗으로 둔다. info 로 두면 있지도 않은
        # 질문에 답하려 든다.
        return {"intent": "companion"}

    pending = _pending_contract_intent(state, text)
    if pending:
        return {"intent": pending}

    return {"intent": _classify(text)}


def _pending_contract_intent(state: ConvState, text: str) -> str | None:
    """이 발화가 '방금 로봇이 던진 계약 질문'에 대한 답인가.

    ★ 어르신이 먼저 물은 턴은 가로채지 않는다  (CLAUDE.md §12)

        로봇이 복약 용량을 묻고 기다리는 중인데 어르신이 "오늘 며칠이야?"라고 하면,
        그것은 답이 아니라 새 질문이다. 여기서 clarification 으로 보내면 로봇은
        어르신의 질문을 무시하고 자기 질문을 밀어붙이는 셈이 된다.

        **먼저 답하고, 재질의는 나중에.** 대기 상태는 사라지지 않으므로 다음 턴에
        다시 이어진다. 재질의가 한 턴 늦는 비용은 작고, 어르신의 질문을 무시하는
        비용은 크다.

    왜 확인 단계는 가로채는가
        복창에 대한 답은 "네"/"아니요"이고, 그것이 의문형일 수 없다. 확인 단계에서
        의문형이 오면 그것은 어르신이 되묻는 것이므로 여전히 가로채지 않는다 —
        아래 검사가 두 단계 모두에 같이 적용된다.

    반환값
        "onboarding" | "clarification" | None
    """
    pending = state.get("pending_contract")
    if not pending:
        return None

    if contract_dialogue.looks_like_a_question(text):
        logger.info("the senior asked something; answering first and deferring the %s question",
                    pending.get("kind"))
        return None

    kind = pending.get("kind")
    return kind if kind in {"onboarding", "clarification"} else None


# 지남력·사실 질문의 표지.
#
# 지남력 질문("오늘 며칠이야?")이 가장 빈번한 질문 유형이고, 초기 치매에서는 더
# 잦아진다. 매번 따뜻하게 답해야 하므로 반드시 info 로 흘러가야 한다 (CLAUDE.md §8).
_INFO_MARKERS = (
    "몇 시", "몇시", "며칠", "무슨 요일", "무슨요일", "오늘 날짜", "지금 몇",
    "날씨", "기온", "비 와", "비와", "추워", "더워",
    "뭐야", "뭔가요", "알려줘", "알려주", "가르쳐", "어디야", "어디에",
)

# 지남력 질문의 표지. _INFO_MARKERS 의 부분집합이다.
#
# ★ 왜 따로 두는가
#   지남력 질문의 '반복 횟수'는 인지 저하의 이른 신호이고, T2 추세로 가야 한다
#   (S15P11E102-211). 그런데 그 값이 프롬프트에 닿으면 어조에 새어나가서 열 번째
#   답변이 짜증스럽게 들린다.
#
#   그래서 두 가지를 동시에 한다. 로봇은 매번 똑같이 따뜻하게 답하고(프롬프트는
#   반복 횟수를 모른다), 서버는 그 반복을 센다(플래그만 실어 보낸다).
#   그 둘을 분리할 수 있어서 둘 다 가능하다 (CLAUDE.md §8).
#
#   날씨는 여기 없다. "오늘 추워?"는 지남력 질문이 아니라 그냥 정보 질문이다.
_ORIENTATION_MARKERS = (
    "몇 시", "몇시", "며칠", "무슨 요일", "무슨요일", "오늘 날짜", "지금 몇",
    "오늘이", "며칟", "무슨 날", "언제였", "여기 어디", "여기가 어디",
)


def is_orientation_question(text: str) -> bool:
    """어르신이 지남력 질문을 했는가.

    누가 호출하는가
        graph/build.py 의 memory_write. 백엔드에 플래그로 실어 보낸다.

    왜 서버가 아니라 로봇이 판정하는가
        로봇은 이미 분류하고 있다(_classify). 서버가 본문을 다시 분석하면 같은
        판정이 두 곳에 생기고 둘이 갈라진다. 그리고 서버가 대화 본문을 분석하기
        시작하면 그 코드는 곧 다른 목적으로도 쓰인다.

    주의사항
        이 값은 T2 추세로만 간다. **절대 프롬프트로 되돌아가지 않는다.**
    """
    return any(marker in (text or "") for marker in _ORIENTATION_MARKERS)

# 복약·일정을 '처리'하려는 발화. 조회가 아니라 상태 변경이므로 schedule 로 간다.
_SCHEDULE_MARKERS = (
    "약 먹었", "약먹었", "약 드셨", "복용했", "챙겨 먹었",
    "일정", "약속", "병원 예약", "예약",
)

# 정서 표현. 듣는 것이 목적이고, 정보를 주려 들면 안 된다.
_EMOTIONAL_MARKERS = (
    "외로", "쓸쓸", "보고 싶", "보고싶", "슬퍼", "우울", "허전", "힘들어", "속상",
)

_QUESTION_SUFFIX = re.compile(r"(까요|나요|어요\?|가요|니\?|냐\?|\?)\s*$")


def _classify(text: str) -> str:
    """규칙만으로 인텐트를 고른다.

    왜 규칙이 먼저인가
        여기서 LLM 을 부르면 턴당 왕복이 하나 더 붙는다. 생성 호출 하나에 500~1500ms
        인데 턴 전체 예산이 약 2초다 (CLAUDE.md §16). 대부분의 발화는 값싼 표지로
        갈린다.

    router.py 에 대한 정정
        llm/router.py 의 판정은 '로컬' SentenceTransformer 추론이다. 외부 API 왕복이
        아니므로 네트워크 예산을 쓰지는 않는다. 다만 모델을 메모리에 상주시키고
        CPU 시간을 쓰므로, 값싼 문자열 검사로 갈리는 것을 굳이 넘기지 않는다.

    주의사항
        정서 표지를 정보 표지보다 먼저 본다. "외로운데 오늘 며칠이야"는 날짜를
        알려주는 턴이 아니라 들어야 하는 턴이다. 정보로 처리하면 사람이 아니라
        검색창처럼 반응하게 된다.
    """
    lowered = text.lower()

    if any(marker in lowered for marker in _EMOTIONAL_MARKERS):
        return "emotional"
    if any(marker in lowered for marker in _SCHEDULE_MARKERS):
        return "schedule"
    if any(marker in lowered for marker in _INFO_MARKERS):
        return "info"

    # 의료·위치 질문은 기존 임베딩 라우터가 이미 잘 판정한다. 재구현하지 않고
    # 물음표로 끝나는 애매한 발화에서만 위임한다.
    if _QUESTION_SUFFIX.search(text) and _is_medical(text):
        return "info"

    # 나머지는 전부 말벗이다. 이 제품에서 기본값이 정보 제공이 아니라 대화인 것은
    # 의도된 선택이다. 외로움이 1번 문제이고 말벗이 본체다 (CLAUDE.md §1).
    return "companion"


def _is_medical(text: str) -> bool:
    """의료 질의 판정을 기존 라우터에 위임한다. 실패해도 턴을 죽이지 않는다."""
    try:
        from bomi_ai_chat.llm import router

        return router.is_medical_query(text)
    except Exception:  # noqa: BLE001 - 모델 로딩 실패가 대화를 끊으면 안 된다
        logger.debug("medical router unavailable; falling back to companion", exc_info=True)
        return False


def route_intent(state: ConvState) -> str:
    """조건부 엣지: 인텐트 이름 -> 핸들러 노드 이름."""
    return "handle_" + state["intent"]
