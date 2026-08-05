"""표현 다양화 배선 검증 — S15P11E102-256.

이 파일이 검증하는 완료 조건
    - phrasing_key 가 식사/수분을 분리하고, 같은 끼니는 같은 키로 묶는다.
    - 침묵 프로브와 T3 동의 질문은 키를 만들지 않는다(기록·조회 대상에서 빠진다).
    - localstore.phrasings 가 보관 기간 만료, 재시작, 개수 상한 초과를 각각
      실제로 지운다.

무엇을 검증하지 '않는가'
    graph/build.py.memory_write 와 graph/context.py.context_read 가 실제로
    이 모듈을 부르는지는 tests/test_naturalness_replay.py 의 시나리오 08
    (proactive 경로)이 그래프 전체를 태워서 확인한다. 여기서는 순수 함수와
    저장소만 좁게 본다.

참고
    CLAUDE.md §17.8, §19 / graph/phrasing.py, localstore/phrasings.py
"""

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.graph.phrasing import phrasing_key
from bomi_ai_chat.localstore import db, phrasings

SENIOR = "senior-1"


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    """테스트마다 빈 저장소를 쓰고, 끝나면 연결을 닫는다 (test_localstore.py 관례)."""
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()


def restart() -> None:
    """프로세스 재시작을 흉내낸다."""
    db.close_all()


# ─────────────────────────────────────────────────────────────────────────────
# phrasing_key — 순수 함수
# ─────────────────────────────────────────────────────────────────────────────


def test_meal_and_water_get_different_keys():
    """식사 권유와 수분 권유는 서로 다른 키로 분리된다 (완료 조건)."""
    meal = phrasing_key("schedule:meal:0800", "companion")
    water = phrasing_key("schedule:water:1000", "companion")

    assert meal != water


def test_same_meal_slot_shares_a_key_across_days():
    """같은 끼니(아침)는 같은 키로 묶인다 (완료 조건).

    jobs/ticks.schedule_tick 이 만드는 origin 에는 날짜가 없다("schedule:meal:0800").
    그래서 오늘의 아침 권유와 내일의 아침 권유가 저절로 같은 키가 된다.
    """
    today_breakfast = phrasing_key("schedule:meal:0800", "companion")
    tomorrow_breakfast = phrasing_key("schedule:meal:0800", "companion")

    assert today_breakfast == tomorrow_breakfast


def test_different_meal_slots_get_different_keys():
    """아침과 점심은 같은 "meal" 이어도 다른 키다 — 다른 시각의 다른 권유다."""
    breakfast = phrasing_key("schedule:meal:0800", "companion")
    lunch = phrasing_key("schedule:meal:1230", "companion")

    assert breakfast != lunch


def test_silence_probe_is_excluded():
    """침묵 프로브는 다양화 대상이 아니다 (완료 조건).

    생존 확인이 목적이라, 매번 다른 문구가 오히려 "새 질문"으로 들려 혼란을 준다.
    """
    assert phrasing_key("silence_ladder:1", "companion") == ""
    assert phrasing_key("silence_ladder:3", "companion") == ""


def test_t3_consent_question_is_excluded():
    """T3 동의 질문은 다양화 대상이 아니다 (완료 조건).

    문구 자체가 고정된 한국어 문장이라 다양화할 대상이 없다(원인이지, "id 가
    붙어서 키가 늘어난다"가 아니다 — 티켓의 정정 사항).
    """
    origin = "t3_consent: 어르신이 마음을 이야기하셨고, 그것을 가족과 나눠도 될지"
    assert phrasing_key(origin, "emotional") == ""


def test_empty_origin_or_intent_yields_no_key():
    """능동/명령 턴이 아니어서 origin 이 비었으면 다양화 대상이 아니다."""
    assert phrasing_key("", "companion") == ""
    assert phrasing_key("schedule:water:1000", "") == ""


# ─────────────────────────────────────────────────────────────────────────────
# localstore.phrasings — 저장소
# ─────────────────────────────────────────────────────────────────────────────


def test_record_then_recent_round_trips():
    """방금 기록한 표현이 조회에 그대로 나온다."""
    phrasings.record(SENIOR, "companion:schedule:water:1000", "물 한 잔 드세요.")

    assert phrasings.recent(SENIOR, "companion:schedule:water:1000") == ["물 한 잔 드세요."]


def test_recent_returns_oldest_first(frozen_clock):
    """오래된 것부터 최신 순으로 돌아온다 (localstore/phrasings.py 참고)."""
    sim = frozen_clock(start=1_000.0)
    key = "companion:schedule:water:1000"

    phrasings.record(SENIOR, key, "첫 번째")
    sim.advance(60)
    phrasings.record(SENIOR, key, "두 번째")
    sim.advance(60)
    phrasings.record(SENIOR, key, "세 번째")

    assert phrasings.recent(SENIOR, key) == ["첫 번째", "두 번째", "세 번째"]


def test_recent_respects_lookback_limit(frozen_clock):
    """policy.RECENT_PHRASING_LOOKBACK 개수만 돌아온다."""
    sim = frozen_clock(start=1_000.0)
    key = "companion:schedule:water:1000"

    for index in range(policy.RECENT_PHRASING_LOOKBACK + 2):
        phrasings.record(SENIOR, key, f"표현{index}")
        sim.advance(1)

    result = phrasings.recent(SENIOR, key)

    assert len(result) == policy.RECENT_PHRASING_LOOKBACK
    # 가장 최근 것들만 남아야 한다 — 잘려나가는 것은 오래된 쪽이다.
    assert result[-1] == f"표현{policy.RECENT_PHRASING_LOOKBACK + 1}"


def test_empty_key_does_nothing():
    """phrasing_key 가 빈 문자열을 돌려준 경우(다양화 대상이 아님) 아무것도 안 쓴다.

    호출자(graph/build.py._record_phrasing)가 매번 빈 문자열을 검사하지 않아도
    되게 하는 계약이다.
    """
    phrasings.record(SENIOR, "", "아무 말")

    assert phrasings.recent(SENIOR, "") == []


def test_retention_expiry(frozen_clock):
    """(완료 조건) 보관 기간이 지난 표현은 다음 기록 때 지워진다."""
    sim = frozen_clock(start=1_000.0)
    key = "companion:schedule:water:1000"

    phrasings.record(SENIOR, key, "오래된 표현")

    # 보관 기간을 하루 넘겨서 시계를 돌린다.
    sim.advance((policy.RECENT_PHRASING_RETENTION_DAYS + 1) * 86400)
    phrasings.record(SENIOR, key, "새 표현")

    assert phrasings.recent(SENIOR, key) == ["새 표현"]


def test_survives_restart(frozen_clock):
    """(완료 조건) 재시작 후에도 표현 이력이 남아 있다."""
    frozen_clock(start=1_000.0)
    key = "companion:schedule:water:1000"

    phrasings.record(SENIOR, key, "재시작 전 표현")
    restart()

    assert phrasings.recent(SENIOR, key) == ["재시작 전 표현"]


def test_max_rows_per_key_caps_storage(frozen_clock):
    """(완료 조건) 개수 상한을 넘기면 오래된 행부터 저장소에서 실제로 지워진다.

    RECENT_PHRASING_LOOKBACK(조회 개수)보다 큰 상한을 넉넉히 기록해서, "조회가
    제한됐을 뿐 저장은 무한정 쌓인다"는 상황이 아님을 확인한다 — sqlite 파일에
    남은 행 수를 직접 센다.
    """
    sim = frozen_clock(start=1_000.0)
    key = "companion:schedule:water:1000"

    total_written = policy.RECENT_PHRASING_MAX_ROWS_PER_KEY + 5
    for index in range(total_written):
        phrasings.record(SENIOR, key, f"표현{index}")
        sim.advance(1)

    connection = db.runtime_db()
    row = connection.execute(
        "SELECT COUNT(*) AS n FROM spoken_phrasing WHERE senior_id = ? AND phrasing_key = ?",
        (SENIOR, key),
    ).fetchone()

    assert row["n"] == policy.RECENT_PHRASING_MAX_ROWS_PER_KEY


def test_clear_removes_all_history_for_senior():
    """clear() 는 이 어르신의 이력을 전부 지운다 (테스트·운영자 개입용)."""
    key = "companion:schedule:water:1000"
    phrasings.record(SENIOR, key, "표현")

    phrasings.clear(SENIOR)

    assert phrasings.recent(SENIOR, key) == []
