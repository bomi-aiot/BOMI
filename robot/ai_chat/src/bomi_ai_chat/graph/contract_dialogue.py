"""계약 주도형 대화의 '결정적'인 부분 — 확인인가, 아닌가.

왜 이것만 LLM 을 쓰지 않는가  ★ 이 파일의 존재 이유
    같은 턴 안에서도 두 가지 판정이 섞여 있다.

        "어르신이 뭐라고 답했는가"      -> 값 추출. 모델이 잘한다
        "어르신이 '확인'한 것이 맞는가"  -> 규칙. 모델에게 맡기지 않는다

    두 번째를 모델에게 맡기면 "동의한 것으로 보인다"가 되고, 그 판정 근거는 재현되지
    않는다. 나중에 "어르신이 정말 동의했는가"를 물었을 때 답할 수 있어야 한다.
    모델은 그 질문에 답해주지 않는다. 이 파일의 함수들은 답한다.

확인으로 인정하지 않는 것 (CLAUDE.md §8)
    침묵, 주제 변경, "글쎄", "아마도", 불명확한 STT, **다른 질문에 대한 답변**.

    마지막 항목이 특히 중요하다. 로봇이 복약 용량을 물었는데 어르신이 "오늘 날씨
    좋네"라고 답하면, 그것은 용량에 대한 확인이 아니다. 그런데 발화 자체는 멀쩡하므로
    "답변이 있었다"로 처리하기 쉽다.

이 판정은 1차 방어다
    백엔드도 같은 것을 검사한다(S15P11E102-227). 두 겹인 이유는 한쪽이 다른 쪽을
    믿지 않기 위해서다 — 로봇 버전이 바뀌어도 서버가 막고, 서버가 못 본 맥락은
    로봇이 안다.

참고
    CLAUDE.md §8 (확인으로 인정하지 않는 것), §12 (계약 주도형 대화)
    policy.CONTRACT_AFFIRMATIONS / CONTRACT_NEGATIONS / CONTRACT_NON_COMMITTAL
"""

from __future__ import annotations

import logging
import re

from bomi_ai_chat import policy

logger = logging.getLogger(__name__)

# 공백과 구두점으로 낱말을 자른다. 조사·어미는 건드리지 않는다 —
# 한국어 형태소 분석을 여기서 시작하면 끝이 없고, 그럴 필요도 없다.
_SPLIT = re.compile(r"[\s,.!?~…·\"'()\[\]]+")


def read_affirmation(text: str) -> bool | None:
    """긍정인가, 부정인가, 판정 불가인가.

    무엇을 하는가
        발화를 세 갈래로 나눈다.
            True   명시적 긍정 ("네", "그렇게 해줘")
            False  명시적 부정 ("아니요", "싫어")
            None   판정 불가 ("글쎄", "아마도", 침묵, 엉뚱한 대답)

    왜 bool 이 아니라 세 갈래인가  ★
        판정 불가를 False 로 접으면 "얼버무렸다"가 "거절했다"가 된다. 그러면 어르신이
        거절한 적 없는 항목이 거절로 기록되고, 그에 딸린 질문들이 영영 안 나온다.
        반대로 True 로 접으면 동의한 적 없는 동의가 기록된다. 둘 다 안 되므로 세 갈래다.

        None 의 올바른 처리는 '다시 묻기'다.

    왜 부정을 먼저 보는가
        긍정 표현이 부정 문장 안에 들어 있는 경우가 많다. "그래, 그건 아니야",
        "네, 싫어요". 긍정부터 찾으면 정반대로 판정한다.
        (206 의 `_is_completion_report` 가 "약 안 먹었어"에서 만난 것과 같은 함정이다.)

    누가 호출하는가
        handle_onboarding(동의 질문, 확인 단계), handle_clarification(확인 단계).

    주의사항
        목록은 policy.py 에 있고 실제 녹취록으로 넓혀야 한다. 넓힐 때 애매한 표현을
        긍정에 넣지 않는 것이 가장 중요하다.
    """
    normalized = (text or "").strip()
    if not normalized:
        # 침묵. 확인이 아니다.
        return None

    # 1. 얼버무림이 최우선이다. "글쎄, 그래"는 확인이 아니다.
    if _matches_any(normalized, policy.CONTRACT_NON_COMMITTAL):
        logger.info("non-committal answer; not treating it as a confirmation")
        return None

    # 2. 부정을 긍정보다 먼저. 위 docstring 참고.
    if _matches_any(normalized, policy.CONTRACT_NEGATIONS):
        return False

    if _is_affirmation(normalized):
        return True

    # 3. 멀쩡한 문장이지만 예/아니오가 아니다. 대개 다른 이야기를 하고 있다.
    #    "답변이 있었다"로 처리하면 다른 질문에 대한 답변이 확인으로 둔갑한다.
    return None


def is_confirmation(text: str) -> bool:
    """복창한 값에 대한 명시적 확인인가.

    read_affirmation 의 True 만 확인으로 인정한다. None(얼버무림)과 False 는 둘 다
    '확인 아님'이지만 뜻이 다르므로, 호출부가 구분해야 하면 read_affirmation 을 쓴다.

    이 함수는 백엔드에 넘길 `confirmed` 플래그를 만드는 자리다. 여기서 True 가 되면
    민감한 값이 확정되므로, 애매한 것은 전부 False 다.
    """
    return read_affirmation(text) is True


def looks_like_a_question(text: str) -> bool:
    """어르신이 '먼저 물은' 턴인가.

    왜 필요한가
        보류된 재질의가 있어도 어르신이 직접 물은 턴을 가로채서는 안 된다.
        "오늘 며칠이야?"에 "약을 몇 알 드세요?"로 답하는 로봇은 대화 상대가 아니다.
        **먼저 답하고, 재질의는 나중에** (CLAUDE.md §12).

    누가 호출하는가
        graph/context.py 의 classify_intent.

    주의사항
        ASR 은 물음표를 잘 붙이지 않는다. 그래서 어미로도 본다. 놓치는 쪽이
        가로채는 쪽보다 낫다 — 놓치면 재질의가 한 턴 늦을 뿐이다.
    """
    normalized = (text or "").strip()
    if not normalized:
        return False
    if normalized.endswith("?"):
        return True
    return any(normalized.endswith(suffix) for suffix in _QUESTION_SUFFIXES)


# 물음표 없이 끝나는 한국어 의문 어미. ASR 은 물음표를 잘 붙이지 않는다.
_QUESTION_SUFFIXES = (
    "까", "까요", "나요", "니", "냐", "지요", "죠", "가요", "래요", "래",
    "뭐야", "뭔데", "어때", "어떄", "언제", "어디", "누구", "얼마",
)


def _tokens(text: str) -> list[str]:
    """공백과 구두점으로 자른 낱말들. 조사·어미는 건드리지 않는다."""
    return [token for token in _SPLIT.split(text) if token]


def _matches_any(text: str, markers: tuple[str, ...]) -> bool:
    """표지 중 하나라도 걸리는가.

    ★ 한 글자 표지는 '낱말이 통째로 같을 때만' 인정한다 — 실제로 잡힌 오탐

        "네"를 부분 문자열로 찾으면 "좋네", "그러네", "약이 많네"가 전부 걸린다.
        "오늘 날씨가 참 좋네"가 동의로 읽히면, 어르신이 동의한 적 없는 건강정보
        처리에 동의 기록이 남는다.

        두 글자 이상은 부분 일치를 허용한다. "아니"는 "아니요"를 잡아야 하고,
        "모르겠"은 "모르겠어요"를 잡아야 한다 — 한국어 어미 변화를 목록으로
        전부 나열할 수는 없다.
    """
    tokens = _tokens(text)
    for marker in markers:
        if len(marker) == 1:
            if marker in tokens:
                return True
        elif marker in text:
            return True
    return False


def _is_affirmation(text: str) -> bool:
    """긍정인가. 부분 일치는 짧은 발화에서만 인정한다.

    왜 길이 조건이 붙는가
        "그래"는 부분 일치로 "그래서 어제 병원에 갔는데…"에 걸린다. 그건 동의가
        아니라 이야기의 시작이다. 실제 확인 응답은 짧다 — 길게 말하고 있다면
        확인이 아니라 다른 이야기다 (policy.CONTRACT_AFFIRMATION_MAX_CHARS).

        낱말이 통째로 일치하면 길이와 무관하게 인정한다. "네, 그리고 어제는…"의
        "네"는 명백한 긍정이다.
    """
    tokens = _tokens(text)
    for marker in policy.CONTRACT_AFFIRMATIONS:
        if marker in tokens:
            return True

    if len(text) > policy.CONTRACT_AFFIRMATION_MAX_CHARS:
        return False
    return any(
        len(marker) > 1 and marker in text
        for marker in policy.CONTRACT_AFFIRMATIONS
    )


def read_back(value: dict) -> str:
    """민감한 값을 어르신에게 그대로 읽어 줄 문장으로 만든다.

    왜 LLM 을 쓰지 않는가  ★
        복창의 목적은 '정확히 이 값이 맞는지' 확인받는 것이다. 모델이 다듬으면
        복창한 문장과 저장될 값이 달라질 수 있고, 그러면 어르신은 듣지 않은 값에
        동의한 것이 된다. 어색해도 값 그대로 읽는다.

    누가 호출하는가
        handle_onboarding, handle_clarification 의 확인 단계.

    반환값
        "혈압약, 1, 정. 이렇게 맞을까요?" 같은 한 문장.

    주의사항
        - 필드명을 읽지 않는다. "medicationName 은 혈압약"이 아니라 값만 나열한다.
          필드명은 계약의 언어이지 사람의 언어가 아니다.
        - 구두점은 쉼표와 마침표만 쓴다. 줄표(—)나 특수문자는 TTS 가 어떻게 읽을지
          보장되지 않고, 복창은 '정확히 들리는 것'이 목적이다.
    """
    parts = [str(item) for item in value.values() if item is not None and str(item).strip()]
    if not parts:
        return "제가 들은 게 없어요. 다시 한 번 말씀해 주시겠어요?"
    return f"{', '.join(parts)}. 이렇게 맞을까요?"
