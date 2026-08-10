"""build_memory_extraction_prompt 단독 검증 — 시계도 LLM 도 네트워크도 없이 (G4).

이 파일이 검증하는 것
    1. 어르신의 '지금'을 주면 프롬프트에 그 날짜·요일·UTC 오프셋이 전부 실린다.
    2. 시각을 모르면 날짜를 지어내지 않는다 — 블록은 남되 "알 수 없습니다"로 나가고,
       프롬프트 어디에도 날짜처럼 보이는 문자열이 생기지 않는다.
    3. APPOINTMENT 분류와 startsAt 형식 지시가 실제로 프롬프트에 실린다
       (템플릿과 빌더가 따로 놀지 않는지 보는 회귀).
    4. 순수 함수다 — 같은 입력이면 같은 출력이고, 시계를 읽지 않는다.
    5. 기존 2-위치인자 호출이 그대로 산다(하위 호환).

왜 2번이 이 파일에서 가장 중요한가
    모르면 뽑지 않는 쪽이 안전한 이유는, 이 경로의 끝이 보호자 화면의 일정이기
    때문이다. 프롬프트가 침묵하면 모델은 그 침묵을 "알아서 하라"로 읽고 '다음 주
    화요일'을 제 마음대로 계산한다. 없다는 사실 자체가 지시여야 한다.

참고
    CLAUDE.md §8, §16 / prompts/builder.py, prompts/templates/memory_extract.md
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from bomi_ai_chat.prompts import build_memory_extraction_prompt

# 어떤 자리에도 진짜 날짜가 새지 않았는지 보는 패턴. 2026-08-11 같은 것을 잡는다.
_LOOKS_LIKE_A_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

SEOUL = timezone(timedelta(hours=9))


@pytest.fixture
def seoul_now() -> datetime:
    """2026-08-07(금) 15:04, 서울. CLAUDE.md 의 '오늘'과 같은 날로 둔다."""
    return datetime(2026, 8, 7, 15, 4, 0, tzinfo=SEOUL)


# ── 1. 날짜 주입 ─────────────────────────────────────────────────────────────


def test_the_prompt_carries_the_local_date_weekday_and_offset(seoul_now):
    """모델이 "다음 주 화요일"을 계산하려면 기준점과 시간대가 둘 다 있어야 한다."""
    prompt = build_memory_extraction_prompt("", "다음 주 화요일 세 시에 병원 가", now_local=seoul_now)

    assert "2026-08-07T15:04:00+09:00" in prompt
    assert "금요일" in prompt
    # 오프셋이 빠지면 모델이 +09:00 을 붙일 근거가 사라지고, 오프셋 없는 startsAt 은
    # 서버에서 조용히 '지금'으로 바뀐다.
    assert "+09:00" in prompt


def test_a_different_zone_shows_that_zone_not_utc():
    """어르신의 시간대를 그대로 싣는다 — UTC 로 바꿔 넣지 않는다."""
    tokyo_ish = datetime(2026, 8, 8, 1, 0, 0, tzinfo=timezone(timedelta(hours=9)))
    prompt = build_memory_extraction_prompt("", "내일 얘기예요", now_local=tokyo_ish)

    assert "2026-08-08T01:00:00+09:00" in prompt
    # 같은 순간의 UTC 는 8월 7일 16시다. 그 날짜가 보이면 시간대가 뭉개진 것이다.
    assert "2026-08-07" not in prompt


# ── 2. 모를 때는 지어내지 않는다 ─────────────────────────────────────────────


def test_without_a_local_now_the_prompt_says_so_and_forbids_appointments():
    prompt = build_memory_extraction_prompt("", "다음 주 화요일 세 시에 병원 가", now_local=None)

    assert "오늘이 며칠인지 알 수 없습니다" in prompt
    assert "약속(APPOINTMENT)을 뽑지 않습니다" in prompt


def test_without_a_local_now_no_date_like_string_appears_anywhere():
    """★ 베낄 것이 없어야 지어내지 않는다.

    템플릿의 출력 예시에 진짜 날짜를 박아 두면 모델이 날짜를 모르는 턴에도 그
    값을 그대로 베낀다 — llm/client.py 에서 이미 밟은 사고(예시의 날씨 수치를
    날씨 정보가 없는 턴에 지어냄)와 같은 실패다. 그래서 이 프롬프트의 날짜 견본은
    '오늘' 블록 하나뿐이고, 그 블록이 사라지면 견본도 함께 사라져야 한다.
    """
    prompt = build_memory_extraction_prompt(
        "요즘 어떻게 지내세요?", "다음 주 화요일 세 시에 병원 가", now_local=None)

    assert _LOOKS_LIKE_A_DATE.search(prompt) is None


# ── 3. 템플릿-빌더 연결 ──────────────────────────────────────────────────────


def test_the_appointment_category_and_starts_at_rules_are_in_the_prompt(seoul_now):
    prompt = build_memory_extraction_prompt("", "다음 주 화요일 세 시에 병원 가", now_local=seoul_now)

    assert "APPOINTMENT" in prompt
    assert "startsAt" in prompt
    assert "title" in prompt
    # 기존 다섯 분류가 그대로 남아 있어야 한다(회귀).
    for fact_type in ("FAMILY", "HOBBY", "DAILY_LIFE", "HEALTH", "OTHER"):
        assert fact_type in prompt


def test_the_prompt_refuses_guessed_times(seoul_now):
    """"조만간"은 날짜가 아니다 — contract_extract.md 의 "한 알쯤은 1이 아닙니다"와 같은 태도."""
    prompt = build_memory_extraction_prompt("", "조만간 병원 가야지", now_local=seoul_now)

    assert "조만간" in prompt  # 발화 자체
    assert '"조만간"은 날짜가 아닙니다' in prompt  # 규칙


# ── 4·5. 순수성과 하위 호환 ──────────────────────────────────────────────────


def test_it_is_pure_and_reads_no_clock(seoul_now):
    """frozen_clock 없이 돈다 — 시계는 호출부가 읽고 값만 넘긴다."""
    first = build_memory_extraction_prompt("직전 말", "어르신 말", now_local=seoul_now)
    second = build_memory_extraction_prompt("직전 말", "어르신 말", now_local=seoul_now)

    assert first == second
    assert isinstance(first, str)
    assert "직전 말" in first
    assert "어르신 말" in first


def test_the_two_positional_argument_call_still_works():
    """now_local 은 키워드 전용에 기본값 None — 기존 호출부가 그대로 산다."""
    prompt = build_memory_extraction_prompt("직전 말", "어르신 말")

    assert "직전 말" in prompt
    assert "어르신 말" in prompt
    assert "오늘이 며칠인지 알 수 없습니다" in prompt


def test_a_missing_preceding_utterance_is_rendered_as_none(seoul_now):
    prompt = build_memory_extraction_prompt("", "어르신 말", now_local=seoul_now)

    assert "(없음)" in prompt
