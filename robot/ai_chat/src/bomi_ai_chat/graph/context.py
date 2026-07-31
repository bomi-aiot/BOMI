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

from bomi_ai_chat import policy
from bomi_ai_chat.state import ConvState


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
    # 아래 두 값은 TODO(backend_client) 호출의 인자로 그대로 들어간다. 지금은 호출이
    # 없어서 미사용이지만, 여기에 두는 것이 결정을 기록한다. 문서는 info 인텐트에서만
    # 요청하고(§8), top-k 는 함수에 박지 않고 policy 에서 읽는다.
    want_documents = state.get("intent") == "info"  # noqa: F841
    top_k = policy.MEMORY_TOP_K  # noqa: F841

    # TODO(backend_client): ctx = fetch_context(senior_id, query=state["user_input"],
    #                                           top_k=top_k, documents=want_documents)
    # TODO(localstore): 전송 오류가 나면 read_context_cache(senior_id) 로 대체하고
    #   ctx_is_cached=True 로 둔다. 절대 예외를 던지지 않는다. 문맥 실패는 턴을
    #   중단시키는 것이 아니라 저하시켜야 한다.
    return {"ctx": {}, "ctx_is_cached": False}


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
        - 순서가 중요하다. 재질의가 필요한 활성 fact_candidate 는 보통 잡담보다
          우선해야 하지만, 어르신이 직접 질문한 턴을 가로채서는 안 된다. 먼저 대답하고
          나중에 재질의한다.
        - 한 대화에서 질의할 수 있는 fact_candidate 는 '하나'뿐이다. DB 계약 규칙이며,
          그래프가 그것을 강제하는 지점이 바로 여기다 (CLAUDE.md §12).
    """
    if state.get("intent"):
        return {}

    # TODO: 규칙 기반 분류를 먼저 시도하고, 애매할 때만 llm/router.py 의 임베딩
    #   라우터에 위임한다. 라우터를 매 턴 부르면 임베딩 API 왕복이 지연 예산에
    #   얹힌다. 규칙으로 대부분을 걸러내는 것이 2초 예산에 유리하다.
    #   그리고 위 주의사항의 fact_candidate 우선순위 규칙도 여기 들어간다.
    return {"intent": "companion"}


def route_intent(state: ConvState) -> str:
    """조건부 엣지: 인텐트 이름 -> 핸들러 노드 이름."""
    return "handle_" + state["intent"]
