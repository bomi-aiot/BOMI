"""능동 발화 게이트 검증 — "말하지 않기로 정하는 것도 기능이다".

이 파일이 검증하는 완료 조건
    1. quiet hours 에 medium 이 연기되고 critical 은 통과한다
    2. 쿨다운 중 ambient 가 막힌다
    3. 후보가 전부 탈락하면 emit 에 도달하지 않는다 (침묵 경로)

특히 공들인 곳
    is_quiet_hours 는 의도된 함정이다. 창이 자정을 넘고(22:00~07:00), 시각이
    로컬이다. naive 비교는 하필 밤새도록 틀린다. §자정 참고.

참고
    CLAUDE.md §7 (게이트와 우선순위 행렬), §22 4단계
"""

import pytest
from langgraph.graph import END

from bomi_ai_chat import policy
from bomi_ai_chat.graph import gate
from bomi_ai_chat.localstore import db

SENIOR = "senior-1"

# 서울 기준 22:00~07:00. 백엔드 문맥 API 가 주는 모양 그대로.
SEOUL_PROFILE = {
    "timeZone": "Asia/Seoul",
    "quietHoursStart": "22:00",
    "quietHoursEnd": "07:00",
}

# 2026-08-01 은 토요일. UTC 기준 자정이 서울 09:00 이다.
UTC_MIDNIGHT_2026_08_01 = 1785542400.0
HOUR = 3600.0


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()


def state_at(seoul_hour: float, **overrides):
    """서울 기준 특정 시각의 state 를 만든다."""
    # UTC 자정 = 서울 09:00 이므로, 서울 h 시는 UTC 자정 + (h - 9) 시간.
    return {
        "senior_id": SENIOR,
        "ctx": {"profile": SEOUL_PROFILE},
        **overrides,
    }, UTC_MIDNIGHT_2026_08_01 + (seoul_hour - 9) * HOUR


def proposal(priority, intent="companion", **extra):
    return {"intent": intent, "priority": priority, "seed": "...", **extra}


# ── quiet hours: 자정을 넘는 창 ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("seoul_hour", "expected", "why"),
    [
        (23.0, True, "자정 전 — 창 안"),
        (2.0, True, "자정 후 — 창 안. naive 비교가 틀리는 지점"),
        (6.5, True, "종료 직전 — 창 안"),
        (7.0, False, "종료 시각 — 창 밖(end 는 미포함)"),
        (12.0, False, "한낮 — 창 밖"),
        (21.9, False, "시작 직전 — 창 밖"),
        (22.0, True, "시작 시각 — 창 안(start 포함)"),
    ],
)
def test_quiet_hours_handles_window_crossing_midnight(
    frozen_clock, seoul_hour, expected, why
):
    """★ 22:00~07:00 처럼 자정을 넘는 창을 올바로 판정한다.

    단순한 `start <= now <= end` 는 이 창에서 '항상 False' 가 되고, 하필
    밤새도록 틀린다. 가장 중요한 시간대에서만 틀리는 버그다.
    """
    state, epoch = state_at(seoul_hour)
    frozen_clock(start=epoch)

    assert gate.is_quiet_hours(state) is expected, why


def test_quiet_hours_uses_the_seniors_local_time_not_utc(frozen_clock):
    """★ clock.now() 는 UTC 다. 변환하지 않으면 시간대만큼 통째로 어긋난다.

    같은 순간이라도 서울에서는 새벽 2시(조용), UTC 로는 전날 17시(안 조용)다.
    """
    _state, epoch = state_at(2.0)  # 서울 02:00 = UTC 17:00 (전날)
    frozen_clock(start=epoch)

    seoul = {"ctx": {"profile": SEOUL_PROFILE}}
    utc = {"ctx": {"profile": {**SEOUL_PROFILE, "timeZone": "UTC"}}}

    assert gate.is_quiet_hours(seoul) is True, "서울은 새벽 2시라 조용해야 한다"
    assert gate.is_quiet_hours(utc) is False, "UTC 로는 17시라 조용하지 않다"


def test_daytime_nap_window_that_does_not_cross_midnight(frozen_clock):
    """자정을 넘지 않는 평범한 창도 동작한다 (예: 13:00~15:00 낮잠)."""
    _state, epoch = state_at(14.0)
    frozen_clock(start=epoch)
    state = {"ctx": {"profile": {
        "timeZone": "Asia/Seoul", "quietHoursStart": "13:00", "quietHoursEnd": "15:00",
    }}}

    assert gate.is_quiet_hours(state) is True


def test_missing_quiet_hours_does_not_block_speech(frozen_clock):
    """창을 모르면 막지 않는다.

    막는 쪽을 고르면 프로필이 안 온 어르신에게는 능동 발화가 영원히 안 나간다.
    복약 알림이 조용히 사라지는 것이 새벽에 한 번 울리는 것보다 나쁘다.
    """
    frozen_clock(start=UTC_MIDNIGHT_2026_08_01)

    assert gate.is_quiet_hours({"ctx": {}}) is False
    assert gate.is_quiet_hours({"ctx": {"profile": {"timeZone": "Asia/Seoul"}}}) is False


def test_unparsable_quiet_hours_does_not_crash(frozen_clock):
    """깨진 값에 게이트가 죽지 않는다. 게이트가 죽으면 능동 발화 전체가 멈춘다."""
    frozen_clock(start=UTC_MIDNIGHT_2026_08_01)
    state = {"ctx": {"profile": {
        "timeZone": "Asia/Seoul", "quietHoursStart": "밤", "quietHoursEnd": "아침",
    }}}

    assert gate.is_quiet_hours(state) is False


# ── 완료 조건 1: quiet hours 에 medium 연기, critical 통과 ─────────────────


def test_quiet_hours_defers_medium_but_critical_passes(frozen_clock):
    """(완료 조건 1) 새벽 3시에 복약 알림은 미루고, 생존 확인은 통과시킨다."""
    state, epoch = state_at(3.0, proposals=[
        proposal("medium", intent="schedule"),
        proposal("critical"),
    ])
    frozen_clock(start=epoch)

    result = gate.proactive_gate(state)

    assert result["gate_decision"] == "speak"
    assert result["speech_priority"] == "critical", "critical 만 살아남아야 한다"


def test_quiet_hours_alone_with_medium_produces_silence(frozen_clock):
    """새벽에 복약 알림 하나뿐이면 침묵한다. 연기이지 폐기가 아니다."""
    state, epoch = state_at(3.0, proposals=[proposal("medium", intent="schedule")])
    frozen_clock(start=epoch)

    assert gate.proactive_gate(state)["gate_decision"] == "silent"


def test_door_greeting_at_night_passes_but_terse(frozen_clock):
    """★ 게이트에서 결과가 '차단'도 '통과'도 아닌 유일한 지점.

    새벽 2시 귀가에 아무 말도 안 하면 냉정하고 약간 으스스하다. 낮처럼 길게
    인사하면 시끄럽다. 그래서 짧게 통과시킨다.
    """
    state, epoch = state_at(2.0, proposals=[proposal("event", intent="greeting")])
    frozen_clock(start=epoch)

    result = gate.proactive_gate(state)

    assert result["gate_decision"] == "speak"
    assert result["terse"] is True


def test_same_greeting_in_daytime_is_not_terse(frozen_clock):
    state, epoch = state_at(14.0, proposals=[proposal("event", intent="greeting")])
    frozen_clock(start=epoch)

    result = gate.proactive_gate(state)

    assert result["gate_decision"] == "speak"
    assert result["terse"] is False


# ── 완료 조건 2: 쿨다운 중 ambient 차단 ────────────────────────────────────


def test_cooldown_blocks_ambient_but_not_high(frozen_clock):
    """(완료 조건 2) 방금 말했으면 잡담은 막고, 인슐린은 통과시킨다."""
    _state, epoch = state_at(14.0)
    frozen_clock(start=epoch)
    just_spoke = epoch - 60  # 1분 전에 말했다

    ambient_only = {
        "senior_id": SENIOR, "ctx": {"profile": SEOUL_PROFILE},
        "last_spoke_at": just_spoke, "proposals": [proposal("ambient")],
    }
    with_high = {
        "senior_id": SENIOR, "ctx": {"profile": SEOUL_PROFILE},
        "last_spoke_at": just_spoke,
        "proposals": [proposal("ambient"), proposal("high", intent="schedule")],
    }

    assert gate.proactive_gate(ambient_only)["gate_decision"] == "silent"
    assert gate.proactive_gate(with_high)["speech_priority"] == "high"


def test_cooldown_expires(frozen_clock):
    """쿨다운이 지나면 잡담도 통과한다."""
    _state, epoch = state_at(14.0)
    frozen_clock(start=epoch)
    state = {
        "senior_id": SENIOR, "ctx": {"profile": SEOUL_PROFILE},
        "last_spoke_at": epoch - policy.COOLDOWN_SEC - 1,
        "proposals": [proposal("ambient")],
    }

    assert gate.proactive_gate(state)["gate_decision"] == "speak"


def test_never_spoken_is_not_in_cooldown(frozen_clock):
    """방금 부팅했으면 식힐 것이 없다."""
    frozen_clock(start=UTC_MIDNIGHT_2026_08_01)

    assert gate.is_in_cooldown({"last_spoke_at": 0.0}) is False


# ── 완료 조건 3: 전원 탈락 → 침묵 (emit 미도달) ────────────────────────────


def test_all_proposals_rejected_reaches_end_not_emit(frozen_clock):
    """(완료 조건 3) 아무도 못 살아남으면 END 로 직행한다.

    이것이 '침묵도 기능'을 LangGraph 로 표현하는 방식이다. 빈 응답을 나중에
    걸러내는 게 아니라, emit 에 애초에 도달하지 않는다.
    """
    state, epoch = state_at(3.0, proposals=[
        proposal("ambient"), proposal("low"), proposal("medium"),
    ])
    frozen_clock(start=epoch)

    result = gate.proactive_gate(state)

    assert result["gate_decision"] == "silent"
    assert gate.route_gate(result) == END, "emit 이 아니라 END 로 가야 한다"
    assert "user_input" not in result, "말할 내용을 만들지 않는다"


def test_empty_queue_is_silence_not_an_error(frozen_clock):
    """제안이 없는 것은 정상이다. 대부분의 틱이 이렇다."""
    state, epoch = state_at(14.0, proposals=[])
    frozen_clock(start=epoch)

    assert gate.proactive_gate(state)["gate_decision"] == "silent"


def test_speaking_route_goes_to_context_read(frozen_clock):
    state, epoch = state_at(14.0, proposals=[proposal("medium")])
    frozen_clock(start=epoch)

    result = gate.proactive_gate(state)

    assert gate.route_gate(result) == "context_read"


# ── 게이트 1: 폐기와 연기의 구분 ───────────────────────────────────────────


def test_expired_greeting_is_discarded_not_deferred(frozen_clock):
    """시간을 놓친 인사는 버린다. 10분 뒤의 "어서오세요"는 침묵보다 나쁘다."""
    state, epoch = state_at(14.0)
    frozen_clock(start=epoch)
    expired = proposal("event", intent="greeting", expires_at=epoch - 1)

    assert gate.is_still_valid(expired, state) is False


def test_medication_without_ttl_survives_to_be_deferred(frozen_clock):
    """복약 알림은 TTL 이 없다. 사라지는 대신 나중에 다시 와야 한다."""
    state, epoch = state_at(14.0)
    frozen_clock(start=epoch)

    assert gate.is_still_valid(proposal("medium", intent="schedule"), state) is True


def test_completed_slot_invalidates_its_pending_reminder(frozen_clock):
    """★ 8시 55분에 "약 먹었어" → 9시 알림이 폐기된다.

    이게 없으면 이미 먹은 약을 다시 알리는 잔소리꾼이 된다.
    """
    from bomi_ai_chat.localstore import proposals as store

    state, epoch = state_at(8.9)
    frozen_clock(start=epoch)
    pending = proposal("medium", intent="schedule", meta={"slot_key": "2026-08-01:med:0900"})

    assert gate.is_still_valid(pending, state) is True

    store.mark_slot_completed(SENIOR, "2026-08-01:med:0900")

    assert gate.is_still_valid(pending, state) is False


def test_proposal_without_slot_key_is_not_invalidated(frozen_clock):
    """슬롯 키가 없는 제안은 무효화 대상이 아니다.

    무엇이 충족을 뜻하는지 정의되지 않았고, 정의 없이 지우면 조용히 사라지는
    발화가 생긴다.
    """
    state, epoch = state_at(14.0)
    frozen_clock(start=epoch)

    assert gate.is_still_valid(proposal("ambient"), state) is True


# ── 게이트 4: 끼어들기 ─────────────────────────────────────────────────────


def test_busy_room_defers_low_priority_but_not_critical(frozen_clock):
    """TV 소리인지 진짜 대화인지 구분할 수 없다. 애매하면 잡담은 미루고 critical 은 통과."""
    _state, epoch = state_at(14.0)
    frozen_clock(start=epoch)
    busy = {"someone_speaking": True}

    low = {
        "senior_id": SENIOR, "ctx": {"profile": SEOUL_PROFILE},
        "audio_ctx": busy, "proposals": [proposal("low")],
    }
    critical = {
        "senior_id": SENIOR, "ctx": {"profile": SEOUL_PROFILE},
        "audio_ctx": busy, "proposals": [proposal("critical")],
    }

    assert gate.proactive_gate(low)["gate_decision"] == "silent"
    assert gate.proactive_gate(critical)["gate_decision"] == "speak"


# ── 우선순위 중재 ──────────────────────────────────────────────────────────


def test_exactly_one_proposal_wins(frozen_clock):
    """한 턴에 정확히 하나. 두 가지를 한 번에 말하면 듣는 사람은 둘 다 기억 못 한다."""
    state, epoch = state_at(14.0, proposals=[
        proposal("ambient"), proposal("low"), proposal("high", intent="schedule"),
    ])
    frozen_clock(start=epoch)

    result = gate.proactive_gate(state)

    assert result["speech_priority"] == "high"
    assert result["intent"] == "schedule"


def test_winner_carries_origin_for_after_the_fact_audit(frozen_clock):
    """"왜 로봇이 새벽 3시에 말했는가"에 답할 수 있어야 한다."""
    state, epoch = state_at(3.0, proposals=[
        proposal("critical", origin="silence_ladder:3"),
    ])
    frozen_clock(start=epoch)

    assert gate.proactive_gate(state)["speech_origin"] == "silence_ladder:3"


def test_priority_behaviour_comes_from_the_policy_table(frozen_clock):
    """게이트 루프가 아니라 표가 동작을 정한다.

    이 테스트가 깨지면 누군가 게이트에 우선순위 예외를 넣은 것이다.
    """
    _state, epoch = state_at(3.0)  # quiet hours
    frozen_clock(start=epoch)

    for priority, expected in [
        ("critical", "speak"), ("high", "speak"),
        ("event", "speak"), ("clarification", "silent"),
        ("medium", "silent"), ("low", "silent"), ("ambient", "silent"),
    ]:
        state = {
            "senior_id": SENIOR, "ctx": {"profile": SEOUL_PROFILE},
            "proposals": [proposal(priority)],
        }
        assert gate.proactive_gate(state)["gate_decision"] == expected, (
            f"{priority} 의 quiet hours 동작이 policy.PRIORITY_POLICY 와 다르다")
