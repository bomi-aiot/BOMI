"""침묵 사다리 — 하루치 시나리오 회귀.

이 파일이 검증하는 완료 조건
    1. SimClock 으로 하루치 시나리오 4종 (정상 침묵 / 외출 / 낮잠 / 무응답)
    2. 사다리 소진 시 T1 이 outbox 에 적재된다

왜 시나리오로 검증하는가
    이 기능의 실패는 "동작이 틀렸다"가 아니라 "적절하지 않은 때에 동작했다"이다.
    함수 하나를 단위 테스트해서는 그것을 잡을 수 없다. 하루를 흘려보내면서
    "이 상황에서 로봇이 몇 번 말을 걸었나"를 세야 한다.

    오탐이 폭발하면 보호자가 알림을 무시하기 시작하고, 그때부터 진짜 응급을
    놓친다. 시끄러운 감지기는 짜증이 아니라 안전 실패다 (CLAUDE.md §10).

참고
    CLAUDE.md §10 (침묵 사다리), §15 (압축 시계), §22 4단계
"""

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.jobs import ticks
from bomi_ai_chat.localstore import context_cache, db, outbox, proposals
from bomi_ai_chat.localstore import runtime as runtime_store

SENIOR = "senior-1"

# 2026-08-01 00:00 UTC = 서울 09:00. 아침에 대화를 나눈 뒤 하루가 흐른다.
MORNING_UTC = 1785542400.0
HOUR = 3600.0

SEOUL_PROFILE = {
    "profile": {
        "timeZone": "Asia/Seoul",
        "quietHoursStart": "22:00",
        "quietHoursEnd": "07:00",
    }
}


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()


def start_day(frozen_clock, *, occupancy="HOME", rest_state="AWAKE"):
    """아침 09:00 에 어르신과 대화한 상태로 하루를 시작한다."""
    sim = frozen_clock(start=MORNING_UTC)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    runtime_store.save(
        SENIOR,
        last_user_interaction_at=MORNING_UTC,
        occupancy=occupancy,
        rest_state=rest_state,
        silence_level=0,
    )
    return sim


def run_hours(sim, hours: int) -> list[dict]:
    """한 시간씩 흘리며 틱을 돌린다. 그동안 큐에 들어온 프로브를 모은다.

    app 을 넘기지 않으므로 프로브는 제안 큐에 쌓인다. 게이트를 통과하는지는
    test_proactive_gate 가 따로 검증한다 — 여기서 보는 것은 '사다리가 언제
    올라가는가'다.
    """
    for _ in range(hours):
        sim.advance(HOUR)
        ticks.silence_tick(SENIOR, None)
    return [
        p for p in proposals.pending(SENIOR)
        if p.get("origin", "").startswith("silence_ladder")
    ]


# ── 시나리오 1: 정상 침묵 (조금 조용한 것뿐) ───────────────────────────────


def test_short_quiet_spell_does_not_probe(frozen_clock):
    """(시나리오 1) 두 시간 조용한 것으로는 아무 일도 일어나지 않는다.

    사다리 1칸이 3시간이다. 그전에 프로브를 던지면 로봇이 안절부절 못하는
    것처럼 보인다.
    """
    sim = start_day(frozen_clock)

    probes = run_hours(sim, 2)

    assert probes == []
    assert runtime_store.load(SENIOR)["silence_level"] == 0


# ── 시나리오 2: 외출 ───────────────────────────────────────────────────────


def test_going_out_all_day_never_probes(frozen_clock):
    """(시나리오 2) 하루 종일 나가 있으면 사다리가 아예 돌지 않는다.

    집에 없는 사람이 대답하지 않는 것은 아무 정보도 아니다. 여기서 프로브를
    던지면 빈 집에 대고 말하는 것이고, 결국 보호자에게 오탐이 간다.
    """
    sim = start_day(frozen_clock, occupancy="AWAY")

    probes = run_hours(sim, 10)

    assert probes == []
    assert outbox.pending_count() == 0


# ── 시나리오 3: 낮잠 ───────────────────────────────────────────────────────


def test_resting_delays_the_ladder_but_does_not_stop_it(frozen_clock):
    """(시나리오 3) 낮잠은 사다리를 '늦춘다'. 멈추지는 않는다.

    쉬는 중의 침묵은 정상이지만, 쉬다가 쓰러질 수도 있다. 그래서 완전히
    멈추지 않고 인내심 배수만큼 늦춘다.
    """
    awake = start_day(frozen_clock, rest_state="AWAKE")
    awake_probes = run_hours(awake, 4)
    assert awake_probes, "깨어 있으면 4시간 뒤에는 프로브가 나가야 한다"

    # 같은 4시간을 쉬는 상태로 흘려보낸다.
    db.close_all()
    proposals.clear(SENIOR)
    resting = start_day(frozen_clock, rest_state="RESTING")
    resting_probes = run_hours(resting, 4)

    assert resting_probes == [], "쉬는 중이면 아직 이르다"


def test_resting_eventually_probes_anyway(frozen_clock):
    """쉬고 있어도 충분히 길면 결국 확인한다. 쉬다가 쓰러질 수도 있다."""
    sim = start_day(frozen_clock, rest_state="RESTING")

    # 인내심 배수를 곱한 1칸 임계치를 넘긴다.
    patient_first_rung = policy.SILENCE_LADDER_SEC[0] * policy.RESTING_PATIENCE_MULTIPLIER
    probes = run_hours(sim, int(patient_first_rung // HOUR) + 1)

    assert probes, "쉬는 중이어도 결국은 확인해야 한다"


# ── 시나리오 4: 무응답 → 사다리 소진 → T1 ─────────────────────────────────


def test_no_response_climbs_the_ladder_then_escalates(frozen_clock):
    """(시나리오 4 · 완료 조건 2) 끝까지 응답이 없으면 T1 이 outbox 에 적재된다.

    프로브가 세 단계로 올라가고, 그래도 응답이 없으면 보호자를 부른다.
    """
    sim = start_day(frozen_clock)

    # 사다리 전체를 넘기기에 충분한 시간.
    total = sum(policy.SILENCE_LADDER_SEC)
    probes = run_hours(sim, int(total // HOUR) + 2)

    levels = sorted(p["meta"]["probe_level"] for p in probes)
    assert levels == [1, 2, 3], f"세 단계가 순서대로 나가야 한다: {levels}"

    assert outbox.pending_count() == 1, "T1 이 큐에 적재되어야 한다"


def test_escalation_payload_carries_the_weak_signals(frozen_clock):
    """에스컬레이션은 단일 임계치가 아니라 여러 약한 신호의 조합이다.

    판단 근거를 알림에 실어야 보호자와 사후 튜닝이 볼 수 있다.
    """
    import json

    sim = start_day(frozen_clock)
    run_hours(sim, int(sum(policy.SILENCE_LADDER_SEC) // HOUR) + 2)

    row = outbox.outbox_db().execute(
        "SELECT tier, payload FROM outbox WHERE status = 'PENDING'").fetchone()
    payload = json.loads(row["payload"])

    assert row["tier"] == "T1"
    assert payload["reason"] == "no_response"
    assert payload["probes_failed"] == len(policy.SILENCE_LADDER_SEC)
    assert payload["occupancy"] == "HOME"
    assert payload["rest_state"] == "AWAKE"
    assert payload["silence_sec"] > 0


def test_response_resets_the_ladder(frozen_clock):
    """어르신이 대답하면 사다리가 처음으로 돌아간다.

    발화는 가장 강력한 생존 증거다.
    """
    sim = start_day(frozen_clock)
    run_hours(sim, 4)
    assert runtime_store.load(SENIOR)["silence_level"] >= 1

    runtime_store.reset_silence(SENIOR)
    proposals.clear(SENIOR)

    probes = run_hours(sim, 2)

    assert probes == [], "리셋 직후에는 다시 조용해도 이르다"
    assert runtime_store.load(SENIOR)["silence_level"] == 0


def test_same_rung_does_not_probe_twice(frozen_clock):
    """같은 칸에서 프로브를 반복하지 않는다.

    틱이 1분마다 도는데 칸마다 한 번만 물어야 한다. 안 그러면 3시간이 지난
    순간부터 1분마다 "점심 드셨어요?"가 나간다.
    """
    sim = start_day(frozen_clock)

    # 1칸(3시간)을 막 넘긴 지점. 다음 칸까지는 45분 남아 있다.
    sim.advance(policy.SILENCE_LADDER_SEC[0] + 60)
    ticks.silence_tick(SENIOR, None)
    first = _ladder_probes()
    assert len(first) == 1, "1칸에서 프로브 하나"

    # 같은 칸에 머무는 동안(다음 임계치 전까지) 틱을 여러 번 더 돌린다.
    for _ in range(10):
        sim.advance(60)
        ticks.silence_tick(SENIOR, None)

    assert len(_ladder_probes()) == 1, "같은 칸에서는 더 묻지 않는다"


def _ladder_probes() -> list[dict]:
    return [
        p for p in proposals.pending(SENIOR)
        if p.get("origin", "").startswith("silence_ladder")
    ]


# ── UNKNOWN 함정 ───────────────────────────────────────────────────────────


def test_unknown_occupancy_still_runs_the_ladder(frozen_clock):
    """★ UNKNOWN 은 '예상된 부재'가 아니다.

    현관 노드가 죽으면 occupancy 가 UNKNOWN 으로 강등된다. 그때 사다리를 멈추면
    라즈베리파이 하나가 죽은 것만으로 안전 감시가 통째로 꺼지고, 아무도 그 사실을
    모른다. 이 설계가 피하려는 바로 그 조용한 실패다.
    """
    sim = start_day(frozen_clock, occupancy="UNKNOWN")

    probes = run_hours(sim, 4)

    assert probes, "UNKNOWN 이면 보수적으로 가동해야 한다"


def test_away_and_unknown_behave_differently(frozen_clock):
    """AWAY 는 정지, UNKNOWN 은 가동. 둘을 같게 다루면 안 된다."""
    away = start_day(frozen_clock, occupancy="AWAY")
    assert run_hours(away, 4) == []

    db.close_all()
    proposals.clear(SENIOR)
    unknown = start_day(frozen_clock, occupancy="UNKNOWN")
    assert run_hours(unknown, 4)


# ── quiet hours ────────────────────────────────────────────────────────────


def test_night_silence_is_sleep_not_a_warning(frozen_clock):
    """새벽 4시의 침묵은 경고 신호가 아니라 수면이다.

    게이트와 '같은' 창을 쓴다. 두 곳이 어긋나면 로봇이 조용해야 할 때 프로브를
    던지거나, 반대로 낮에 감시를 쉰다.
    """
    # 서울 23:00 에 마지막 대화. 그 뒤로 새벽 내내 조용하다.
    sim = frozen_clock(start=MORNING_UTC + 14 * HOUR)  # 서울 23:00
    context_cache.save(SENIOR, SEOUL_PROFILE)
    runtime_store.save(
        SENIOR,
        last_user_interaction_at=MORNING_UTC + 14 * HOUR,
        occupancy="HOME", rest_state="AWAKE", silence_level=0,
    )

    probes = run_hours(sim, 7)  # 서울 06:00 까지

    assert probes == [], "밤중에는 프로브를 던지지 않는다"


def test_morning_after_a_quiet_night_resumes_monitoring(frozen_clock):
    """아침이 되면 다시 감시한다. 밤새 조용했다고 봐주지 않는다."""
    sim = frozen_clock(start=MORNING_UTC + 14 * HOUR)  # 서울 23:00
    context_cache.save(SENIOR, SEOUL_PROFILE)
    runtime_store.save(
        SENIOR,
        last_user_interaction_at=MORNING_UTC + 14 * HOUR,
        occupancy="HOME", rest_state="AWAKE", silence_level=0,
    )

    probes = run_hours(sim, 10)  # 서울 09:00 까지 (quiet hours 는 07:00 종료)

    assert probes, "아침이 되면 확인해야 한다"


# ── 부팅 직후 ──────────────────────────────────────────────────────────────


def test_fresh_boot_does_not_probe_immediately(frozen_clock):
    """상호작용 기록이 없으면 사다리를 돌리지 않는다.

    켜자마자 "괜찮으세요?"를 묻는 로봇이 되면 안 된다.
    """
    sim = frozen_clock(start=MORNING_UTC)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    # last_user_interaction_at 을 세팅하지 않는다 (기본값 0).
    runtime_store.save(SENIOR, occupancy="HOME", rest_state="AWAKE")

    assert run_hours(sim, 6) == []


# ── 캐시 오디오 경고 ───────────────────────────────────────────────────────


def test_critical_probe_warns_when_cached_audio_is_missing(frozen_clock, caplog):
    """★ critical 프로브에 캐시 오디오가 없으면 요란하게 남긴다.

    네트워크 없이 동작해야 하고, 그게 바로 이 프로브가 가장 중요한 상황이다.
    없는 채로 조용히 넘어가면 정작 필요할 때 말을 못 한다.
    """
    import logging

    sim = start_day(frozen_clock)

    with caplog.at_level(logging.WARNING):
        run_hours(sim, int(sum(policy.SILENCE_LADDER_SEC[:2]) // HOUR) + 2)

    assert any("cached audio" in record.getMessage() for record in caplog.records)


def test_cached_audio_present_produces_no_warning(frozen_clock, caplog):
    """미리 렌더링해 두면 경고가 사라진다."""
    import logging

    from bomi_ai_chat.localstore import audio_cache

    sim = start_day(frozen_clock)
    audio_cache.register("probe.critical.1", b"RIFF-fake", "어르신, 대답 좀 해주세요.")

    with caplog.at_level(logging.WARNING):
        run_hours(sim, int(sum(policy.SILENCE_LADDER_SEC[:2]) // HOUR) + 2)

    assert not any("cached audio" in record.getMessage() for record in caplog.records)
