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
    개방형:     info, companion, schedule, emotional, greeting
                LLM 이 자연스럽게 표현할 여지가 있다.
    계약 주도형: onboarding, clarification
                백엔드가 강제하는 계약이 정의한 고정 슬롯을 채운다. LLM 에게 자유를
                거의 주지 않는다. 한 필드, 한 질문, 그 외에는 아무것도 (CLAUDE.md §12).

기존 모듈에 위임한다 (재구현 금지)
    이 패키지에는 이미 검증된 클라이언트들이 있다. 핸들러는 얇아야 한다.
        일반 대화        -> llm/client.py
        의료 조회        -> llm/medical_flow.py  (function calling)
        날씨             -> weather/client.py
        병원·약국·의약품  -> db/medical_repository.py  (지오/정확 조회, RAG 아님)
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

import logging

from bomi_ai_chat.localstore import proposals as proposal_store
from bomi_ai_chat.prompts import build_prompt
from bomi_ai_chat.state import ConvState

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


# 네트워크가 죽었을 때 내놓을 말.
#
# 왜 침묵이 아닌가
#   어르신은 방금 말을 걸었다. 아무 반응이 없으면 고장 난 기계다. 모른다고 말하는
#   것과 반응하지 않는 것은 전혀 다르다.
_FALLBACK_RESPONSE = "죄송해요, 지금 잘 못 들었어요. 다시 한 번 말씀해 주시겠어요?"


def _generate(state: ConvState) -> str:
    """이 턴의 '유일한' 생성 호출.

    무엇을 하는가
        프롬프트를 조립해 LLM 을 한 번 부른다. 개방형 핸들러들이 공유한다.

    왜 핸들러마다 따로 두지 않는가
        턴당 생성 호출 1회가 예산이다 (CLAUDE.md §16). 핸들러마다 호출 코드를
        복사하면 언젠가 두 번 부르는 핸들러가 생기고, 그 순간 지연 예산이 무너진다.
        한 곳에 두면 "이 함수가 한 턴에 한 번" 이라는 규칙을 눈으로 확인할 수 있다.

    무엇을 호출하는가
        prompts.build_prompt(순수 함수), 그다음 llm/client.py.

    주의사항
        생성 실패에 예외를 올리지 않는다. 어르신 입장에서 예외는 그냥 대답 없는
        로봇이다. 되묻는 문장으로 저하시킨다.
    """
    prompt = build_prompt(
        state.get("ctx") or {},
        state.get("intent") or "companion",
        state.get("user_input", ""),
        terse=bool(state.get("terse")),
        ctx_is_cached=bool(state.get("ctx_is_cached")),
        speech_origin=state.get("speech_origin", ""),
        recent_phrasings=state.get("recent_phrasings"),
    )

    try:
        return _llm().generate(prompt)
    except Exception:  # noqa: BLE001 - 생성 실패가 턴을 죽이면 안 된다
        logger.warning("generation failed; falling back to a clarifying reply", exc_info=True)
        return _FALLBACK_RESPONSE


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
    """듣는다. 그리고 훨씬 나중에, 공유해도 되는지 묻는다.

    무엇을 하는가
        외로움, 상실, 가족 갈등에 지지적으로 반응하고, T3 동의 질문을 그날의 자연스러운
        시점을 위해 큐에 넣는다.

    왜 이 '지연'이 설계의 핵심인가
        속마음을 꺼내는 순간 "아드님께 알려드릴까요?"로 끊는 것은 최악의 대응이다.
        말벗을 문장 중간에 감시 장치로 바꿔버리고, 어르신은 더 이상 털어놓지 않는다.
        그래서 로봇은 지금 듣고, 나중에 묻는다 (CLAUDE.md §9).

    누가 호출하는가  build.py, intent "emotional".
    반환값          {"response": str}

    주의사항
        - 자해는 이 핸들러에 절대 도달하지 않는다. 트리아지가 먼저 잡아 T1 으로
          에스컬레이션하며 동의를 무시한다. 여기서 상담 로직을 쓰고 있다면 멈춘다.
          그건 사람의 몫이다.
        - T3 는 동의와 guardian_sharing_consent_status 둘 다 필요하다. T4 자료(일상
          푸념, 회상, "우리끼리 얘기")는 로봇을 아예 떠나지 않으며, 어르신이 그것을
          믿을 수 있어야 T3 가 작동한다.
        - LangGraph 의 interrupt / human-in-the-loop 가 이 지연된 질문에 직접 만든
          큐보다 잘 맞는다 (CLAUDE.md §16).
    """
    raise NotImplementedError


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
    """공용 질문 세트를 자연스러운 대화로 진행한다.

    무엇을 하는가
        온보딩 세션의 현재 질문 코드를 받아 그 robotPrompt 를 말하고, 답변을 백엔드용
        으로 정규화한다.

    왜 앱과 계약을 공유하는가
        앱과 로봇은 같은 질문 코드, 필수 필드, 동의 게이트, JSON 스키마, 최종 매핑을
        쓴다. 표면만 다르다. 폼 컨트롤이냐 음성 프롬프트냐. 그래서 앱에서 시작한 세션을
        음성으로 마칠 수 있다.

    누가 호출하는가  build.py, intent "onboarding".
    반환값          {"response": str}

    주의사항
        - 한 번에 한 필드. 협상 불가이며, 계약의 기본값에 명시되어 있다.
        - 동의 질문이 이후 질문의 관문이다(prerequisiteConsent). 건강정보 동의 전에
          복약 질문을 하는 것은 계약 위반이다.
        - 민감한 답변은 값이 명확해도 전체를 읽어주고 명시적으로 확인받아야 한다.
        - 침묵, 주제 변경, "글쎄", "아마도", 불명확한 STT, 또는 '다른' 질문에 대한
          답변은 확인으로 인정하지 않는다.
    """
    raise NotImplementedError


def handle_clarification(state: ConvState) -> dict:
    """활성 fact_candidate 하나의 필드 하나만 다시 묻는다.

    무엇을 하는가
        missing_fields 와 clarification_reason 을 짧은 구어 질문 하나로 바꾸고,
        답변을 백엔드에 넘겨 후보를 갱신한다.

    왜 이것이 존재하는가
        발화에서 추출된 사실을 그대로 기록해서는 안 되기 때문이다. 후보 흐름이 그
        안전장치다. confirmed_value 만 최종 반영되고, 나머지는 전부 대기한다
        (CLAUDE.md §8).

    누가 호출하는가  build.py, intent "clarification".
    반환값          {"response": str}

    주의사항
        - 한 대화에 활성 후보는 정확히 하나다. DB 계약이 그렇게 정하고 있고, 그것을
          강제하는 곳이 그래프다. 보류된 사실 세 개를 한꺼번에 묻는 순간 계약이 깨진다
          (context.classify_intent 참고).
        - missing_fields 에는 '필드명'이 들어 있고 질문 문구가 아니다. 짧은 사람의
          질문으로 바꿔야 하며, 필드명을 소리내어 읽어서는 절대 안 된다.
        - clarification_reason 이 문구를 결정한다. 필드 누락, 모호한 값, 낮은 STT
          신뢰도, 기존 데이터와의 충돌, 민감정보 확인. 특히 낮은 STT 신뢰도는
          오류 메시지가 아니라 평범한 재질문처럼 들려야 한다.
    """
    raise NotImplementedError
