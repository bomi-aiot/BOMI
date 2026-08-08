"""wake_search 노드의 순수 판단 함수를 검증한다."""

from core.wake_search import is_person_currently_visible


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
