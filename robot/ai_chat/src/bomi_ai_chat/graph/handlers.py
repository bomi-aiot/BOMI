"""일곱 개의 핸들러 — '무엇을' 말할지 정하고, '말할지 여부'는 정하지 않는다.

어디에 위치하는가
    인텐트 라우터와 response_shaper 사이. 핸들러가 실행되는 시점에는 말하기로 하는
    결정이 이미 끝났고(게이트), 안전 티어가 확인됐고(트리아지), 문맥이 도착해 있다
    (context_read).

모든 핸들러의 단 하나의 규칙
    핸들러는 `response` 텍스트를 만든다. 말할지 여부를 정하지 않고, 네트워크나 DB 에
    직접 접근하지 않고, 오디오를 내보내지 않는다. 타이밍은 게이트의 것이고,
    I/O 는 backend_client 와 localstore 의 것이다.

    왜 이렇게 엄격한가: 핸들러가 자기 출력을 억제할 수 있게 되는 순간
    "로봇이 왜 조용했는가"에 대한 답이 하나가 아니게 되고, 게이트를 신뢰할 수 없게 된다.

핸들러의 두 계열
    개방형:       info, companion, schedule, emotional, greeting
                  LLM 이 자연스럽게 표현할 여지가 있다. 병원·약국·의약품·날씨
                  조회(S15P11E102-311)는 이 핸들러들이 직접 하지 않는다 —
                  context_read 가 미리 조회해 ctx["documents"]("참고 자료")로
                  넘기고, info 핸들러의 _generate() 가 그것을 참고해 답한다.
                  실제 조회는 llm/medical_flow.py·weather/client.py 에 위임한다
                  (graph/context.py 의 _gather_lookup_documents 참고).
    계약 주도형:   onboarding, clarification
                  백엔드가 강제하는 계약이 정의한 고정 슬롯을 채운다. LLM 에게 자유를
                  거의 주지 않는다. 한 필드, 한 질문, 그 외에는 아무것도 (CLAUDE.md §12).

기존 모듈에 위임한다 (재구현 금지)
    이 패키지에는 이미 검증된 클라이언트들이 있다. 핸들러는 얇아야 한다.
        일반 대화        -> llm/client.py
        의도 분류        -> llm/router.py 에 위임 (context.classify_intent 참고)
    핸들러가 하는 일은 "무엇을 말할지"를 정하고 프롬프트를 조립해 위 클라이언트를
    호출하는 것까지다. HTTP 호출이나 SQL 을 직접 쓰지 않는다.

파일 배치에 대한 메모
    CLAUDE.md §20 은 `handlers/` 패키지를 명시한다. 스텁 상태에서는 한 모듈이 읽기
    쉬우므로 여기 모아두었다. 어느 핸들러든 실제 로직이 생기면 바로 분리한다.

참고
    CLAUDE.md §12 (계약 주도형 대화), §14 (발화 규칙), §16 (프롬프트)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bomi_ai_chat import policy
from bomi_ai_chat.backend_client.contract_client import (
    BackendClarificationClient,
    BackendOnboardingClient,
    BackendUnavailable,
)
from bomi_ai_chat.clock import clock
from bomi_ai_chat.graph import contract_dialogue
from bomi_ai_chat.localstore import consent as consent_store
from bomi_ai_chat.localstore import emotion, outbox
from bomi_ai_chat.localstore import proposals as proposal_store
from bomi_ai_chat.prompts import (
    build_extraction_prompt,
    build_field_question_prompt,
    build_prompt,
)
from bomi_ai_chat.state import ConvState
from bomi_ai_chat.turn_timer import current_stage

logger = logging.getLogger(__name__)

# LLM 클라이언트를 지연 생성한다. import 시점에 만들면 API 키가 없는 환경에서
# 모듈을 불러오는 것만으로 실패한다.
_LLM = None


def _llm():
    global _LLM
    if _LLM is None:
        from bomi_ai_chat.llm.client import LLMClient

        _LLM = LLMClient()
    return _LLM


def set_llm(client) -> None:
    """LLM 클라이언트를 교체한다. 테스트와 부트스트랩에서 쓴다."""
    global _LLM
    _LLM = client


# 계약 API 클라이언트도 같은 이유로 지연 생성한다.
_ONBOARDING_CLIENT: Any = None
_CLARIFICATION_CLIENT: Any = None


def _onboarding_client():
    global _ONBOARDING_CLIENT
    if _ONBOARDING_CLIENT is None:
        _ONBOARDING_CLIENT = BackendOnboardingClient()
    return _ONBOARDING_CLIENT


def _clarification_client():
    global _CLARIFICATION_CLIENT
    if _CLARIFICATION_CLIENT is None:
        _CLARIFICATION_CLIENT = BackendClarificationClient()
    return _CLARIFICATION_CLIENT


def set_contract_clients(onboarding=None, clarification=None) -> None:
    """계약 API 클라이언트를 교체한다. 테스트와 부트스트랩에서 쓴다."""
    global _ONBOARDING_CLIENT, _CLARIFICATION_CLIENT
    _ONBOARDING_CLIENT = onboarding
    _CLARIFICATION_CLIENT = clarification


def _timed_generate(prompt: str) -> str:
    """대화 그래프의 모든 생성 호출을 한 단계명으로 계측한다."""
    with current_stage("llm"):
        return _llm().generate(prompt)


# 네트워크가 죽었을 때 내놓을 말.
#
# 왜 침묵이 아닌가
#   어르신은 방금 말을 걸었다. 아무 반응이 없으면 고장 난 기계다. 모른다고 말하는
#   것과 반응하지 않는 것은 전혀 다르다.
_FALLBACK_RESPONSE = "죄송해요, 지금 잘 못 들었어요. 다시 한 번 말씀해 주시겠어요?"


def _generate(state: ConvState, *, fallback: str = _FALLBACK_RESPONSE) -> str:
    """이 턴의 '유일한' 생성 호출.

    무엇을 하는가
        프롬프트를 조립해 LLM 을 한 번 부른다. 개방형 핸들러들이 공유한다.

    왜 핸들러마다 따로 두지 않는가
        턴당 생성 호출 1회가 예산이다 (CLAUDE.md §16). 핸들러마다 호출 코드를
        복사하면 언젠가 두 번 부르는 핸들러가 생기고, 그 순간 지연 예산이 무너진다.
        한 곳에 두면 "이 함수가 한 턴에 한 번" 이라는 규칙을 눈으로 확인할 수 있다.

    무엇을 호출하는가
        prompts.build_prompt(순수 함수), 그다음 llm/client.py.

    인자
        fallback: 생성이 실패했을 때 대신 내놓을 문장. 기본값은 일반적인
            "다시 한 번 말씀해 주시겠어요?" 지만, 정서 턴처럼 그 문장이 오히려
            상처가 되는 곳은 핸들러가 자기 폴백을 넘긴다(S15P11E102-253).

    주의사항
        - 생성 실패에 예외를 올리지 않는다. 어르신 입장에서 예외는 그냥 대답 없는
          로봇이다. 되묻는 문장으로 저하시킨다.
        - ★ build_prompt 호출도 이 try 안에 있다 (S15P11E102-253 이전에는 밖에
          있었다). 템플릿 파일이 없으면 load_template 이 FileNotFoundError 를
          던지는데, 그게 이 함수를 그대로 뚫고 나가면 핸들러가 예외로 죽는다.
          프롬프트를 못 만든 것도 결국 "이번 턴에 말할 것을 못 만들었다"는
          점에서 생성 실패와 같은 사건이므로, 같은 우산 아래 둔다.
    """
    try:
        prompt = build_prompt(
            state.get("ctx") or {},
            state.get("intent") or "companion",
            state.get("user_input", ""),
            terse=bool(state.get("terse")),
            ctx_is_cached=bool(state.get("ctx_is_cached")),
            speech_origin=state.get("speech_origin", ""),
            recent_phrasings=state.get("recent_phrasings"),
            is_medical=bool(state.get("is_medical_query")),
            retrieval_status=state.get("retrieval_status"),
        )
        if state.get("closing_turn"):
            prompt += (
                "\n\n이번 답변은 대화의 마지막 답변입니다. 새로운 질문을 하지 말고, "
                "사용자의 말을 짧게 받아준 뒤 편히 쉬시라는 마무리 문장으로 끝내세요."
            )
        # 참고 자료가 실제로 이 프롬프트에 실렸는지 확인할 방법이 없었다 —
        # context_read 가 문서를 찾아도, 그게 build_prompt 를 거쳐 실제로
        # "참고 자료" 섹션으로 들어갔는지는 지금까지 아무 데도 안 남았다.
        # 답변이 근거 없이 나온 건지(문서가 비었거나 안 실렸는지) 여기서
        # 바로 구분할 수 있어야 한다(S15P11E102-311 관련 실측 진단).
        logger.debug(
            "generating intent=%s documents=%d reference_material_in_prompt=%s",
            state.get("intent"),
            len((state.get("ctx") or {}).get("documents") or []),
            "참고 자료" in prompt,
        )
        return _timed_generate(prompt)
    except Exception:  # noqa: BLE001 - 생성 실패가 턴을 죽이면 안 된다
        logger.warning("generation failed; falling back to a clarifying reply", exc_info=True)
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# 개방형 핸들러
# ─────────────────────────────────────────────────────────────────────────────


def handle_info(state: ConvState) -> dict:
    """사실 질문에 답한다. 필요하면 검색된 문서를 쓴다.

    무엇을 하는가
        ctx(프로필, 오늘 상태, 검색된 문서)로 프롬프트를 만들고, 이 턴의 유일한
        생성 호출을 한다.

    누가 호출하는가   build.py, intent "info".
    무엇을 호출하는가  prompts.build_prompt, LLM API.
    반환값            {"response": str}

    주의사항
        - 지남력 질문("오늘 며칠이야?")이 여기로 오고, 가장 빈번한 질문 유형이다.
          한 시간에 열 번째여도 '매번 따뜻하게' 답해야 한다. 반복 정보가 프롬프트에
          닿게 하지 않는다. 대신 추세 보고용으로 로그에 남긴다 (CLAUDE.md §8).
        - 날씨와 병원 질문은 API 호출이고 RAG 가 아니다. 긴 산문(복지제도, FAQ)만
          벡터 저장소에서 온다.
        - 한두 문장으로 답한다. 정확한 세 문단 답변은 여기서는 실패다.
    """
    return {"response": _generate(state)}


def handle_companion(state: ConvState) -> dict:
    """안부, 잡담, 회상 — 정서의 핵심 루프.

    무엇을 하는가
        선호와 검색된 기억을 써서 '이어짐'이 느껴지는 말을 한다.
        "무릎은 좀 어떠세요?", "그 여행 얘기 다시 해주세요".

    왜 가장 중요한 핸들러인가
        이 제품이 다루는 첫 번째 문제가 외로움이다. 특히 회상은 기분과 인지에 실제로
        치료 효과가 있어서, 옛 이야기를 끌어내고 따라가는 것은 시간 메꾸기가 아니라
        기능이다.

    누가 호출하는가  build.py, intent "companion". 침묵 사다리의 모든 프로브도 여기로.
    반환값          {"response": str}

    주의사항
        - 회피 목록은 절대적이다. 돌아가신 배우자를 살아있는 것처럼 언급하는 것은 이
          시스템이 낼 수 있는 최악의 실패 중 하나다. 프롬프트에 '정보'가 아니라
          '금지'로 넘긴다. 사실로 주면 모델은 기꺼이 활용한다 (CLAUDE.md §16 3단계).
        - 침묵 사다리 프로브가 여기로 오는 것이 정확히 맞다. "점심 드셨어요?"는
          말벗이자 생존 확인이며, 감시처럼 들려서는 안 된다 (CLAUDE.md §10).
        - 표현을 바꾼다. 최근에 쓴 표현을 넘기고 다르게 말하라고 지시하지 않으면,
          같은 권유가 3일 연속 글자 하나까지 똑같이 나온다.
    """
    return {"response": _generate(state)}


def handle_schedule(state: ConvState) -> dict:
    """복약·일정 알림, 조회, 완료 처리.

    무엇을 하는가
        ctx 에서 오늘 일정을 읽어 해당 항목을 말하고, 어르신이 확인하면
        ("약 먹었어") 완료로 기록한다.

    왜 완료 처리가 게이트에 중요한가
        항목을 완료로 표시하는 것이 게이트 1이 그 항목의 대기 중 알림을 폐기할 수 있게
        해준다. 이게 없으면 8시 55분에 이미 약을 먹었는데도 9시 알림이 나간다
        (gate.is_still_valid 참고).

    누가 호출하는가  build.py, intent "schedule".
    반환값          {"response": str}

    주의사항
        - 복약 변경을 절대 그대로 기록하지 않는다. "이제 아침 약 안 먹어"는 확인을
          위한 fact_candidate 가 되며, 조용한 스케줄 수정이 되어서는 안 된다.
          ASR 오인식이 복약 스케줄을 지울 수 있어서는 안 된다 (CLAUDE.md §8).
        - 용량을 계산하지 않고 의학적 결정을 하지 않는다. 기록된 것을 말할 뿐이고,
          그 밖의 것은 사람에게 넘긴다.
        - 세 가지가 예정돼 있어도 한 발화에 한 항목만.
    """
    senior_id = state.get("senior_id") or ""
    text = state.get("user_input", "")

    # 어르신이 완료를 알린 턴인가.
    #
    # 이 판정이 게이트 1 무효화의 유일한 입력이다. 여기서 놓치면 이미 먹은 약을
    # 9시에 또 알린다. 반대로 과하게 잡으면 안 먹은 약을 먹었다고 기록한다 —
    # 그래서 '완료 표현'과 '부정'을 함께 본다.
    if senior_id and _is_completion_report(text):
        slot_key = _resolve_slot_key(state)
        if slot_key:
            proposal_store.mark_slot_completed(senior_id, slot_key)
            logger.info("schedule slot marked complete: %s", slot_key)

    return {"response": _generate(state)}


# 완료를 알리는 표현. 부정이 붙으면 완료가 아니다.
#
# ★ 이 목록은 최소한이고, 실사용 발화로 넓혀야 한다. 넓힐 때는 '부정' 쪽을 먼저
#   확인할 것 — "약 안 먹었어"를 완료로 잡으면 어르신이 약을 거른 채 알림이 사라진다.
#   그건 조용한 안전 실패다.
_COMPLETION_MARKERS = ("먹었", "복용했", "챙겨 먹", "다 먹", "마셨")
_NEGATIONS = ("안 ", "안먹", "못 ", "못먹", "아직", "않았")


def _is_completion_report(text: str) -> bool:
    """"약 먹었어"인가, "약 안 먹었어"인가.

    부정을 먼저 본다. "안 먹었어"에도 "먹었"이 들어 있으므로, 완료 표현만 찾으면
    정반대로 판정한다.
    """
    if not text:
        return False
    if any(negation in text for negation in _NEGATIONS):
        return False
    return any(marker in text for marker in _COMPLETION_MARKERS)


def _resolve_slot_key(state: ConvState) -> str | None:
    """어떤 슬롯이 완료됐는가.

    능동 턴이면 이긴 제안이 자기 슬롯 키를 들고 온다. 어르신이 먼저 말한 턴이면
    가장 최근에 제안된 스케줄 슬롯을 쓴다 — 9시 알림이 큐에 있는데 8시 55분에
    "약 먹었어"라고 하는 것이 정확히 이 경우다.

    슬롯을 특정하지 못하면 None 을 돌려주고 아무것도 표시하지 않는다.
    엉뚱한 슬롯을 완료로 찍는 것보다 알림이 한 번 더 나가는 편이 낫다.
    """
    own = (state.get("proposal_meta") or {}).get("slot_key")
    if own:
        return str(own)

    senior_id = state.get("senior_id") or ""
    if not senior_id:
        return None

    for proposal in reversed(proposal_store.pending(senior_id)):
        slot_key = (proposal.get("meta") or {}).get("slot_key")
        if proposal.get("intent") == "schedule" and slot_key:
            return str(slot_key)
    return None


def handle_emotional(state: ConvState) -> dict:
    """듣는다. 그리고 훨씬 나중에, 공유해도 되는지 묻는다. 답이 오면 그 답을 판정한다.

    무엇을 하는가
        세 갈래다.
          1. 방금 로봇이 던진 동의 질문에 대한 답이 와 있으면(pending_consent)
             그 답을 규칙으로 판정하고, GRANTED 일 때만 outbox 에 T3 를 남긴다.
          2. 지금 이 턴이 그 동의 질문을 '던지는' 능동 턴이면(_is_t3_consent_turn)
             제안의 seed 를 그대로 말하고, pending_consent 를 새로 연다.
          3. 그 외에는 평범한 정서 발화다. 봉인 표지가 있으면 대화를 봉인하고,
             없으면 신호를 하나 남긴다(localstore.emotion). 언제 실제로 질문을
             올릴지는 jobs.ticks.consent_tick 이 누적치를 보고 정한다 — 여기서는
             큐잉하지 않는다(S15P11E102-253, 263 에서 바뀐 부분).

    왜 이 '지연'이 설계의 핵심인가
        속마음을 꺼내는 순간 "아드님께 알려드릴까요?"로 끊는 것은 최악의 대응이다.
        말벗을 문장 중간에 감시 장치로 바꿔버리고, 어르신은 더 이상 털어놓지 않는다.
        그래서 로봇은 지금 듣고, 나중에 묻는다 (CLAUDE.md §9).

    누가 호출하는가  build.py, intent "emotional".
    반환값          {"response": str, "pending_consent": dict|None}

    주의사항
        - 자해는 이 핸들러에 절대 도달하지 않는다. 트리아지가 먼저 잡아 T1 으로
          에스컬레이션하며 동의를 무시한다. 여기서 상담 로직을 쓰고 있다면 멈춘다.
          그건 사람의 몫이다.
        - T3 는 동의와 guardian_sharing_consent_status 둘 다 필요하다. 후자는
          서버가 outbox 전송 시점에 다시 확인한다(notify/backend_notifier.py) —
          로봇은 '언제 여쭤볼지'만 정한다. T4 자료(일상 푸념, 회상, "우리끼리
          얘기")는 로봇을 아예 떠나지 않으며, 어르신이 그것을 믿을 수 있어야
          T3 가 작동한다.
        - 갈래 1·2 는 둘 다 LLM 을 부르지 않는다(완료 조건). 질문은 이미 정해진
          문장을 그대로 말하고, 답은 규칙(contract_dialogue.read_affirmation)으로
          판정한다 — "동의한 것으로 보인다"를 재현 불가능한 채로 남기지 않는다
          (CLAUDE.md §8, §16).
    """
    pending_consent = state.get("pending_consent")
    if pending_consent:
        return _resolve_consent_answer(state, pending_consent)

    if _is_t3_consent_turn(state):
        return _speak_consent_question(state)

    senior_id = state.get("senior_id") or ""
    conversation_id = state.get("conversation_id") or ""
    text = state.get("user_input") or ""

    if senior_id and _contains_seal_marker(text):
        # 봉인은 대화 단위다. conversation_id 가 없으면(대화 경계 판정 전의
        # 첫 턴 등) emotion.mark_sealed 가 조용히 아무것도 하지 않는다 —
        # 무엇을 봉인하는지 정의되지 않았기 때문이다(emotion.py 참고).
        emotion.mark_sealed(senior_id, conversation_id)
        logger.info("conversation sealed by the senior's own words; it will not "
                    "count toward a T3 consent question")
    elif senior_id:
        emotion.record_signal(senior_id, conversation_id)

    return {"response": _generate(state, fallback=_EMOTIONAL_FALLBACK)}


# 정서 턴 전용 폴백. 일반 폴백("다시 한 번 말씀해 주시겠어요?")은 방금 마음을
# 꺼낸 사람에게는 서비스 오류처럼 들린다 — 최악의 응답이다(S15P11E102-253).
_EMOTIONAL_FALLBACK = "곁에서 듣고 있어요. 제가 잠깐 놓쳤어요, 다시 한 번 말씀해 주시겠어요?"

# 큐에 들어간 동의 질문을 알아보는 표식. 제안의 origin 에 실린다.
_T3_CONSENT_MARKER = "t3_consent"

# origin 에서 request_id 를 꺼내는 패턴. jobs.ticks.consent_tick 이 만드는
# origin 의 모양("t3_consent:<id>: ...")과 반드시 같이 바뀌어야 한다.
_T3_CONSENT_ORIGIN_RE = re.compile(rf"^{re.escape(_T3_CONSENT_MARKER)}:(\d+):")

# T4 봉인 표지. 이 발화가 나오면 이 대화는 다시는 동의 질문의 재료가 되지 않는다.
_SEAL_MARKERS = policy.T4_SEAL_MARKERS

# 동의 질문의 답을 못 알아들었을 때. 예/아니오 둘 다 아니라는 뜻이지, 거절이 아니다.
_CONSENT_RECONFIRM = (
    "제가 잘 못 들었어요. 가족분께 전해드려도 괜찮으면 '네', 아니면 '아니요'라고 "
    "한 번만 말씀해 주시겠어요?"
)
_CONSENT_GRANTED_REPLY = "네, 가족분께 잘 전해드릴게요."
_CONSENT_DECLINED_REPLY = "네, 알겠어요. 저만 알고 있을게요."


def _is_t3_consent_turn(state: ConvState) -> bool:
    """지금 턴이 '동의를 여쭤보는' 능동 턴인가.

    게이트가 이긴 제안의 origin 을 speech_origin 으로 실어 준다. 그 값으로 판단한다.
    """
    return _T3_CONSENT_MARKER in (state.get("speech_origin") or "")


def _contains_seal_marker(text: str) -> bool:
    """"우리끼리 얘기" 류 표현이 이 발화에 섞여 있는가."""
    return any(marker in text for marker in _SEAL_MARKERS)


def _speak_consent_question(state: ConvState) -> dict:
    """T3 동의 질문을 '그대로' 말하고, 다음 턴이 답을 알아볼 수 있게 연다.

    ★ LLM 을 부르지 않는다  (완료 조건)
        온보딩(handle_onboarding)이 계약 문장을 그대로 말하는 것과 같은 이유다.
        나중에 "어르신이 정말 동의했는가"를 물었을 때, 실제로 무엇을 물었는지가
        매번 달라지면 안 된다. 이긴 제안의 seed 가 이미 최종 문장이고
        (jobs.ticks.consent_tick 이 만든다), 다시 쓰면 그 보장이 깨진다.

    누가 호출하는가  handle_emotional, _is_t3_consent_turn 이 True 일 때.
    반환값  {"response": str, "pending_consent": dict}

    주의사항
        origin 에 request_id 가 없으면(형식이 어긋났거나 누군가 손으로 만든
        제안이면) 질문은 그대로 말하되 pending_consent 를 열지 않는다. 열어도
        답을 어느 요청에 연결할지 모르므로, 여는 것 자체가 거짓 약속이다.
    """
    request_id = _extract_consent_request_id(state.get("speech_origin") or "")
    response = state.get("user_input") or ""
    out: dict = {"response": response}

    if request_id is None:
        logger.warning("t3 consent turn has no request id in speech_origin=%r; "
                       "the senior's answer cannot be resolved later",
                       state.get("speech_origin"))
        return out

    out["pending_consent"] = {"request_id": request_id, "asked_at": clock.now()}
    return out


def _extract_consent_request_id(origin: str) -> int | None:
    """origin 문자열에서 동의 요청 id 를 꺼낸다. 못 찾으면 None."""
    match = _T3_CONSENT_ORIGIN_RE.match(origin)
    return int(match.group(1)) if match else None


def _resolve_consent_answer(state: ConvState, pending: dict) -> dict:
    """어르신의 "응"/"아니"를 규칙으로 판정하고, GRANTED 일 때만 outbox 에 남긴다.

    ★ 이 판정만은 LLM 에게 맡기지 않는다  (완료 조건)
        contract_dialogue._resolve_confirmation 과 같은 원칙이다. "동의한 것으로
        보인다"는 재현되지 않는 근거다 — 나중에 "정말 동의했는가"를 물었을 때
        답할 수 있어야 한다.

    세 갈래.
        긍정   GRANTED 로 확정하고 outbox 에 T3 한 건을 남긴다. 발화 원문은
               싣지 않는다 — 보호자에게 필요한 것은 "가서 봐 주세요"이지 원문이
               아니고, 원문을 실으면 T4 가 T1/T3 알림에 묻어 나가는 경로가 생긴다
               (notify/backend_notifier.py 참고).
        부정   DECLINED 로 확정한다. 아무것도 나가지 않고, pending_consent 를
               비우므로 다시 묻지 않는다.
        애매   확정하지 않는다. pending_consent 를 그대로 두고 한 번 더 확인한다
               ("글쎄"를 거절로 접으면 안 되는 이유는 contract_dialogue 와 같다).

    누가 호출하는가  handle_emotional, pending_consent 가 있을 때.
    반환값  {"response": str, "pending_consent": dict|None}
    """
    verdict = contract_dialogue.read_affirmation(state.get("user_input") or "")
    if verdict is None:
        return {"response": _CONSENT_RECONFIRM, "pending_consent": pending}

    request_id = pending.get("request_id")
    if request_id is not None:
        consent_store.resolve(request_id, "GRANTED" if verdict else "DECLINED")

    if verdict:
        outbox.enqueue("T3", {
            "reason": "emotional_disclosure",
            "request_id": request_id,
        })
        response = _CONSENT_GRANTED_REPLY
    else:
        response = _CONSENT_DECLINED_REPLY

    # None 을 명시적으로 돌려준다. 안 그러면 이 키에는 reducer 가 없으므로
    # (state.py 참고) 다음 턴까지 이번 요청이 '아직 대기 중'인 것처럼 남는다.
    return {"response": response, "pending_consent": None}


def handle_greeting(state: ConvState) -> dict:
    """백엔드가 정한 인사 문구를 발화로 옮긴다. 다시 고르지 않는다.

    ★ 이 핸들러가 얇은 것이 의도다  (2026-08-01 재정의, CLAUDE.md §11)

        초안에서는 이 핸들러가 골랐다 — 외출이면 날씨·미복용 약·오늘 일정 중 하나,
        귀가면 수분·안부·휴식 중 하나. 합의된 구조는 다르다. **그 선택은 백엔드가 한다.**

        이유는 데이터의 위치다. "미복용 약이 있는가", "오늘 일정이 있는가", "동의를
        받았는가"는 전부 백엔드만 아는 사실이다. 로봇이 다시 조회해 다시 고르면 같은
        우선순위 규칙이 두 곳에 생기고, 두 곳은 갈라진다. 그러면 "왜 로봇이 우산을
        말하지 않았는가"에 답할 곳이 두 곳이 된다.

        그래서 로봇의 몫은 하나다. 받은 문구를 §14 를 지켜 말하기.

    무엇을 하는가
        backend_command 가 넣어준 user_input(= 최종 문구)을 response 로 옮긴다.

    왜 그래도 노드가 필요한가
        모든 발화가 같은 파이프라인을 지나야 하기 때문이다. 여기를 건너뛰고 정제기로
        직행하는 지름길을 만들면, 그 지름길로 다른 것들이 따라 들어온다.
        이 노드가 "백엔드 문구가 로봇 발화가 되는 유일한 지점"이다.

    누가 호출하는가
        build.py, intent "greeting". backend_command 경로에서 온다.

    반환값
        {"response": str}. 문구가 없으면 빈 문자열 — 정제기가 그것을 침묵으로 만든다.

    주의사항
        - '하나만'은 여전히 유효하다. 다만 그 판정이 백엔드로 갔다. 백엔드가 세 가지를
          한 문장에 담아 보내면 여기서 막지 않는다 — 그건 226 의 완료 조건이다.
          정제기의 MAX_SENTENCES 가 마지막 방어선이다.
        - terse 는 백엔드가 지정한다(command.terse). quiet hours 판정도 백엔드 몫이다.
        - 이동을 기다리지 않는다. 음성은 방을 건너 들리고, 인사의 TTL 은 약 45초다.
          로봇이 현관에 도착했는지 여기서 확인하지 않는다 (CLAUDE.md §11).
    """
    text = (state.get("user_input") or "").strip()
    if not text:
        # 여기 도달했는데 문구가 없다는 것은 backend_command 가 빈 명령을 통과시켰거나
        # 누군가 intent="greeting" 을 직접 넣었다는 뜻이다. 조용히 침묵으로 끝낸다 —
        # 무음 TTS 를 재생하는 것보다 낫다.
        logger.warning("handle_greeting has no text to speak; falling through to silence")
        return {"response": ""}

    return {"response": text}


# ─────────────────────────────────────────────────────────────────────────────
# 계약 주도형 핸들러  (CLAUDE.md §12)
#
# 정해진 슬롯을 채운다. 모델에게 자유를 거의 주지 않는다. 수집 중인 단 하나의 필드,
# 허용되는 답변 형태를 명시하고, 그 외에는 아무것도 묻지 말라고 지시한다.
# 사후에 고치는 대신 여기서 제약한다. 백엔드는 계약에 맞지 않는 것을 어차피 거부한다.
# ─────────────────────────────────────────────────────────────────────────────


def handle_onboarding(state: ConvState) -> dict:
    """공용 질문 세트를 음성 대화로 진행한다.

    무엇을 하는가
        두 방향이 한 함수에 있다.
          대기 중인 질문이 없으면  -> 백엔드에서 다음 질문 하나를 받아 그대로 말한다.
          대기 중인 질문이 있으면  -> 어르신의 말을 그 질문의 답으로 처리한다.

    ★ robotPrompt 를 '그대로' 말한다. 다시 쓰지 않는다.
        LLM 으로 다듬으면 자연스러워지지만, 그 문장은 앱이 화면에 보여주는 문장과
        달라진다. 동의 문구라면 그것은 계약 위반이다 — 어르신이 들은 동의와 기록된
        동의가 다른 것이 된다. 계약 주도형 대화가 자유를 뺏는 흐름인 이유가 이것이다
        (CLAUDE.md §12).

    왜 앱과 계약을 공유하는가
        앱과 로봇은 같은 질문 코드, 필수 필드, 동의 게이트, JSON 스키마, 최종 매핑을
        쓴다. 표면만 다르다. 폼 컨트롤이냐 음성 프롬프트냐. 그래서 앱에서 시작한 세션을
        음성으로 마칠 수 있다.

    누가 호출하는가  build.py, intent "onboarding".
    반환값          {"response": str, "pending_contract": dict|None}

    주의사항
        - 한 번에 한 필드. 서버가 하나만 내려주므로 로봇이 큐를 들지 않는다.
        - 동의 질문이 이후 질문의 관문이다. 순서는 서버가 정한다.
        - 민감한 답변은 값이 명확해도 전체를 읽어주고 명시적으로 확인받는다.
        - 백엔드에 못 닿으면 **아무것도 하지 않는다.** 캐시된 질문을 되풀이하면 이미
          답한 것을 또 묻고, 옛 문구로 동의를 받게 된다.
    """
    pending = state.get("pending_contract")
    if pending and pending.get("kind") == "onboarding":
        return _answer_onboarding(state, pending)
    return _ask_next_onboarding_question(state)


def _ask_next_onboarding_question(state: ConvState) -> dict:
    """세션을 확보하고 다음 질문 하나를 말한다."""
    senior_id = state.get("senior_id") or ""
    client = _onboarding_client()

    try:
        session = client.start_or_resume(senior_id, state.get("robot_id") or "")
        if not session:
            return _contract_silence("onboarding session was not returned")
        question = client.next_question(session["sessionId"])
    except BackendUnavailable as error:
        return _contract_silence(f"onboarding unavailable ({error})")

    if question is None:
        # 물을 것이 없다. 온보딩이 끝났거나 지금 물을 수 있는 질문이 없다.
        return {"response": "", "pending_contract": None}

    return {
        # 계약의 문장 그대로. 위 docstring 참고.
        "response": question["robotPrompt"],
        "pending_contract": {
            "kind": "onboarding",
            "session_id": session["sessionId"],
            "question_code": question["questionCode"],
            "fields": question.get("requiredFields") or [],
            "stage": "ask",
            "sensitive": bool(question.get("sensitive")),
            "requires_confirmation": bool(question.get("requiresConfirmation")),
            "fact_type": question["questionCode"],
            # 다시 물어야 할 때 쓴다. 계약의 문장이 있는데 새로 지어내면, 같은 질문이
            # 두 번째에는 다른 문장으로 나간다.
            "robot_prompt": question["robotPrompt"],
        },
    }


def _is_consent_question(pending: dict) -> bool:
    """예/아니오 하나로 끝나는 동의 질문인가.

    계약에서 동의 질문은 `consentStatus` 하나만 요구한다. 필드 목록으로 판정하므로
    질문 코드를 로봇에 하드코딩하지 않는다 — 계약에 동의가 추가돼도 그대로 동작한다.
    """
    return (pending.get("fields") or []) == ["consentStatus"]


def _answer_onboarding(state: ConvState, pending: dict) -> dict:
    """어르신의 말을 대기 중인 온보딩 질문의 답으로 처리한다."""
    utterance = (state.get("user_input") or "").strip()
    client = _onboarding_client()

    if pending.get("stage") == "confirm":
        return _resolve_confirmation(
            state, pending,
            submit=lambda value, confirmed: client.submit_answer(
                pending["session_id"], pending["question_code"], value,
                confirmed=confirmed,
                conversation_id=state.get("conversation_id"),
            ),
        )

    value = _extract_value(pending.get("fields") or [], utterance)
    if value is None:
        # 무슨 말인지 못 알아들었다. 확정하지 않고 같은 질문을 한 번 더.
        return {"response": _REASK, "pending_contract": pending}

    # ★ 동의 질문은 '그 답이 곧 명시적 확인'이다.
    #
    #   동의 질문은 이미 명확한 예/아니오 질문이고, 어르신은 그것을 듣고 답했다.
    #   여기서 값을 복창하면 로봇이 "GRANTED. 이렇게 맞을까요?"라고 말하게 된다 —
    #   내부 코드값을 어르신에게 읽어주는 것이고, 확인에 아무것도 보태지 않는다
    #   (CLAUDE.md §17.9: 내부 기제를 절대 말하지 않는다).
    #
    #   애매한 답변은 이미 _extract_value 에서 걸러져 여기 오지 않는다.
    confirmed = _is_consent_question(pending)

    try:
        result = client.submit_answer(
            pending["session_id"], pending["question_code"], value,
            confirmed=confirmed,
            conversation_id=state.get("conversation_id"),
        )
    except BackendUnavailable as error:
        return _contract_silence(f"onboarding unavailable ({error})", pending=pending)

    return _apply_outcome(state, pending, result, value)


def handle_clarification(state: ConvState) -> dict:
    """활성 fact_candidate 하나의 필드 하나만 다시 묻는다.

    무엇을 하는가
        대기 중인 재질의가 없으면 백엔드에서 활성 후보 하나를 받아 그 '한 필드'를
        사람의 질문으로 바꿔 묻는다. 대기 중이면 어르신의 말을 그 답으로 처리한다.

    왜 이것이 존재하는가
        발화에서 추출된 사실을 그대로 기록해서는 안 되기 때문이다. 후보 흐름이 그
        안전장치다. confirmed_value 만 최종 반영되고, 나머지는 전부 대기한다
        (CLAUDE.md §8).

    ★ 여기서는 LLM 을 쓴다. 온보딩과 반대다.
        온보딩은 말할 문장이 계약에 있지만, 재질의는 `"dose"` 라는 '필드명'만 온다.
        그것을 소리내어 읽으면 돌봄 로봇이 아니라 서식이 된다. 짧은 우리말 질문으로
        바꾸는 것이 로봇의 몫이고, 그래서 이쪽만 생성 호출이 필요하다.

    누가 호출하는가  build.py, intent "clarification".
    반환값          {"response": str, "pending_contract": dict|None}

    주의사항
        - 한 대화에 활성 후보는 정확히 하나다. 서버가 하나만 내려주고, 로봇도 한
          대화에서 두 번째를 꺼내지 않는다 (jobs/ticks.py 의 contract_tick).
        - clarification_reason 이 문구를 결정한다. 특히 낮은 STT 신뢰도는 오류
          메시지가 아니라 평범한 재질문처럼 들려야 한다.
        - 백엔드에 못 닿으면 아무것도 하지 않는다.
    """
    pending = state.get("pending_contract")
    if pending and pending.get("kind") == "clarification":
        return _answer_clarification(state, pending)
    return _ask_clarification(state)


def _ask_clarification(state: ConvState) -> dict:
    """활성 후보 하나를 받아 그 한 필드를 묻는다."""
    senior_id = state.get("senior_id") or ""

    try:
        candidate = _clarification_client().active(senior_id)
    except BackendUnavailable as error:
        return _contract_silence(f"clarification unavailable ({error})")

    if candidate is None:
        return {"response": "", "pending_contract": None}

    fields = candidate.get("missingFields") or []
    reason = candidate.get("clarificationReason") or ""

    if reason == "SENSITIVE_INFORMATION_CONFIRMATION" or not fields:
        # 값은 다 모였고 확인만 남았다. 전체를 그대로 읽어준다.
        value = candidate.get("proposedValue") or {}
        return {
            "response": contract_dialogue.read_back(value),
            "pending_contract": _clarification_pending(candidate, fields, "confirm", value),
        }

    question = _field_question(fields[0], candidate.get("factType") or "", reason)
    return {
        "response": question,
        "pending_contract": _clarification_pending(candidate, fields, "ask", {}),
    }


def _answer_clarification(state: ConvState, pending: dict) -> dict:
    """어르신의 말을 대기 중인 재질의의 답으로 처리한다."""
    client = _clarification_client()

    if pending.get("stage") == "confirm":
        return _resolve_confirmation(
            state, pending,
            submit=lambda value, confirmed: client.answer(
                pending["candidate_id"], value, confirmed=confirmed,
                conversation_id=state.get("conversation_id"),
            ),
        )

    utterance = (state.get("user_input") or "").strip()
    value = _extract_value(pending.get("fields") or [], utterance)
    if value is None:
        return {"response": _REASK, "pending_contract": pending}

    try:
        result = client.answer(
            pending["candidate_id"], value, confirmed=False,
            conversation_id=state.get("conversation_id"),
        )
    except BackendUnavailable as error:
        return _contract_silence(f"clarification unavailable ({error})", pending=pending)

    return _apply_outcome(state, pending, result, value)


# ─────────────────────────────────────────────────────────────────────────────
# 계약 주도형 공통부
# ─────────────────────────────────────────────────────────────────────────────

# 못 알아들었을 때. 오류 메시지처럼 들리지 않아야 한다.
_REASK = "죄송해요, 한 번만 더 말씀해 주시겠어요?"

# 확인 단계에서 얼버무렸을 때. 부정이 아니므로 거절로 기록하지 않고 다시 확인한다.
_RECONFIRM = "제가 잘 못 들었네요. 맞으면 '네'라고 한 번만 말씀해 주세요."

# 생성된 문장이 우리말인지 보는 최소 검사. 한글이 한 글자도 없으면 말하지 않는다.
_HANGUL = re.compile(r"[가-힣]")


def _contract_silence(reason: str, *, pending: dict | None = None) -> dict:
    """계약 대화를 진행하지 않고 조용히 넘어간다.

    ★ 왜 침묵인가 — 다른 경로와 반대되는 결정
        개방형 핸들러는 네트워크가 죽어도 무언가 말한다. 어르신이 말을 걸었는데
        반응이 없으면 고장 난 기계이기 때문이다(_FALLBACK_RESPONSE).

        계약 대화는 반대다. 계약을 서버가 강제하는데 서버에 못 닿으면 계약이 없는
        상태이고, 그 상태로 민감정보를 물으면 안 된다. 온보딩과 재질의는 **미뤄도 되는
        일**이다 — 침묵 사다리나 T1 과 달리, 네트워크가 없을 때가 가장 중요한 순간이
        아니다 (CLAUDE.md §18 의 성능 저하 순서).

        빈 response 는 response_shaper 를 지나 침묵이 된다.
    """
    logger.info("skipping the contract dialogue: %s", reason)
    return {"response": "", "pending_contract": pending}


def _clarification_pending(candidate: dict, fields: list, stage: str, value: dict) -> dict:
    return {
        "kind": "clarification",
        "candidate_id": candidate["factCandidateId"],
        "question_code": candidate.get("factType") or "",
        "fields": fields,
        "stage": stage,
        "value": value,
        "sensitive": candidate.get("riskLevel") in {"SENSITIVE", "HIGH"},
        "requires_confirmation": True,
        "fact_type": candidate.get("factType") or "",
        "reason": candidate.get("clarificationReason") or "",
    }


def _apply_outcome(state: ConvState, pending: dict, result: dict | None,
                   value: dict) -> dict:
    """백엔드가 알려준 다음 행동을 발화로 옮긴다.

    세 가지뿐이다.
        NEEDS_CLARIFICATION  한 필드만 다시 묻는다.
        NEEDS_CONFIRMATION   전체를 읽어주고 명시적 확인을 받는다.
        ACCEPTED             받아들여졌다. 온보딩이면 곧바로 다음 질문으로 넘어간다.

    왜 ACCEPTED 에서 곧바로 다음 질문을 묻는가
        한 턴에 한 질문씩 10분을 기다리면 온보딩이 며칠 걸린다. 대화가 이어지는 동안
        진행하는 것이 자연스럽고, 어르신 입장에서도 한 번에 끝내는 편이 낫다.
        백엔드 호출이 한 턴에 두 번(제출 + 다음 질문) 일어나지만, 둘 다 로컬 네트워크
        왕복이라 생성 호출 하나보다 싸다 (CLAUDE.md §16).
    """
    outcome = (result or {}).get("outcome", "")

    if outcome == "NEEDS_CLARIFICATION":
        fields = result.get("missingFields") or pending.get("fields") or []
        field = fields[0] if fields else ""
        return {
            "response": _field_question(field, pending.get("fact_type") or "",
                                        result.get("clarificationReason") or ""),
            "pending_contract": {**pending, "stage": "ask", "fields": fields},
        }

    if outcome == "NEEDS_CONFIRMATION":
        to_confirm = result.get("valueToConfirm") or value
        return {
            "response": contract_dialogue.read_back(to_confirm),
            "pending_contract": {**pending, "stage": "confirm", "value": to_confirm},
        }

    if outcome in {"ACCEPTED", "CONFIRMED"}:
        if pending.get("kind") == "onboarding":
            # 대화가 이어지는 동안 다음 질문으로 넘어간다.
            return _ask_next_onboarding_question(state)
        return {"response": "네, 알겠어요.", "pending_contract": None}

    logger.warning("unexpected contract outcome %r; ending the exchange", outcome)
    return {"response": "", "pending_contract": None}


def _resolve_confirmation(state: ConvState, pending: dict, *, submit) -> dict:
    """복창한 값에 대한 어르신의 반응을 판정한다.

    ★ 이 판정만은 LLM 에게 맡기지 않는다.
        "동의한 것으로 보인다"는 재현되지 않는 근거다. 나중에 "어르신이 정말
        동의했는가"를 물었을 때 답할 수 있어야 한다 (contract_dialogue.py).

    세 갈래를 서로 다르게 다룬다.
        긍정   confirmed=True 로 제출한다. 여기서만 민감한 값이 확정된다.
        부정   확정하지 않고 처음부터 다시 묻는다. 거절이 아니라 '값이 틀렸다'이다.
        애매   확정도 거절도 아니다. 한 번 더 확인한다.

    애매를 부정으로 접으면 안 되는 이유
        "글쎄"를 거절로 기록하면, 어르신이 거절한 적 없는 항목이 거절로 남고 그에
        딸린 질문들이 영영 안 나온다.
    """
    verdict = contract_dialogue.read_affirmation(state.get("user_input") or "")

    if verdict is None:
        return {"response": _RECONFIRM, "pending_contract": pending}

    if verdict is False:
        # 값이 틀렸다. 처음부터 다시 묻는다.
        return {
            "response": _reask_question(pending),
            "pending_contract": {**pending, "stage": "ask", "value": {}},
        }

    value = pending.get("value") or {}
    try:
        result = submit(value, True)
    except BackendUnavailable as error:
        return _contract_silence(f"contract API unavailable ({error})", pending=pending)

    return _apply_outcome(state, pending, result, value)


def _reask_question(pending: dict) -> str:
    """같은 질문을 다시 묻는다.

    왜 계약의 문장을 다시 쓰는가
        온보딩 질문에는 계약이 정한 문장(robotPrompt)이 있다. 두 번째에 새로 지어내면
        같은 질문이 다른 문장으로 나가고, 동의 문구라면 그것은 계약 위반이다.

        재질의(clarification)에는 계약 문장이 없고 필드명만 있으므로 생성한다.
    """
    prompt = pending.get("robot_prompt")
    if prompt:
        return prompt

    fields = pending.get("fields") or []
    return _field_question(fields[0] if fields else "", pending.get("fact_type") or "", "")


def _field_question(field: str, fact_type: str, reason: str) -> str:
    """필드명 하나를 짧은 우리말 질문으로 바꾼다. 이 턴의 유일한 생성 호출이다.

    주의사항
        생성이 실패해도 예외를 올리지 않는다. 다만 폴백이 필드명을 읽어서는 안 되므로,
        무엇을 묻는지 모르는 채로 되묻는 문장을 쓴다.
    """
    if not field:
        return _REASK

    hint = "잘 못 들어서 한 번 더 여쭙는 상황입니다." \
        if reason == "LOW_RECOGNITION_CONFIDENCE" else ""
    prompt = build_field_question_prompt(field, fact_type=fact_type, hint=hint)

    try:
        question = (_timed_generate(prompt) or "").strip()
    except Exception:  # noqa: BLE001 - 생성 실패가 턴을 죽이면 안 된다
        logger.warning("field question generation failed", exc_info=True)
        return _REASK

    # 모델이 필드명을 그대로 뱉는 경우가 있다. 그건 사람의 말이 아니다.
    if not question or field.lower() in question.lower():
        logger.warning("generated question leaked the field name %r; falling back", field)
        return _REASK

    # ★ 사람의 말처럼 보이지 않으면 말하지 않는다 — 워크스루에서 실제로 잡힌 것
    #
    #   모델이 "{}" 를 돌려준 적이 있고, 그것이 그대로 TTS 로 나갔다. 어르신은
    #   로봇이 무의미한 소리를 내는 것을 들었다. 한글이 한 글자도 없으면 그것은
    #   우리말 질문이 아니다.
    if not _HANGUL.search(question):
        logger.warning("generated question has no Korean text (%r); falling back", question)
        return _REASK
    return question


def _extract_value(fields: list[str], utterance: str) -> dict | None:
    """어르신의 말에서 필요한 필드만 뽑는다. 못 뽑으면 None.

    동의 질문은 LLM 을 쓰지 않는다  ★
        `consentStatus` 하나만 필요한 질문은 예/아니오다. 그것을 모델에게 물으면
        "동의한 것으로 보인다"가 되고, 그 판정은 재현되지 않는다. 규칙으로 읽는다
        (contract_dialogue.read_affirmation).

    나머지는 한 번의 생성 호출로 뽑는다
        턴당 생성 호출 1회가 예산이다 (CLAUDE.md §16).

    반환값
        {"dose": 1} 처럼 채워진 필드만. 아무것도 못 뽑았으면 None.
        빈 dict 를 돌려주지 않는 이유는, 호출부가 '못 알아들었다'와 '값이 비었다'를
        구분해야 하기 때문이다.
    """
    if not utterance:
        return None

    if fields == ["consentStatus"]:
        verdict = contract_dialogue.read_affirmation(utterance)
        if verdict is None:
            return None
        return {"consentStatus": "GRANTED" if verdict else "DENIED"}

    try:
        raw = _timed_generate(build_extraction_prompt(fields, utterance))
    except Exception:  # noqa: BLE001 - 추출 실패가 턴을 죽이면 안 된다
        logger.warning("answer extraction failed", exc_info=True)
        return None

    value = _parse_json_object(raw)
    if not value:
        return None

    # 계약이 요구하지 않은 필드는 버린다. 모델이 만들어낸 값이 백엔드로 새어나가면,
    # 어르신이 말한 적 없는 사실이 후보가 된다.
    filtered = {key: item for key, item in value.items() if key in fields}
    return filtered or None


def _parse_json_object(raw: str | None) -> dict:
    """모델 출력에서 JSON 객체를 꺼낸다. 실패하면 빈 dict.

    코드 블록으로 감싸 오는 경우가 흔해서 중괄호 범위만 잘라 쓴다.
    """
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start:end + 1])
    except ValueError:
        logger.warning("extraction did not return JSON; treating it as nothing heard")
        return {}
    return parsed if isinstance(parsed, dict) else {}
