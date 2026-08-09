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


# ── 중복 시작 무시 (2026-08-09 실기: FOLLOW_START 가 힌트를 날림) ────────────


class _FakeLogger:
    def info(self, _message: str) -> None:
        pass

    def error(self, _message: str) -> None:
        pass


class _FakePolicy:
    def __init__(self, active: bool) -> None:
        self.is_active = active
        self.started = False

    def start(self, *_args, **_kwargs):
        self.started = True
        raise AssertionError("중복 시작이 정책까지 내려갔습니다.")


def _debounce_node(*, active: bool, started_at: float) -> WakeSearchNode:
    node = object.__new__(WakeSearchNode)
    node._policy = _FakePolicy(active)
    node._start_debounce_sec = 3.0
    node._search_started_at_sec = started_at
    node.get_logger = lambda: _FakeLogger()
    return node


def test_duplicate_start_within_debounce_is_ignored() -> None:
    """★ UDP 로 이미 시작했는데 FOLLOW_START 가 뒤따라오면 힌트를 잃는다."""
    node = _debounce_node(active=True, started_at=100.0)

    node._begin_search(100.5)

    assert node._policy.started is False
    # 시작 시각을 갱신하지 않아야 원래 탐색의 기준이 유지된다.
    assert node._search_started_at_sec == 100.0


def _reaches_odom_check(node: WakeSearchNode, now: float) -> bool:
    """중복 판정을 통과해 실제 시작 절차까지 갔는지 확인한다."""
    reached = []
    node._odom_is_fresh = lambda _now: reached.append(True) or False
    node._publish_follow_enable = lambda _enable: None
    node._begin_search(now)
    return bool(reached)


def test_start_is_allowed_once_the_debounce_passes() -> None:
    node = _debounce_node(active=True, started_at=100.0)

    # 3초를 넘겼으므로 중복이 아니다.
    assert _reaches_odom_check(node, 105.0) is True


def test_start_is_allowed_when_no_search_is_running() -> None:
    node = _debounce_node(active=False, started_at=100.0)

    assert _reaches_odom_check(node, 100.1) is True
