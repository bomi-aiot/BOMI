"""회전 탐색 순수 로직 검증 — ROS 2 나 하드웨어 없이 실행한다.

각도 wrap-around(359° 다음이 0°)와 상태 전이는 실기에서 눈으로 잡기 어렵다.
여기서 막지 못하면 "로봇이 반대로 한 바퀴 돈다" 같은 증상으로만 드러난다.
"""

import math

from core.search_policy import (
    SearchConfig,
    SearchState,
    WakeSearchPolicy,
    angle_error,
    normalize_angle,
)
import pytest


TOLERANCE = 1e-6


def _config(**overrides) -> SearchConfig:
    """테스트용 설정 — 관찰 시간을 짧게 줄여 시뮬레이션을 빠르게 한다."""
    defaults = {
        "step_angle_deg": 40.0,
        "angular_speed": 0.6,
        "observe_duration_sec": 0.8,
        "sweep_limit_deg": 320.0,
        "goal_tolerance_deg": 3.0,
        "follow_timeout_sec": 60.0,
        "search_timeout_sec": 45.0,
    }
    defaults.update(overrides)
    return SearchConfig(**defaults)


# ── 각도 계산 ───────────────────────────────────────────────────────────────


def test_normalize_angle_folds_into_pi_range() -> None:
    assert normalize_angle(0.0) == pytest.approx(0.0)
    assert normalize_angle(math.radians(370.0)) == pytest.approx(
        math.radians(10.0), abs=TOLERANCE)
    assert normalize_angle(math.radians(-370.0)) == pytest.approx(
        math.radians(-10.0), abs=TOLERANCE)
    assert normalize_angle(math.radians(190.0)) == pytest.approx(
        math.radians(-170.0), abs=TOLERANCE)

    # 180도는 +pi 와 -pi 가 같은 방향이다. 이 구현은 [-pi, pi) 규약이라 -pi 를
    # 돌려준다 — 부호가 아니라 크기가 pi 인지만 확인한다.
    for value in (math.pi, -math.pi, 3.0 * math.pi):
        assert abs(normalize_angle(value)) == pytest.approx(math.pi)


def test_normalize_angle_rejects_non_finite() -> None:
    with pytest.raises(ValueError):
        normalize_angle(float("nan"))
    with pytest.raises(ValueError):
        normalize_angle(float("inf"))


def test_angle_error_takes_the_short_way_around() -> None:
    # 359도에서 1도로 가는 최단 경로는 +2도이지 -358도가 아니다.
    error = angle_error(math.radians(1.0), math.radians(359.0))
    assert error == pytest.approx(math.radians(2.0), abs=TOLERANCE)

    # 반대 방향도 같다.
    error = angle_error(math.radians(359.0), math.radians(1.0))
    assert error == pytest.approx(math.radians(-2.0), abs=TOLERANCE)


# ── 설정 검증 ───────────────────────────────────────────────────────────────


def test_config_rejects_tolerance_larger_than_step() -> None:
    # 허용 오차가 스텝보다 크면 즉시 "도착"이 되어 영원히 제자리에 머문다.
    with pytest.raises(ValueError):
        SearchConfig(step_angle_deg=5.0, goal_tolerance_deg=10.0)


def test_config_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError):
        SearchConfig(angular_speed=0.0)
    with pytest.raises(ValueError):
        SearchConfig(observe_duration_sec=-1.0)


def test_config_rejects_min_speed_above_speed() -> None:
    with pytest.raises(ValueError):
        SearchConfig(angular_speed=0.3, min_angular_speed=0.5)


# ── 시작 ────────────────────────────────────────────────────────────────────


def test_start_without_hint_observes_first() -> None:
    policy = WakeSearchPolicy(_config())
    decision = policy.start(0.0, 0.0, hint_deg=None)

    assert decision.state is SearchState.OBSERVE
    assert decision.angular_z == 0.0
    assert decision.follow_enable is None
    assert policy.is_active


def test_start_with_hint_turns_toward_the_sound() -> None:
    policy = WakeSearchPolicy(_config())
    decision = policy.start(0.0, 0.0, hint_deg=90.0)

    assert decision.state is SearchState.TURN_TO_HINT
    # 왼쪽(양수) 힌트이므로 반시계 방향으로 돈다.
    assert decision.angular_z > 0.0


def test_start_with_right_side_hint_turns_clockwise() -> None:
    policy = WakeSearchPolicy(_config())
    decision = policy.start(0.0, 0.0, hint_deg=-90.0)

    assert decision.angular_z < 0.0


def test_start_with_hint_already_in_front_skips_turning() -> None:
    policy = WakeSearchPolicy(_config())
    decision = policy.start(0.0, 0.0, hint_deg=1.0)

    assert decision.state is SearchState.OBSERVE
    assert decision.angular_z == 0.0


def test_start_hint_is_relative_to_the_current_heading() -> None:
    # 로봇이 이미 90도를 보고 있고 힌트가 +90도면 목표는 180도다.
    policy = WakeSearchPolicy(_config())
    policy.start(0.0, math.radians(90.0), hint_deg=90.0)

    # 180도에 도달하면 관찰로 넘어간다.
    decision = policy.update(0.1, math.radians(180.0), person_visible=False)
    assert decision.state is SearchState.OBSERVE


# ── 회전 → 관찰 → 스텝 ──────────────────────────────────────────────────────


def test_turn_completes_when_within_tolerance() -> None:
    policy = WakeSearchPolicy(_config())
    policy.start(0.0, 0.0, hint_deg=90.0)

    still_turning = policy.update(0.1, math.radians(45.0), person_visible=False)
    assert still_turning.state is SearchState.TURN_TO_HINT
    assert still_turning.angular_z > 0.0

    arrived = policy.update(0.2, math.radians(89.0), person_visible=False)
    assert arrived.state is SearchState.OBSERVE
    assert arrived.angular_z == 0.0


def test_observe_holds_still_until_the_duration_passes() -> None:
    policy = WakeSearchPolicy(_config(observe_duration_sec=1.0))
    policy.start(0.0, 0.0)

    mid = policy.update(0.5, 0.0, person_visible=False)
    assert mid.state is SearchState.OBSERVE
    assert mid.angular_z == 0.0

    after = policy.update(1.1, 0.0, person_visible=False)
    assert after.state is SearchState.STEP_TURN
    assert after.angular_z > 0.0


def test_step_turn_target_is_one_step_counter_clockwise() -> None:
    policy = WakeSearchPolicy(_config(observe_duration_sec=0.1))
    policy.start(0.0, 0.0)
    policy.update(0.2, 0.0, person_visible=False)  # OBSERVE -> STEP_TURN

    # 40도에 닿으면 한 스텝이 끝난다.
    decision = policy.update(0.3, math.radians(39.0), person_visible=False)
    assert decision.state is SearchState.OBSERVE
    assert policy.swept_deg == pytest.approx(40.0)


def test_slowdown_near_target_but_never_below_the_floor() -> None:
    config = _config(angular_speed=0.6, min_angular_speed=0.15,
                     slowdown_band_deg=15.0)
    policy = WakeSearchPolicy(config)
    policy.start(0.0, 0.0, hint_deg=90.0)

    far = policy.update(0.1, math.radians(0.0), person_visible=False)
    near = policy.update(0.2, math.radians(85.0), person_visible=False)

    assert far.angular_z == pytest.approx(0.6)
    assert 0.15 <= near.angular_z < 0.6


# ── 힌트 좌우 지그재그 ──────────────────────────────────────────────────────
# 2026-08-08 실기: 힌트가 있어도 못 찾으면 곧장 한 방향으로만 계속 돌아서
# 힌트를 무시하고 아무 데나 도는 것처럼 보였다. 힌트 좌우를 먼저 지그재그로
# 본 뒤에야 전체 회전으로 넘어가야 한다.


def test_local_search_zigzags_around_hint_then_falls_back_to_global_sweep() -> None:
    # 관찰 종료 시각(observe_until_sec)이 부동소수 덧셈으로 정확히 떨어지지
    # 않을 수 있어(예: 0.2+0.1), 다음 update 는 여유를 두고 부른다.
    policy = WakeSearchPolicy(_config(observe_duration_sec=0.1))
    policy.start(0.0, 0.0, hint_deg=90.0)
    policy.update(0.2, math.radians(90.0), person_visible=False)  # -> OBSERVE(힌트)

    # 1) 힌트 + 1스텝(오른쪽 반대편, +40 = 130도).
    step_1 = policy.update(0.35, math.radians(90.0), person_visible=False)
    assert step_1.state is SearchState.STEP_TURN
    assert step_1.reason == "local_search_step"
    obs_1 = policy.update(0.45, math.radians(130.0), person_visible=False)
    assert obs_1.state is SearchState.OBSERVE

    # 2) 힌트 - 1스텝(반대쪽, -40 = 50도).
    step_2 = policy.update(0.6, math.radians(130.0), person_visible=False)
    assert step_2.state is SearchState.STEP_TURN
    assert step_2.reason == "local_search_step"
    obs_2 = policy.update(0.7, math.radians(50.0), person_visible=False)
    assert obs_2.state is SearchState.OBSERVE

    # 3) 다음 지그재그(±2스텝=80도)는 local_search_range_deg(90)의 절반인
    #    45도를 넘는다 — 여기서부터 기존 전체 회전으로 넘어간다.
    step_3 = policy.update(0.85, math.radians(50.0), person_visible=False)
    assert step_3.state is SearchState.STEP_TURN
    assert step_3.reason == "stepping"
    assert policy.swept_deg == pytest.approx(0.0)  # 지그재그는 아직 안 셌다

    arrived = policy.update(0.95, math.radians(90.0), person_visible=False)
    assert arrived.state is SearchState.OBSERVE
    # 전체 회전으로 넘어간 뒤의 첫 스텝만 swept_deg 에 들어간다.
    assert policy.swept_deg == pytest.approx(40.0)


def test_local_search_range_smaller_than_step_skips_local_phase() -> None:
    # 절반 폭(20도)이 한 스텝(40도)보다 좁으면 지그재그를 한 번도 못 해보고
    # 곧장 전체 회전으로 넘어간다.
    policy = WakeSearchPolicy(
        _config(observe_duration_sec=0.1, local_search_range_deg=40.0))
    policy.start(0.0, 0.0, hint_deg=90.0)
    policy.update(0.2, math.radians(90.0), person_visible=False)  # -> OBSERVE(힌트)

    decision = policy.update(0.35, math.radians(90.0), person_visible=False)
    assert decision.reason == "stepping"


def test_local_search_is_skipped_entirely_without_a_hint() -> None:
    policy = WakeSearchPolicy(_config(observe_duration_sec=0.1))
    policy.start(0.0, 0.0)  # 힌트 없음 -> OBSERVE 부터 시작

    decision = policy.update(0.2, 0.0, person_visible=False)
    assert decision.reason == "stepping"


def test_resume_after_lost_never_repeats_the_local_search() -> None:
    policy = WakeSearchPolicy(_config())
    policy.start(0.0, 0.0, hint_deg=90.0)
    # 힌트 도착 직후 바로 찾았다 — 지그재그를 한 번도 안 썼다.
    policy.update(0.1, math.radians(90.0), person_visible=True)

    decision = policy.resume_after_lost(0.2, math.radians(90.0))

    assert decision.reason == "resuming_after_lost"


# ── 사람 발견 ───────────────────────────────────────────────────────────────


def test_person_found_stops_rotation_and_enables_follow() -> None:
    policy = WakeSearchPolicy(_config())
    policy.start(0.0, 0.0, hint_deg=90.0)

    decision = policy.update(0.1, math.radians(30.0), person_visible=True)

    assert decision.state is SearchState.FOLLOWING
    assert decision.angular_z == 0.0
    assert decision.follow_enable is True
    assert decision.finished is False


def test_following_does_not_publish_rotation() -> None:
    policy = WakeSearchPolicy(_config())
    policy.start(0.0, 0.0)
    policy.update(0.1, 0.0, person_visible=True)

    decision = policy.update(0.2, math.radians(10.0), person_visible=False)
    assert decision.state is SearchState.FOLLOWING
    assert decision.angular_z == 0.0


def test_following_ends_after_the_time_limit(  # noqa: D103
) -> None:
    policy = WakeSearchPolicy(_config(follow_timeout_sec=5.0))
    policy.start(0.0, 0.0)
    policy.update(0.1, 0.0, person_visible=True)

    before = policy.update(4.9, 0.0, person_visible=True)
    assert before.finished is False

    after = policy.update(5.2, 0.0, person_visible=True)
    assert after.finished is True
    assert after.follow_enable is False
    assert after.state is SearchState.FINISHED


# ── 추종 포기 후 재개 ────────────────────────────────────────────────────────
# person_follower 가 대상을 놓치고 완전히 포기(target_lost_timeout)했을 때
# wake_search 노드가 이 메서드를 부른다. 2026-08-08 실기: 엉뚱한 사람을
# 잠깐 락온했다가 놓쳤을 때 이 신호가 없어 FOLLOWING 에 영원히 멈춰 섰다.


def test_resume_after_lost_steps_from_the_current_heading() -> None:
    policy = WakeSearchPolicy(_config())
    policy.start(0.0, 0.0)
    policy.update(0.1, 0.0, person_visible=True)  # OBSERVE -> FOLLOWING

    decision = policy.resume_after_lost(0.2, math.radians(10.0))

    assert decision.state is SearchState.STEP_TURN
    assert decision.angular_z != 0.0
    assert decision.reason == "resuming_after_lost"


def test_resume_after_lost_is_a_no_op_outside_following() -> None:
    policy = WakeSearchPolicy(_config())
    policy.start(0.0, 0.0)  # OBSERVE, not FOLLOWING

    decision = policy.resume_after_lost(0.1, 0.0)

    # 이미 새 탐색이 시작됐거나 아직 시작 전인 상태를 그대로 돌려준다 —
    # 뒤늦게 도착한 신호가 진행 중인 상태를 건드리지 않는다.
    assert decision.state is SearchState.OBSERVE
    assert decision.angular_z == 0.0


def test_resume_after_lost_returns_when_sweep_budget_is_spent() -> None:
    config = _config(observe_duration_sec=0.1, sweep_limit_deg=40.0)
    policy = WakeSearchPolicy(config)
    policy.start(0.0, 0.0)
    policy.update(0.2, 0.0, person_visible=False)  # OBSERVE -> STEP_TURN
    # 스텝 회전을 끝까지 마쳐야 swept_rad 가 쌓인다(도중에 사람이 보이면
    # 그 자리에서 바로 FOLLOWING 으로 빠져 이번 스텝은 안 쌓인다).
    policy.update(0.3, math.radians(40.0), person_visible=False)  # -> OBSERVE
    policy.update(0.4, math.radians(40.0), person_visible=True)  # -> FOLLOWING
    assert policy.swept_deg == pytest.approx(40.0)

    decision = policy.resume_after_lost(0.5, math.radians(40.0))

    assert decision.state is SearchState.RETURNING
    assert decision.reason == "resumed_sweep_complete"


# ── 한 바퀴 → 복귀 ──────────────────────────────────────────────────────────


def _sweep_to_the_end(policy: WakeSearchPolicy) -> tuple[float, float]:
    """사람을 못 찾은 채 한 바퀴를 다 돌 때까지 시뮬레이션한다."""
    now = 0.0
    yaw = 0.0
    policy.start(now, yaw)
    step = math.radians(policy.config.step_angle_deg)

    for _ in range(400):
        now += 0.1
        decision = policy.update(now, yaw, person_visible=False)
        if decision.finished:
            break
        if decision.angular_z != 0.0:
            # 목표까지 한 번에 이동했다고 가정한다(각도 제어는 별도 테스트).
            yaw = normalize_angle(yaw + math.copysign(step, decision.angular_z))
        if policy.state is SearchState.RETURNING:
            yaw = 0.0
    return now, yaw


def test_full_sweep_returns_to_start_and_finishes() -> None:
    policy = WakeSearchPolicy(_config(observe_duration_sec=0.1))
    _sweep_to_the_end(policy)

    assert policy.state is SearchState.FINISHED
    # 320도 = 40도 x 8스텝. 관찰 지점 9곳으로 360도를 모두 덮는다.
    assert policy.swept_deg == pytest.approx(320.0)


def test_sweep_without_return_finishes_in_place() -> None:
    policy = WakeSearchPolicy(
        _config(observe_duration_sec=0.1, return_to_start=False))
    _sweep_to_the_end(policy)

    assert policy.state is SearchState.FINISHED


# ── 정지와 안전 ─────────────────────────────────────────────────────────────


def test_stop_always_turns_the_follow_switch_off() -> None:
    policy = WakeSearchPolicy(_config())
    policy.start(0.0, 0.0, hint_deg=90.0)

    decision = policy.stop("re_wake")

    assert decision.finished is True
    assert decision.angular_z == 0.0
    assert decision.follow_enable is False
    assert decision.reason == "re_wake"
    assert not policy.is_active


def test_stop_is_safe_to_call_twice() -> None:
    policy = WakeSearchPolicy(_config())
    policy.start(0.0, 0.0)
    policy.stop("first")
    second = policy.stop("second")

    assert second.finished is True
    assert second.follow_enable is False


def test_update_before_start_is_a_no_op() -> None:
    policy = WakeSearchPolicy(_config())
    decision = policy.update(0.0, 0.0, person_visible=True)

    assert decision.angular_z == 0.0
    assert decision.follow_enable is None
    assert decision.state is SearchState.IDLE


def test_search_timeout_triggers_return() -> None:
    policy = WakeSearchPolicy(_config(search_timeout_sec=2.0))
    policy.start(0.0, 0.0, hint_deg=170.0)

    decision = policy.update(2.5, 0.0, person_visible=False)
    assert decision.state is SearchState.RETURNING


def test_restart_resets_the_sweep_counter() -> None:
    policy = WakeSearchPolicy(_config(observe_duration_sec=0.1))
    policy.start(0.0, 0.0)
    policy.update(0.2, 0.0, person_visible=False)
    policy.update(0.3, math.radians(40.0), person_visible=False)
    assert policy.swept_deg > 0.0

    policy.start(10.0, math.radians(40.0))
    assert policy.swept_deg == pytest.approx(0.0)


def test_update_rejects_non_boolean_person_visible() -> None:
    policy = WakeSearchPolicy(_config())
    policy.start(0.0, 0.0)
    with pytest.raises(ValueError):
        policy.update(0.1, 0.0, person_visible="yes")  # type: ignore[arg-type]


def test_update_rejects_non_finite_yaw() -> None:
    policy = WakeSearchPolicy(_config())
    policy.start(0.0, 0.0)
    with pytest.raises(ValueError):
        policy.update(0.1, float("nan"), person_visible=False)
