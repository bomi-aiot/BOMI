"""build_prompt 단독 검증 — 그래프도 LLM 도 네트워크도 없이.

이 파일이 검증하는 완료 조건
    build_prompt() 단독 테스트 통과.

왜 이게 완료 조건인가
    자연스러움 대부분이 프롬프트에서 결정된다. 그래프를 띄우고 LLM 을 불러야 한 줄을
    확인할 수 있으면 아무도 프롬프트를 다듬지 않는다. 순수 함수라는 사실 자체가
    검증 대상이다.

참고
    CLAUDE.md §16 (조립 순서), §17 (자연스러움의 조작적 정의)
"""

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.prompts import build_prompt


@pytest.fixture
def ctx():
    """203 의 문맥 조립 API 응답 모양."""
    return {
        "profile": {
            "name": "김순자",
            "preferredName": "순자님",
            "avoidTopics": ["남편 사망"],
        },
        "todayState": {
            "medicationTakenCount": 1,
            "medicationScheduledCount": 2,
            "mealCount": 2,
            "waterIntakeCount": None,
        },
        "recentMessages": [
            {"role": "SENIOR", "content": "무릎이 아파"},
            {"role": "ROBOT", "content": "많이 불편하시겠어요"},
        ],
        "conversationSummary": "무릎 통증 이야기",
        "relevantSummaries": [
            {"content": "어제도 무릎이 아프다고 하셨다", "periodEndedAt": "2026-07-30T09:00:00Z"}
        ],
        "memories": [
            {"content": "작년부터 무릎이 아프시다", "lastConfirmedAt": "2026-06-01T09:00:00Z"}
        ],
        "careRecords": [
            {"recordType": "MEDICATION", "details": {"name": "혈압약", "dose": "1정"}}
        ],
        "documents": [
            {"title": "노인맞춤돌봄서비스", "content": "만 65세 이상 신청 가능"}
        ],
    }


def test_build_prompt_is_pure_and_returns_text(ctx):
    """순수 함수다. 같은 입력이면 같은 출력이고, 부수효과가 없다."""
    first = build_prompt(ctx, "companion", "무릎이 아파")
    second = build_prompt(ctx, "companion", "무릎이 아파")

    assert isinstance(first, str)
    assert first == second


def test_avoid_topics_are_rendered_as_prohibition_not_information(ctx):
    """★ 회피 목록은 '정보'가 아니라 '금지'로 들어가야 한다.

    사실로 주면 모델이 화제로 활용한다. 돌아가신 배우자를 살아있는 것처럼 꺼내는 것은
    이 시스템 최악의 실패 중 하나다 (CLAUDE.md §16 3단계, §17.5).
    """
    prompt = build_prompt(ctx, "companion", "요즘 어때요")

    assert "말하지 않을 주제" in prompt
    assert "먼저 꺼내지 않습니다" in prompt
    assert "남편 사망" in prompt


def test_output_constraints_appear_at_the_very_end(ctx):
    """제약은 맨 끝에 다시 나와야 한다.

    위에만 있으면 긴 문맥에 묻힌다. 모델은 마지막에 읽은 것을 더 잘 따른다.
    """
    prompt = build_prompt(ctx, "companion", "안녕")

    tail = prompt[-400:]
    assert "문장 이내" in tail
    assert f"{policy.MAX_SENTENCES}문장" in tail


def test_terse_tightens_the_sentence_limit(ctx):
    """quiet hours 의 인사는 더 짧아야 한다."""
    normal = build_prompt(ctx, "greeting", "다녀왔다")
    terse = build_prompt(ctx, "greeting", "다녀왔다", terse=True)

    assert f"{policy.MAX_SENTENCES}문장" in normal
    assert f"{policy.MAX_SENTENCES_TERSE}문장" in terse


def test_documents_only_for_info_intent(ctx):
    """문서는 info 에서만. 잡담에 넣으면 지연을 낭비하고 프롬프트를 오염시킨다."""
    info = build_prompt(ctx, "info", "노인맞춤돌봄서비스가 뭐야")
    companion = build_prompt(ctx, "companion", "요즘 어때요")

    assert "노인맞춤돌봄서비스" in info
    assert "참고 자료" in info
    assert "참고 자료" not in companion


def test_medical_stance_appears_only_when_the_turn_looked_up_medical_facts(ctx):
    """(회귀) 참고 자료가 있는데도 안 쓰던 사고 — 의료 조회 턴에만 지시를 붙인다.

    실측: "남경의원, 누엘의원, 가덕한의원"이 참고 자료에 정확히 있었는데도,
    system.md 의 "한 번에 한 가지만" 규칙과 부딪혀 "찾아드릴게요"로만 답한 사고가
    있었다. medical_stance.md 는 그 충돌을 "2~3개까지는 나열 가능"으로 풀어준다.

    날씨 등 다른 info 조회에는 이 지시가 붙으면 안 된다 — "2~3개만 안내"는 병원
    목록에나 맞는 말이라 관련 없는 지시로 프롬프트를 채우게 된다.
    """
    medical = build_prompt(ctx, "info", "부산 강서구 정형외과 찾아줘", is_medical=True)
    weather_like = build_prompt(ctx, "info", "노인맞춤돌봄서비스가 뭐야", is_medical=False)
    companion = build_prompt(ctx, "companion", "요즘 어때요", is_medical=True)

    assert "병원·약국·의약품 안내 방식" in medical
    assert "2~3개" in medical
    assert "병원·약국·의약품 안내 방식" not in weather_like
    # companion 은 애초에 참고 자료 섹션이 없으므로 is_medical=True 여도 안 붙는다
    # (핸들러 호출부는 실제로 info 일 때만 is_medical_query 를 채우지만, 이 함수
    # 자체의 방어도 확인해 둔다).
    assert "병원·약국·의약품 안내 방식" not in companion


def test_cached_context_adds_a_do_not_assert_warning(ctx):
    """캐시를 썼으면 단정적 표현을 막는 문구가 들어가야 한다.

    낡은 복약 정보를 단정적으로 말하는 것은 품질 문제가 아니라 안전 문제다.
    """
    fresh = build_prompt(ctx, "info", "내 약 뭐야", ctx_is_cached=False)
    cached = build_prompt(ctx, "info", "내 약 뭐야", ctx_is_cached=True)

    assert "단정적으로" not in fresh
    assert "단정적으로" in cached


def test_memories_carry_dates(ctx):
    """기억에 날짜가 붙어야 모델이 여섯 달 전 일을 오늘 일처럼 말하지 않는다."""
    prompt = build_prompt(ctx, "companion", "무릎")

    assert "(2026-06-01)" in prompt


def test_medication_appears_as_exact_fact(ctx):
    """복약은 정확 조회 결과 그대로 실린다."""
    prompt = build_prompt(ctx, "info", "내 약 뭐야")

    assert "혈압약" in prompt


def test_unmeasured_metric_is_omitted_rather_than_reported_as_zero(ctx):
    """None 은 '측정 못 함'이고 0 이 아니다. 없는 값은 아예 넣지 않는다.

    0 으로 말하면 하지 않은 일을 단정하게 된다.
    """
    prompt = build_prompt(ctx, "companion", "안녕")

    assert "식사: 2회" in prompt
    assert "물:" not in prompt


def test_empty_sections_are_omitted():
    """빈 섹션은 만들지 않는다.

    "기억: (없음)"을 보면 모델이 기억이 없다는 사실 자체를 화제로 삼는다.
    """
    prompt = build_prompt({}, "companion", "안녕")

    assert "기억하고 있는 것" not in prompt
    assert "말하지 않을 주제" not in prompt
    # 시스템 지시와 출력 제약은 문맥이 비어도 남아야 한다.
    assert "보미" in prompt
    assert "문장 이내" in prompt


def test_recent_phrasings_instruct_variation(ctx):
    """같은 알림이 3일 연속 똑같지 않게 하는 한 줄 (CLAUDE.md §17.8)."""
    prompt = build_prompt(
        ctx, "companion", "", recent_phrasings=["물 한 잔 드세요", "물 좀 드시겠어요"])

    assert "다르게 말합니다" in prompt
    assert "물 한 잔 드세요" in prompt


def test_speech_origin_explains_why_the_robot_is_speaking(ctx):
    """능동 턴에서는 '왜 말하는가'가 프롬프트에 들어간다."""
    prompt = build_prompt(ctx, "companion", "", speech_origin="silence_ladder:1")

    assert "지금 말을 꺼내는 이유" in prompt
    assert "silence_ladder:1" in prompt


def test_proactive_turn_without_user_input_is_marked(ctx):
    """발화 없이 먼저 말을 꺼내는 턴임을 모델이 알아야 한다."""
    prompt = build_prompt(ctx, "companion", "")

    assert "먼저 말을 꺼냅니다" in prompt


def test_repetition_count_never_reaches_the_prompt(ctx):
    """★ 지남력 질문의 반복 횟수는 절대 프롬프트에 닿지 않는다.

    닿으면 어조에 새어나가 열 번째 답변이 짜증스럽게 들린다. 그 정보는 T2 추세로만
    간다 (CLAUDE.md §8).
    """
    polluted = {**ctx, "orientationRepeatCount": 9, "repeatedQuestionCount": 9}

    prompt = build_prompt(polluted, "info", "오늘 며칠이야")

    assert "9" not in prompt or "9번" not in prompt
    assert "repeat" not in prompt.lower()
    assert "반복" not in prompt
