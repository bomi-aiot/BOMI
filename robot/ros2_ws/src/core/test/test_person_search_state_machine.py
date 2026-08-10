"""웨이포인트 사용자 탐색 상태 전환을 검증한다."""

import pytest

from core.person_search_state_machine import (
    PersonSearchState,
    PersonSearchStateMachine,
    parse_person_detection,
)


def test_same_person_must_remain_visible_before_nav2_cancel() -> None:
    """같은 track ID가 확정 시간 동안 유지돼야 취소 상태로 전환한다."""
    machine = PersonSearchStateMachine(target_confirm_sec=0.5)
    machine.start()
    first = machine.observe("tracking", 7, 10.0)
    early = machine.observe("tracking", 7, 10.49)
    confirmed = machine.observe("tracking", 7, 10.5)

    assert first.person_confirmed is False
    assert early.person_confirmed is False
    assert confirmed.person_confirmed is True
    assert confirmed.state == PersonSearchState.CANCELING_NAV2


def test_candidate_resets_when_person_disappears() -> None:
    """확정 전에 사람이 사라지면 이전 관측 시간을 이어 쓰지 않는다."""
    machine = PersonSearchStateMachine(target_confirm_sec=0.5)
    machine.start()
    machine.observe("tracking", 3, 1.0)
    machine.observe("not_detected", None, 1.4)
    decision = machine.observe("tracking", 3, 1.6)

    assert decision.reason == "candidate_started"
    assert decision.person_confirmed is False


def test_following_starts_only_after_nav2_cancel_confirmation() -> None:
    """사람 확정만으로는 추종을 켜지 않고 Nav2 취소 완료를 기다린다."""
    machine = PersonSearchStateMachine(target_confirm_sec=0.5)
    machine.start()
    machine.observe("tracking", 4, 2.0)
    machine.observe("tracking", 4, 2.5)

    assert machine.state == PersonSearchState.CANCELING_NAV2
    assert machine.nav2_cancelled().state == PersonSearchState.FOLLOWING


def test_one_patrol_pass_finishes_as_not_found() -> None:
    """모든 지점을 확인한 한 바퀴 탐색은 NOT_FOUND로 끝난다."""
    machine = PersonSearchStateMachine()
    machine.start()
    assert machine.complete_without_person().state == PersonSearchState.NOT_FOUND


def test_lost_person_can_start_another_patrol_after_following() -> None:
    """추종 복귀 후 다시 놓쳐도 새로운 순찰을 시작할 수 있어야 한다."""
    machine = PersonSearchStateMachine(target_confirm_sec=0.5)
    machine.start()
    machine.observe("tracking", 4, 2.0)
    machine.observe("tracking", 4, 2.5)
    machine.nav2_cancelled()

    restarted = machine.start()

    assert restarted.state == PersonSearchState.PATROLLING
    assert restarted.reason == "search_started"


def test_parse_person_detection_normalizes_status() -> None:
    """비전 메시지의 상태를 소문자로 정규화한다."""
    assert parse_person_detection('{"status":"TRACKING","track_id":8}') == (
        "tracking",
        8,
    )


@pytest.mark.parametrize("value", [True, -1, 1.2, "7"])
def test_parse_person_detection_rejects_invalid_track_id(value) -> None:
    """음이 아닌 정수가 아닌 track ID를 거부한다."""
    with pytest.raises(ValueError):
        parse_person_detection(f'{{"status":"tracking","track_id":{value!r}}}')
