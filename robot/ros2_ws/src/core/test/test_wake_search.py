"""wake_search 노드의 순수 판단 함수를 검증한다."""

import json

from std_msgs.msg import String

from core.wake_search import WakeSearchNode, is_person_currently_visible


def test_visible_when_tracking_fresh_and_after_search_start() -> None:
    assert is_person_currently_visible(
        vision_tracking=True,
        vision_stamp_sec=10.0,
        now_sec=10.5,
        vision_timeout_sec=2.0,
        search_started_at_sec=9.0,
    )


def test_not_visible_when_not_tracking() -> None:
    assert not is_person_currently_visible(
        vision_tracking=False,
        vision_stamp_sec=10.0,
        now_sec=10.5,
        vision_timeout_sec=2.0,
        search_started_at_sec=9.0,
    )


def test_not_visible_when_result_is_stale() -> None:
    assert not is_person_currently_visible(
        vision_tracking=True,
        vision_stamp_sec=10.0,
        now_sec=13.0,
        vision_timeout_sec=2.0,
        search_started_at_sec=9.0,
    )


def test_not_visible_when_result_predates_search_start() -> None:
    # 웨이크워드를 부르기 전부터 남아있던 결과 — 최신이어도 무시해야 한다.
    assert not is_person_currently_visible(
        vision_tracking=True,
        vision_stamp_sec=10.0,
        now_sec=10.5,
        vision_timeout_sec=2.0,
        search_started_at_sec=10.1,
    )


# ── 도착 후 정지 (2026-08-09 실기: 대화 중 앞에서 깔짝거림) ──────────────────


def _status(payload: dict) -> String:
    message = String()
    message.data = json.dumps(payload)
    return message


def _status_node() -> WakeSearchNode:
    node = object.__new__(WakeSearchNode)
    node._pending_resume = False
    node._pending_arrived = False
    return node


def test_arrival_status_requests_stopping_the_follow() -> None:
    node = _status_node()

    node._on_follow_status(
        _status({"state": "arrived", "reason": "person_too_close"}))

    assert node._pending_arrived is True
    assert node._pending_resume is False


def test_lost_status_requests_resuming_the_search() -> None:
    node = _status_node()

    node._on_follow_status(
        _status({"state": "waiting_target", "reason": "target_lost_timeout"}))

    assert node._pending_resume is True
    assert node._pending_arrived is False


def test_other_status_changes_nothing() -> None:
    node = _status_node()

    node._on_follow_status(
        _status({"state": "following", "reason": "target_confirmed"}))

    assert node._pending_resume is False
    assert node._pending_arrived is False
