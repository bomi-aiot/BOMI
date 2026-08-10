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
from bomi_ai_chat.prompts import build_prompt, builder


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


def test_document_source_version_chunk_and_citation_reach_the_prompt(ctx):
    """문서 코퍼스 근거 식별자는 본문과 함께 최종 프롬프트까지 보존된다."""
    ctx["documents"] = [{
        "title": "기초연금 안내",
        "content": "신청은 주소지 주민센터에서 할 수 있습니다.",
        "source": "보건복지부",
        "version": "2026-07",
        "chunkId": "basic-pension#apply",
        "citation": "사업안내 31쪽",
        "url": "https://example.test/basic-pension",
    }]

    prompt = build_prompt(ctx, "info", "기초연금 어디서 신청해")

    assert "출처=보건복지부" in prompt
    assert "버전=2026-07" in prompt
    assert "청크=basic-pension#apply" in prompt
    assert "인용=사업안내 31쪽" in prompt
    assert "URL=https://example.test/basic-pension" in prompt


def test_unavailable_semantic_and_document_search_add_honest_warnings(ctx):
    """검색 불가를 '관련 결과 없음'으로 오해하지 않게 프롬프트에 구분한다."""
    prompt = build_prompt(
        ctx,
        "info",
        "복지제도 알려줘",
        retrieval_status={
            "semantic_available": False,
            "documents_requested": True,
            "document_corpus_available": False,
            "document_hit_count": 0,
        },
    )

    assert "의미 기반 기억 검색을 사용할 수 없습니다" in prompt
    assert "관련 기억이 없다고 단정하지 않습니다" in prompt
    assert "참고 문서 코퍼스를 확인할 수 없습니다" in prompt


def test_empty_document_result_is_distinct_from_unavailable_corpus(ctx):
    """코퍼스 조회 성공·0건과 코퍼스 장애는 서로 다른 안전 문구를 쓴다."""
    prompt = build_prompt(
        {**ctx, "documents": []},
        "info",
        "복지제도 알려줘",
        retrieval_status={
            "documents_requested": True,
            "document_corpus_available": True,
            "document_used": True,
            "document_hit_count": 0,
        },
    )

    assert "관련 문서를 찾지 못했습니다" in prompt
    assert "코퍼스를 확인할 수 없습니다" not in prompt


def test_request_level_document_failure_is_distinct_from_zero_hits(ctx):
    """코퍼스가 살아 있어도 이번 검색 실패면 0-hit 성공으로 말하지 않는다."""
    prompt = build_prompt(
        {**ctx, "documents": []},
        "info",
        "복지제도 알려줘",
        retrieval_status={
            "documents_requested": True,
            "document_corpus_available": True,
            "document_used": False,
            "document_fallback_reason": "document_search_failed",
            "document_hit_count": 0,
        },
    )

    assert "참고 문서 검색을 완료하지 못했습니다" in prompt
    assert "document_search_failed" in prompt
    assert "관련 문서를 찾지 못했습니다" not in prompt


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


# ── 이야기 턴 (2026-08-10 실사용 피드백) ────────────────────────────────────


def test_a_story_turn_raises_the_sentence_limit_and_adds_the_stance(ctx):
    """★ "심심해"에 이야기를 실제로 들려주려면 두 문장 상한을 벗어나야 한다.

    실측: 어르신이 "재미있는 이야기 해줘"라고 해도 로봇은 "해드릴까요?"라고만
    되물었다. 원인은 모델이 아니라 프롬프트의 두 문장 상한과 "한 가지만" 지시였다.
    """
    prompt = build_prompt(ctx, "companion", "심심해", wants_story=True)

    assert f"{policy.MAX_SENTENCES_STORY}문장 이내" in prompt
    assert "묻지 말고 시작합니다" in prompt


def test_a_story_turn_carries_the_actual_repertoire(ctx):
    """★ 태도만 주면 매번 같은 이야기가 나오고, 없는 이야기를 지어낼 여지도 생긴다.

    목록을 함께 실어서 "무엇을 말할지"를 프롬프트가 정하게 한다.
    """
    prompt = build_prompt(ctx, "companion", "심심해", wants_story=True)

    assert "들려드릴 이야기 목록" in prompt
    assert "소금 나오는 맷돌" in prompt      # 옛이야기
    assert "동지 팥죽" in prompt             # 절기
    assert "가을 운동회" in prompt           # 회상 유도


def test_stories_told_recently_are_shown_so_they_are_not_repeated(ctx):
    """같은 옛날이야기를 세 번 들으면 로봇이 하나밖에 모른다는 걸 바로 아신다."""
    told = {**ctx, "recentStories": ["옛날에 형제가 살았는데, 아우가 맷돌을"]}

    prompt = build_prompt(told, "companion", "심심해", wants_story=True)

    assert "## 최근에 들려드린 이야기" in prompt
    assert "아우가 맷돌을" in prompt


def test_no_empty_recent_story_section_when_nothing_was_told(ctx):
    """빈 절을 넣지 않는다 — 모델이 "처음 들려드리네요"를 화제로 삼는다.

    제목만 본다. 목록(stories.md)이 본문에서 이 절을 가리키므로 같은 낱말은
    프롬프트 어딘가에 늘 있다.
    """
    prompt = build_prompt(ctx, "companion", "심심해", wants_story=True)

    assert "## 최근에 들려드린 이야기" not in prompt


def test_an_ordinary_turn_keeps_the_two_sentence_limit_and_no_story_stance(ctx):
    """이야기 지시는 청한 턴에만 붙는다. 늘 켜면 알림·안내까지 길어진다."""
    prompt = build_prompt(ctx, "companion", "점심 먹었어")

    assert f"{policy.MAX_SENTENCES}문장 이내" in prompt
    assert "묻지 말고 시작합니다" not in prompt


def test_quiet_hours_beat_a_story_request(ctx):
    """새벽 두 시에는 여덟 문장짜리 옛날이야기를 시작하지 않는다."""
    prompt = build_prompt(ctx, "companion", "심심해", terse=True, wants_story=True)

    assert f"{policy.MAX_SENTENCES_TERSE}문장 이내" in prompt
    assert "묻지 말고 시작합니다" not in prompt


# ── 오늘의 복약 (2026-08-10 실사용 피드백) ──────────────────────────────────


def test_medication_is_rendered_even_though_the_backend_never_sends_a_denominator(ctx):
    """★ 예정 횟수는 백엔드가 설계상 늘 null 이다.

    그래서 예전 조건("예정 횟수가 있으면")은 영원히 거짓이었고, 복약 이행이
    프롬프트에 한 번도 실리지 않았다 — 분자만 있어도 말할 수 있는데도.
    """
    today = {**ctx["todayState"], "medicationTakenCount": 2,
             "medicationScheduledCount": None}

    prompt = build_prompt({**ctx, "todayState": today}, "schedule", "약 먹었나")

    assert "오늘 2회" in prompt


def test_what_the_senior_said_about_medication_is_marked_as_hearsay(ctx):
    """★ 로컬 기록은 '복약 기록'이 아니라 '어르신이 하신 말'이다.

    로봇이 확인한 사실처럼 말하면, 기억이 흐린 분에게 잘못된 확신을 준다.
    프롬프트 문구가 출처를 남겨야 모델도 "드셨다고 하셨어요"로 말한다.
    """
    prompt = build_prompt(
        {**ctx, "medicationReportedTimes": ["08:31", "12:35"]},
        "schedule", "아침에 약을 먹었는지 기억이 안나")

    assert "말씀하신 시각: 08:31, 12:35" in prompt


# ── 복약·일정 렌더 (2026-08-10 실측) ───────────────────────────────────────


CARE_CTX = {"careRecords": [
    {"recordType": "MEDICATION", "details": {
        "activeIngredient": "모름", "dose": "1정", "medicationName": "혈압약",
        "instruction": "아침 식사 후 물과 함께 복용", "purpose": "혈압조절",
        "reminderEnabled": False}},
    {"recordType": "MEDICATION_SCHEDULE", "details": {
        "localTimes": ["09:00"], "medicationName": "혈압약",
        "reminderLeadMinutes": 10, "timeZone": "Asia/Seoul"}},
    {"recordType": "MEDICATION", "details": {
        "dose": 1, "doseUnit": "정", "medicationName": "관절염약",
        "instruction": "매 끼니 식후 30분", "sourceType": "ONBOARDING_ANSWER",
        "verificationStatus": "USER_CONFIRMED"}},
    {"recordType": "MEDICATION_SCHEDULE", "details": {
        "localTimes": ["08:30", "12:30", "18:30"], "mealTimes": ["08:00"],
        "medicationName": "관절염약", "timeZone": "Asia/Seoul",
        "sourceType": "CONVERSATION_MESSAGE"}},
]}


def test_internal_plumbing_never_reaches_the_prompt():
    """★ system.md 가 금지한 것을 우리가 직접 먹이고 있었다.

    details 를 통째로 펼치던 렌더가 `verificationStatus USER_CONFIRMED`,
    `sourceType ONBOARDING_ANSWER`, `timeZone Asia/Seoul` 을 프롬프트에 실었다.
    233 실기에서 로봇이 "[현재 정보] ..."를 소리 내어 읽은 것과 같은 누출이다.
    """
    prompt = build_prompt(CARE_CTX, "companion", "안녕")

    for leaked in ("verificationStatus", "sourceType", "timeZone",
                   "reminderEnabled", "reminderLeadMinutes", "localTimes"):
        assert leaked not in prompt, leaked


def test_the_same_medicine_is_one_line_not_two():
    """MEDICATION 과 MEDICATION_SCHEDULE 은 같은 약의 두 기록이다.

    따로 실으면 프롬프트에 "혈압약"이 두 번 나오고, 모델이 약이 두 개라고 읽는다.
    """
    rendered = builder._format_care_records(CARE_CTX)

    assert rendered.count("혈압약") == 1
    assert rendered.count("관절염약") == 1
    assert "- 복약 혈압약: 1정, 아침 식사 후 물과 함께 복용, 혈압조절 (09:00)" in rendered
    assert "(08:30, 12:30, 18:30)" in rendered


def test_unknown_values_are_dropped_not_spoken():
    """`activeIngredient 모름` 을 실으면 모델이 '모름'을 사실로 읽고 말한다."""
    assert "모름" not in builder._format_care_records(CARE_CTX)


def test_care_records_stay_in_every_turn_even_when_off_topic():
    """★ intent 로 이 섹션을 끄지 않는다 — 분류 실패가 곧 안전 실패가 된다.

    "아침에 약을 먹었는지 기억이 안 나"가 companion 으로 빠지던 버그가 그 증거다.
    그 턴에 복약이 프롬프트에 없었다면 로봇은 되묻지도 못했다.
    """
    prompt = build_prompt(CARE_CTX, "companion", "옛날 생각나네", wants_reminiscence=True)

    assert "관절염약" in prompt


def test_a_schedule_is_one_human_sentence_not_three_repeats():
    """content·title·startsAt 을 다 실으면 같은 약속이 세 번 나온다."""
    rendered = builder._format_care_records({"careRecords": [
        {"recordType": "APPOINTMENT", "details": {
            "title": "병원 예약", "content": "8월 10일 오후 2시에 병원에 간다.",
            "startsAt": "2026-08-10T14:00:00+09:00"}},
    ]})

    assert rendered == "- 일정: 8월 10일 오후 2시에 병원에 간다."
    assert "2026-08-10T" not in rendered


# ── 회상 턴 (2026-08-10) ────────────────────────────────────────────────────


def test_a_reminiscence_turn_gets_the_stance_and_the_era_prompts(ctx):
    """회상은 시간 메꾸기가 아니라 이 대화가 하려는 일이다 (CLAUDE.md §1)."""
    prompt = build_prompt(
        ctx, "companion", "옛날에 학교 다닐 때가 생각나네", wants_reminiscence=True)

    assert "마중물" in prompt
    assert "검정 고무신" in prompt


def test_the_seniors_own_memories_come_before_the_era_prompts(ctx):
    """★ 1번(개인 씨앗) 없이 3번(마중물)만 하면 "누구에게나 하는 말"이 된다.

    지시문이 그 순서를 명시해야 모델이 목록부터 꺼내지 않는다.
    """
    prompt = build_prompt(ctx, "companion", "예전 생각이 나", wants_reminiscence=True)

    assert "\"기억하고 있는 것\"에 있는 어르신의 이야기를 먼저 씁니다" in prompt


def test_reminiscence_does_not_change_the_sentence_limit(ctx):
    """이야기와 다르다. 회상은 짧게 받고 되묻는 것이 정석이다."""
    prompt = build_prompt(ctx, "companion", "옛날 생각나네", wants_reminiscence=True)

    assert f"{policy.MAX_SENTENCES}문장 이내" in prompt


@pytest.mark.parametrize("intent", ["schedule", "info"])
def test_reminiscence_stance_stays_off_outside_companion_turns(ctx, intent):
    """★ "예전에 먹던 약이 뭐였지"는 회상 표지에 걸리지만 복약 턴이다.

    거기에 회상 태도를 얹으면 답해야 할 것을 안 답하고 옛날 이야기를 여쭙는다.
    """
    prompt = build_prompt(
        ctx, intent, "예전에 먹던 약이 뭐였지", wants_reminiscence=True)

    assert "마중물" not in prompt
