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

읽는 값   user_input, intent, is_medical_query
쓰는 값   ctx, ctx_is_cached, is_medical_query

db/ 와 backend_client/ 의 경계  ★ 혼동 주의
    db/medical_repository.py = 의료 '참조' 데이터 조회(병원·약국·의약품 허가).
        정확·지오 조회이며 RAG 가 아니다. 이 경로는 그대로 유지한다.
    backend_client/          = 어르신의 '사실과 기억'(프로필, memory, care_record).
        반드시 백엔드 API 를 통한다. ssh_tunnel 로 직접 조회하지 않는다.
    두 경로를 섞으면 검색 규칙(선필터·visibility·동의)이 두 곳에 구현된다.

날씨·의료 조회가 왜 핸들러가 아니라 여기 있는가 (S15P11E102-311)
    handle_info 는 §6 규칙대로 "무엇을 말할지"만 정해야 하고 직접 I/O 를 하면
    안 된다(§23). 그런데 "근처 병원 어디야", "오늘 서울 날씨 어때" 는 근거 데이터
    없이는 LLM 이 그냥 지어낸다. 그래서 조회 자체는 이 노드(context_read)가 하고,
    결과를 ctx["documents"] 에 담아 넘긴다. prompts/builder.py 가 info 인텐트일 때
    그 목록을 "참고 자료" 섹션으로 이미 렌더하므로 프롬프트 빌더 시그니처는 바뀌지
    않는다. handle_info 는 여전히 _generate() 한 번만 부르는 얇은 핸들러로 남는다.

참고
    CLAUDE.md §5 (소유권과 API 이음새), §8 (기억과 RAG 경계), §14 (날씨는 행동이다),
    §16 (턴당 생성 호출 1회), §23 (핸들러 직접 I/O 금지)
    docs/database/mvp-erd.md §9 (권위 있는 문맥 조립 레시피)
"""

from __future__ import annotations

import logging
import re

from bomi_ai_chat import degradation
from bomi_ai_chat.backend_client import BackendContextClient
from bomi_ai_chat.graph import contract_dialogue
from bomi_ai_chat.llm.medical_flow import handle_medical_query
from bomi_ai_chat.state import ConvState
from bomi_ai_chat.weather.client import WeatherClient, extract_city

logger = logging.getLogger(__name__)

# 클라이언트를 지연 생성해 한 번만 만든다.
#
# 왜 모듈 최상단에서 만들지 않는가
#   생성 시점에 Settings 를 읽는다. import 시점에 읽으면 테스트가 환경변수를 바꾸기
#   전에 굳어버리고, .env 가 없는 환경에서는 import 자체가 실패한다.
_CLIENT: BackendContextClient | None = None

# 날씨 클라이언트도 같은 이유로 지연 생성한다 (S15P11E102-311).
_WEATHER_CLIENT: WeatherClient | None = None


def _client() -> BackendContextClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = BackendContextClient()
    return _CLIENT


def set_client(client: BackendContextClient | None) -> None:
    """클라이언트를 교체한다. 테스트와 부트스트랩에서 쓴다."""
    global _CLIENT
    _CLIENT = client


def _weather_client() -> WeatherClient:
    global _WEATHER_CLIENT
    if _WEATHER_CLIENT is None:
        _WEATHER_CLIENT = WeatherClient()
    return _WEATHER_CLIENT


def set_weather_client(client: WeatherClient | None) -> None:
    """날씨 클라이언트를 교체한다. 테스트와 부트스트랩에서 쓴다."""
    global _WEATHER_CLIENT
    _WEATHER_CLIENT = client


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
        {"ctx": {...}, "ctx_is_cached": bool, "is_medical_query": bool | None}

    주의사항
        - 이 호출은 지연 예산 '안에' 있다. top-k 는 policy.MEMORY_TOP_K 로 유지하고,
          압박 상황에서는 MEMORY_TOP_K_DEGRADED 로 내린다(policy.DEGRADATION_ORDER).
        - 문서(복지제도, FAQ)는 info 인텐트일 때'만' 요청한다. 잡담에 문서를 검색하면
          지연을 낭비하고 프롬프트를 오염시킨다.
        - ctx_is_cached 가 True 면 핸들러는 일정과 복약에 대해 단정적으로 말하지 않아야
          한다. 캐시는 낡았을 수 있고, 낡은 복약 정보를 단정적으로 말하는 것은 품질
          문제가 아니라 안전 문제다.
        - 날씨·의료 조회(S15P11E102-311)는 백엔드 문서 검색과 별개다. 반응형 턴은
          이 시점에 아직 classify_intent 가 돌지 않았으므로(intent 가 비어 있다),
          같은 규칙으로 '미리' 살펴봐서 조회 여부를 정한다. 자세한 이유는
          _gather_lookup_documents 참고.
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
    # 저하 단계를 실제로 읽는다 (S15P11E102-212). 212 전까지 이 주석은 "압박 상황에서는
    # 낮춘 값이 들어온다"고 말했지만 넣는 사람이 없었다.
    want_documents = state.get("intent") == "info" and degradation.documents_allowed()
    top_k = state.get("memory_top_k") or degradation.memory_top_k()

    result = _client().fetch_context(
        senior_id,
        query=state.get("user_input", ""),
        conversation_id=state.get("conversation_id"),
        top_k=top_k,
        documents=want_documents,
    )

    lookup_documents, medical_flag = _gather_lookup_documents(state)
    ctx = result.ctx
    if lookup_documents:
        # 백엔드 문서(복지제도·FAQ)와 우리가 직접 조회한 날씨·의료 자료를 같은
        # "참고 자료" 슬롯에 합친다. build_prompt 는 출처를 구분하지 않는다 —
        # 어차피 둘 다 "모델이 답을 지어내지 말고 참고할 것"이라는 같은 역할이다.
        ctx = {**ctx, "documents": [*(ctx.get("documents") or []), *lookup_documents]}

    return {
        "ctx": ctx,
        "ctx_is_cached": result.is_cached,
        # 이 턴에 판정하지 않았으면 명시적으로 None 을 써서, 지난 턴에 남은 값이
        # 이번 턴까지 새는 것을 막는다. checkpoint 된 state 는 이 노드가 손대지
        # 않는 키를 그대로 들고 있기 때문이다(state.py 의 is_medical_query 설명 참고).
        "is_medical_query": medical_flag,
        "recent_phrasings": _lookup_recent_phrasings(state, senior_id),
    }


def _lookup_recent_phrasings(state: ConvState, senior_id: str) -> list[str]:
    """같은 종류의 알림에서 최근에 쓴 표현을 찾는다 (§17.8, S15P11E102-256).

    무엇을 하는가
        능동/명령 턴(trigger_type in "proactive"/"backend_command")에서만
        phrasing_key 를 만들어 localstore.phrasings.recent 로 조회한다.

    ★ 왜 반응형 턴은 항상 빈 리스트인가 — 이 함수에서 가장 중요한 판단
        speech_origin 과 intent 는 checkpoint 된 state 의 필드라 reducer 가 없다
        (state.py 참고). 능동 턴이 "silence_ladder:1" 을 남기고 나면, 바로 다음
        어르신 발화(user_utterance) 턴에도 그 값이 그대로 남아 있다 — 아무도
        지우지 않았을 뿐이다. 이 함수가 trigger_type 을 보지 않고 speech_origin
        만 봤다면, "능동 턴 직후의 반응형 턴"에 지난 알림의 표현 이력이 새어
        들어간다. graph/build.py._record_phrasing 도 기록 쪽에서 같은 가드를
        쓴다 — 둘이 어긋나면 저장과 조회 중 하나만 걸러져 조용히 틀린다.

    누가 호출하는가
        context_read, ctx 를 만든 다음.

    반환값
        표현 문자열 목록. 반응형 턴이거나, origin/intent 가 다양화 대상이 아니면
        (graph.phrasing.phrasing_key 참고) 빈 리스트.
    """
    if state.get("trigger_type") not in ("proactive", "backend_command"):
        return []

    from bomi_ai_chat.graph.phrasing import phrasing_key
    from bomi_ai_chat.localstore import phrasings

    key = phrasing_key(state.get("speech_origin") or "", state.get("intent") or "")
    return phrasings.recent(senior_id, key)


# ─────────────────────────────────────────────────────────────────────────────
# 날씨·의료 조회 (S15P11E102-311)
#
# 핸들러가 아니라 여기서 조회하는 이유는 모듈 docstring 참고. 이 절의 함수들은
# 전부 "무엇을 조회할지"만 정하고, 실제 호출은 이미 검증된 기존 클라이언트
# (weather/client.py, llm/medical_flow.py)에 위임한다 — 재구현하지 않는다.
#
# _WEATHER_MARKERS 는 아래에서 정의하지 않는다. _INFO_MARKERS 바로 위(§8 절)에
# 이미 있고, 여기서 또 만들면 "날씨 질문"의 기준이 두 곳에 생긴다.
# ─────────────────────────────────────────────────────────────────────────────


# 라우터(SentenceTransformer 추론)를 부르기 '전'에 거치는 값싼 1차 필터.
#
# 왜 필요한가
#   라우터는 네트워크는 안 쓰지만(로컬 추론) 모델이 첫 호출에서 로딩된다
#   (llm/router.py 최상단 `SentenceTransformer(...)`). "안녕하세요", "심심해"
#   같은 흔한 잡담까지 매번 라우터로 보내면 평범한 대화 테스트마저 무거운 모델
#   로딩에 얽매인다. 그래서 의료 '시설·의약품 검색' 과 조금이라도 관련 있어
#   보이는 발화만 넘긴다.
#
# 왜 "병원"/"약국"만으로 부족한가
#   router.py 의 MEDICAL_EXAMPLES 에는 상비약 브랜드명("게보린", "정로환")과
#   진료과 이름("정형외과")도 있고, 그 발화들은 "병원"이라는 글자를 포함하지
#   않는다.
#
# ★ 바른 "약" 을 일부러 넣지 않는다
#   "내 약 뭐야", "혈압약 한 알이요" 처럼 어르신 '자신의' 복약을 묻는 흔한 말에
#   전부 걸린다. 그런 질문은 이미 ctx.careRecords(정확 조회, CLAUDE.md §8)로
#   답할 수 있고, 이 조회(medical_flow)가 다루는 "약국이 어디야"·"이 약이 뭐야
#   (허가 정보)"와는 다른 질문이다. 브랜드명·진료과처럼 구체적인 표지만 남긴다.
_MEDICAL_HINT_MARKERS = (
    "병원", "약국", "약사", "처방", "진료", "부작용", "의원",
    "정형외과", "이비인후과", "안과", "소아과", "치과", "내과", "외과", "피부과",
    "타이레놀", "게보린", "판피린", "정로환", "베아제", "활명수",
    "후시딘", "마데카솔", "우루사", "인사돌", "파스",
)


def _gather_lookup_documents(state: ConvState) -> tuple[list[dict], bool | None]:
    """날씨·의료 조회를 수행해 '참고 자료' 문서 목록을 만든다.

    무엇을 하는가
        이 턴이 info 로 흘러갈 가능성이 있을 때만(아래 _eligible_for_lookup)
        의료 힌트 표지가 있으면 라우터로 확인하고, 의료가 아니면 날씨 표지를
        본다. 의료가 이기는 이유는 legacy 경로(pipeline.py)와 같다 — 두 조건이
        동시에 참인 문장은 드물고, 있다면 의료 쪽이 더 안전 관련이 크다.

    왜 classify_intent 의 판정을 그대로 못 쓰는가
        그래프 순서가 context_read -> classify_intent 다. 반응형 턴(어르신이
        먼저 말한 턴)은 이 시점에 아직 intent 가 없다. intent 가 없다고 조회를
        건너뛰면 "근처 병원 어디야" 같은 흔한 질문이 이 티켓이 고치려는 문제
        그대로 남는다. 그래서 여기서 같은 규칙을 '미리' 한 번 본다.

    왜 의료 판정이 classify_intent._classify 보다 넓은가  ★
        _classify 는 "어디야"·"뭐야"·"알려줘" 같은 값싼 정보 표지에 먼저 걸리면
        의료 라우터까지 가지도 않고 "info" 로 확정한다("근처 병원 **어디야**"가
        정확히 이 경우다). 그 판정 자체는 옳다(info 가 맞다) — 문제는 '조회'
        여부를 그 판정에 의존하면, 의료 라우터가 한 번도 불리지 않아 조회가
        전혀 안 된다는 것이다. 그래서 여기서는 _MEDICAL_HINT_MARKERS 로 넓게
        훑어 라우터를 부른다 — _classify 가 보는 _INFO_MARKERS 매칭과는 무관하다.

    왜 힌트가 없으면 라우터를 아예 안 부르는가 (그리고 그것이 왜 안전한가)
        _classify 는 원래도 "질문형으로 끝나고 다른 표지가 없을 때만" 라우터를
        불렀다. 그 좁은 문(원래 동작)은 여기서 그대로 classify_intent 에 남아
        있다 — 힌트가 없어 여기서 판정하지 않은 턴은 is_medical_query 가 None 인
        채로 넘어가고, classify_intent 는 자기 힌트가 없으니 원래 하던 대로
        (필요하면 스스로 라우터를 불러) 판정한다. 즉 이 사전 필터는 '더 넓게
        잡는 지름길'을 추가할 뿐, 기존 좁은 경로를 막지 않는다.

    반환값
        (documents, is_medical) - documents 는 build_prompt 의 "참고 자료"에
        들어갈 {"title", "content"} 목록. is_medical 은 라우터를 이 턴에 실제로
        불렀을 때만 bool, 그 외에는 캐시할 것이 없다는 뜻으로 None.

    주의사항  ★ state["is_medical_query"] 를 여기서 '읽지' 않는다
        이 함수는 그 값을 채우는 쪽이지 읽는 쪽이 아니다. context_read 는 이번
        턴에 가장 먼저 도는 노드라, 이 시점의 state["is_medical_query"] 는 이번
        턴에 아직 아무도 쓰지 않은 값 — 즉 checkpoint 에 남은 '지난 턴' 값이다.
        그것을 캐시로 믿으면 지난 발화의 의료 판정을 이번 발화에 그대로
        재사용하는 사고가 난다. 캐시는 classify_intent(context_read 다음 노드,
        같은 턴)만 읽는다.
    """
    text = (state.get("user_input") or "").strip()
    if not _eligible_for_lookup(state, text):
        return [], None

    medical_flag: bool | None = None
    if any(marker in text for marker in _MEDICAL_HINT_MARKERS):
        medical_flag = _is_medical(text)
        if medical_flag:
            return _lookup_medical_documents(text), medical_flag

    if any(marker in text for marker in _WEATHER_MARKERS):
        return _lookup_weather_documents(text), medical_flag
    return [], medical_flag


def _eligible_for_lookup(state: ConvState, text: str) -> bool:
    """조회를 시도할 가치가 있는 턴인가.

    무엇을 하는가
        세 가지를 확인한다.
          1. 발화가 있는가. 능동 턴의 seed 는 우리가 이미 통제하는 문구라
             조회 대상이 아니다.
          2. intent 가 이미 확정돼 있다면 info 가 아닌 한 조회할 이유가 없다.
             (능동/backend_command 턴은 여기 도달하기 전에 이미 intent 가
             붙어 있다 — greeting 문구에 "비"가 우연히 들어 있다고 다시
             기상청을 부르면 낭비다.)
          3. 정서·일정 표지가 뚜렷하면 의료·날씨일 리 없다. _classify 와 같은
             우선순위다 — 정서가 정보보다 먼저다(CLAUDE.md §1).
    """
    if not text:
        return False
    intent = state.get("intent")
    if intent not in (None, "info"):
        return False
    if any(marker in text for marker in _EMOTIONAL_MARKERS):
        return False
    return not any(marker in text for marker in _SCHEDULE_MARKERS)


# 조회 실패를 "참고 자료"로 감싸는 공통 문구. 근거 없이 답하는 대신, 확인이
# 어렵다고 솔직히 말하거나 되묻으라고 모델에게 직접 지시한다(완료 조건).
_LOOKUP_FAILURE_NOTE = (
    "{topic} 정보를 지금 확인할 수 없습니다. 모르는 것을 지어내지 말고, "
    "확인이 어렵다고 솔직히 말하거나 필요한 것을 다시 여쭤봅니다."
)


def _lookup_unavailable_document(topic: str) -> dict:
    return {"title": f"{topic} 조회 실패", "content": _LOOKUP_FAILURE_NOTE.format(topic=topic)}


def _lookup_weather_documents(text: str) -> list[dict]:
    """기상청 조회를 하고 '참고 자료' 한 건으로 감싼다.

    도시를 특정 못 하면(예: "오늘 날씨 어때") 조회 자체를 시도하지 않는다.
    legacy 경로(pipeline.py)도 같다 — 이것은 조회 '실패'가 아니라 정보 부족이라,
    완료 조건 5번이 요구하는 "조회 실패" 처리(_LOOKUP_FAILURE_NOTE) 대상이 아니다.
    """
    city = extract_city(text)
    if not city:
        return []
    try:
        forecast = _weather_client().get_forecast(city)
    except Exception:  # noqa: BLE001 - 조회 실패가 턴을 죽이면 안 된다
        logger.warning("weather lookup failed for city=%s", city, exc_info=True)
        return [_lookup_unavailable_document(f"{city} 날씨")]

    summary = ", ".join(f"{label} {value}" for label, value in forecast.items())
    return [{"title": f"{city} 날씨", "content": summary}]


def _lookup_medical_documents(text: str) -> list[dict]:
    """의료 function-calling 조회(llm/medical_flow.py)를 하고 '참고 자료'로 감싼다.

    ★ 여기서 Gemini 를 한 번 더 부르는 것과 CLAUDE.md §16 의 관계
        handle_medical_query 는 자체적으로 병원/약국/의약품 검색 인자를 뽑는
        function-calling 왕복을 한다. 이 턴에는 이미 handle_info._generate() 가
        부르는 '응답 생성' 호출이 하나 있고, §16 이 세는 "턴당 생성 호출 1회"는
        바로 그 호출이다 — 여기서는 무엇을 말할지 정하지 않고 조회만 한다.
        이 호출을 handle_info 안에서 그대로 했다면 핸들러가 직접 I/O 를 하는
        셈이라 §23 을 깼을 것이다. context_read 로 올려서 그 문제만 해결한다.
    """
    try:
        answer = handle_medical_query(text)
    except Exception:  # noqa: BLE001 - 조회 실패가 턴을 죽이면 안 된다
        logger.warning("medical lookup failed", exc_info=True)
        return [_lookup_unavailable_document("의료(병원·약국·의약품)")]

    return [{"title": "의료 조회 결과", "content": answer}]


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
    text = (state.get("user_input") or "").strip()

    # ★ pending_consent 는 state.get("intent") 검사보다 먼저 본다.
    #
    #   T3 동의 질문을 던진 턴 자체가 intent="emotional" 을 남기고, 그 값은
    #   reducer 가 없는(LastValue) 채널이라 바로 다음 반응형 턴까지 checkpoint
    #   에 그대로 남아 있을 수 있다(state.py 참고). 그 우연에 기대면, 질문과
    #   답 사이에 다른 능동 발화가 하나라도 끼면(예: 복약 알림) intent 가
    #   "schedule" 로 덮여 답 판정이 조용히 새어나간다. 그래서 pending_consent
    #   가 있으면 남아 있는 intent 값과 무관하게 먼저 확인한다.
    if _pending_consent_intent(state, text):
        return {"intent": "emotional"}

    if state.get("intent"):
        return {}

    if not text:
        # 발화가 없는데 인텐트도 없다면 말벗으로 둔다. info 로 두면 있지도 않은
        # 질문에 답하려 든다.
        return {"intent": "companion"}

    pending = _pending_contract_intent(state, text)
    if pending:
        return {"intent": pending}

    # context_read 가 이미 의료 라우터를 불렀다면(S15P11E102-311) 그 결과를 넘겨
    # 받아 재사용한다 — 같은 턴에 같은 로컬 모델을 두 번 부르지 않는다.
    return {"intent": _classify(text, medical_hint=state.get("is_medical_query"))}


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

    ★ 정서 표현도 같은 이유로 가로채지 않는다  (S15P11E102-253)
        온보딩이 어떤 필드를 기다리는 중에 어르신이 "외로워"라고 하면, 그건
        답이 아니라 마음을 꺼낸 것이다. 여기서 계약으로 보내면 그 발화가
        `_extract_value` 를 거쳐 필드값 후보가 되려 들고, 정서 핸들러는 이
        턴을 아예 보지 못한다 — 위로도 못 받고, 신호도 쌓이지 않는다. 의문형과
        마찬가지로 **먼저 듣고, 계약은 나중에** 다시 잇는다.

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

    if any(marker in text for marker in _EMOTIONAL_MARKERS):
        logger.info("the senior spoke emotionally; answering that first and deferring "
                    "the %s question", pending.get("kind"))
        return None

    kind = pending.get("kind")
    return kind if kind in {"onboarding", "clarification"} else None


def _pending_consent_intent(state: ConvState, text: str) -> bool:
    """이 발화가 '방금 로봇이 던진 T3 동의 질문'에 대한 답인가 (S15P11E102-253).

    _pending_contract_intent 와 같은 원칙이다 — 어르신이 먼저 물은 턴은
    가로채지 않는다. 로봇이 "가족분께 전해도 될까요"라고 물었는데 어르신이
    "오늘 며칠이야?"라고 하면 그것은 답이 아니라 새 질문이다. pending_consent
    는 사라지지 않으므로(_resolve_consent_answer 만 지운다) 다음 턴에 다시
    이어진다.

    반환값
        True  -> handle_emotional 로 보내 답을 판정한다.
        False -> pending_consent 가 없거나, 어르신이 먼저 물었다.
    """
    pending = state.get("pending_consent")
    if not pending:
        return False
    if contract_dialogue.looks_like_a_question(text):
        logger.info("the senior asked something; answering first and deferring "
                    "the T3 consent question")
        return False
    return True


# 날씨 질문의 표지. _gather_lookup_documents(아래 §311 절)가 조회 여부를 정하는
# 데도 그대로 재사용한다 — "info 로는 분류됐는데 조회는 안 됐다" 같은 두 곳의
# 어긋남을 막으려면 표지가 하나여야 한다.
_WEATHER_MARKERS = ("날씨", "기온", "비 와", "비와", "추워", "더워")

# 지남력·사실 질문의 표지.
#
# 지남력 질문("오늘 며칠이야?")이 가장 빈번한 질문 유형이고, 초기 치매에서는 더
# 잦아진다. 매번 따뜻하게 답해야 하므로 반드시 info 로 흘러가야 한다 (CLAUDE.md §8).
_INFO_MARKERS = (
    "몇 시", "몇시", "며칠", "무슨 요일", "무슨요일", "오늘 날짜", "지금 몇",
    *_WEATHER_MARKERS,
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


def _classify(text: str, *, medical_hint: bool | None = None) -> str:
    """규칙만으로 인텐트를 고른다.

    왜 규칙이 먼저인가
        여기서 LLM 을 부르면 턴당 왕복이 하나 더 붙는다. 생성 호출 하나에 500~1500ms
        인데 턴 전체 예산이 약 2초다 (CLAUDE.md §16). 대부분의 발화는 값싼 표지로
        갈린다.

    router.py 에 대한 정정
        llm/router.py 의 판정은 '로컬' SentenceTransformer 추론이다. 외부 API 왕복이
        아니므로 네트워크 예산을 쓰지는 않는다. 다만 모델을 메모리에 상주시키고
        CPU 시간을 쓰므로, 값싼 문자열 검사로 갈리는 것을 굳이 넘기지 않는다.

    인자
        medical_hint: context_read 가 조회 여부를 정하려고 이미 라우터를 불렀다면
            그 결과(S15P11E102-311). None 이 아니면 라우터를 다시 부르지 않고
            그대로 쓴다 — 값싼 마커 검사와 달리 라우터는 모델 추론이라, 같은 턴에
            두 번 부를 이유가 없다.

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
    # 물음표로 끝나는 애매한 발화에서만 위임한다. medical_hint 가 있으면(311)
    # context_read 가 이미 부른 라우터 결과를 재사용한다.
    if _QUESTION_SUFFIX.search(text):
        is_medical = medical_hint if medical_hint is not None else _is_medical(text)
        if is_medical:
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
