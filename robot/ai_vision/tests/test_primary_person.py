"""대표 인물 선택 검증 — 카메라도 모델도 없이 실행한다.

이 파일이 지키는 것 (구현계획 결정 9)
    1. 꺼져 있으면 목록을 1비트도 건드리지 않는다 (기존 안전 동작 보존).
    2. 조건을 통과한 후보가 없으면 대상을 만들어 내지 않는다.
    3. 한 번 고른 사람은 화면에 남아 있는 동안 바뀌지 않는다 (히스테리시스).
"""

from bomi_vision.domain import TrackedPerson
from bomi_vision.primary_person import (
    PrimaryPersonConfig,
    PrimaryPersonSelector,
)
import pytest


FRAME_W = 640
FRAME_H = 480


def person(track_id: int, center_x: float, *, confidence: float = 0.9,
           height: float = 300.0) -> TrackedPerson:
    """가로 중심과 높이만 지정해 추적 결과 하나를 만든다."""
    half_width = 60.0
    top = (FRAME_H - height) / 2.0
    return TrackedPerson(
        track_id=track_id,
        confidence=confidence,
        x1=center_x - half_width,
        y1=top,
        x2=center_x + half_width,
        y2=top + height,
    )


def _selector(**overrides) -> PrimaryPersonSelector:
    defaults = {"enabled": True, "min_confidence": 0.5}
    defaults.update(overrides)
    return PrimaryPersonSelector(PrimaryPersonConfig(**defaults))


def _ids(people) -> list[int]:
    return [p.track_id for p in people]


# ── 꺼져 있을 때는 아무것도 하지 않는다 ──────────────────────────────────────


def test_disabled_returns_the_list_untouched() -> None:
    selector = PrimaryPersonSelector()  # 기본값 = 꺼짐
    people = [person(1, 100.0), person(2, 320.0)]

    result = selector.select(people, FRAME_W, FRAME_H)

    assert result is people
    assert selector.locked_track_id is None


def test_default_config_is_disabled() -> None:
    # 기본값이 켜져 있으면 아무도 모르게 안전 규칙이 헐거워진다.
    assert PrimaryPersonConfig().enabled is False


# ── 고를 것이 없을 때 ───────────────────────────────────────────────────────


def test_empty_list_passes_through() -> None:
    selector = _selector()
    assert list(selector.select([], FRAME_W, FRAME_H)) == []


def test_single_person_passes_through_and_locks() -> None:
    selector = _selector()
    people = [person(7, 100.0)]

    result = selector.select(people, FRAME_W, FRAME_H)

    assert result is people
    assert selector.locked_track_id == 7


# ── 여러 명일 때 중앙을 고른다 ───────────────────────────────────────────────


def test_picks_the_person_closest_to_the_center() -> None:
    selector = _selector()
    people = [person(1, 60.0), person(2, 330.0), person(3, 600.0)]

    result = selector.select(people, FRAME_W, FRAME_H)

    assert _ids(result) == [2]
    assert selector.locked_track_id == 2


def test_confidence_only_filters_it_does_not_choose() -> None:
    # 중앙 사람의 신뢰도가 낮아도(문턱은 넘음) 가장자리의 높은 사람을 이긴다.
    selector = _selector(min_confidence=0.5)
    people = [
        person(1, 60.0, confidence=0.99),
        person(2, 325.0, confidence=0.61),
    ]

    assert _ids(selector.select(people, FRAME_W, FRAME_H)) == [2]


def test_low_confidence_people_are_dropped_from_the_candidates() -> None:
    selector = _selector(min_confidence=0.7)
    people = [
        person(1, 320.0, confidence=0.4),   # 중앙이지만 문턱 미만
        person(2, 500.0, confidence=0.9),
    ]

    assert _ids(selector.select(people, FRAME_W, FRAME_H)) == [2]


def test_people_who_are_too_far_away_are_dropped() -> None:
    # 화면에서 작게 보이는 사람 = 멀리 있는 사람. 복도 끝 행인을 뺀다.
    selector = _selector(min_height_ratio=0.3)
    people = [
        person(1, 320.0, height=60.0),    # 중앙이지만 12.5% 로 너무 작다
        person(2, 500.0, height=300.0),   # 62.5%
    ]

    assert _ids(selector.select(people, FRAME_W, FRAME_H)) == [2]


def test_same_distance_prefers_the_closer_person() -> None:
    # 좌우 대칭이면 상자가 큰(가까운) 쪽. 안 그러면 프레임마다 뒤집힌다.
    selector = _selector()
    people = [person(1, 220.0, height=200.0), person(2, 420.0, height=400.0)]

    assert _ids(selector.select(people, FRAME_W, FRAME_H)) == [2]


# ── 후보가 하나도 없으면 대상을 만들지 않는다 ────────────────────────────────


def test_no_candidate_falls_back_to_the_original_safety_rule() -> None:
    # 전부 문턱 미만이면 원본을 그대로 돌려준다 → 하류가 "다중 인물"로 보고
    # 정지한다. 여기서 억지로 하나를 고르면 못 믿을 대상을 따라간다.
    selector = _selector(min_confidence=0.9)
    people = [person(1, 320.0, confidence=0.3), person(2, 100.0,
                                                      confidence=0.4)]

    result = selector.select(people, FRAME_W, FRAME_H)

    assert result is people
    assert selector.locked_track_id is None


# ── 히스테리시스 ────────────────────────────────────────────────────────────


def test_locked_person_wins_even_when_no_longer_centered() -> None:
    selector = _selector()
    selector.select([person(1, 320.0), person(2, 600.0)], FRAME_W, FRAME_H)
    assert selector.locked_track_id == 1

    # 1번이 옆으로 비켜도 계속 1번을 따라간다.
    result = selector.select(
        [person(1, 600.0), person(2, 320.0)], FRAME_W, FRAME_H)

    assert _ids(result) == [1]


def test_lock_moves_on_when_the_person_disappears() -> None:
    selector = _selector()
    selector.select([person(1, 320.0), person(2, 600.0)], FRAME_W, FRAME_H)

    result = selector.select(
        [person(2, 600.0), person(3, 300.0)], FRAME_W, FRAME_H)

    assert _ids(result) == [3]
    assert selector.locked_track_id == 3


def test_lock_is_dropped_when_the_person_falls_below_the_threshold() -> None:
    selector = _selector(min_confidence=0.6)
    selector.select([person(1, 320.0), person(2, 600.0)], FRAME_W, FRAME_H)

    # 1번의 신뢰도가 떨어지면 후보에서 빠지고 잠금도 옮겨간다.
    result = selector.select(
        [person(1, 320.0, confidence=0.2), person(2, 600.0)],
        FRAME_W, FRAME_H)

    assert _ids(result) == [2]


def test_reset_clears_the_lock() -> None:
    selector = _selector()
    selector.select([person(1, 320.0), person(2, 600.0)], FRAME_W, FRAME_H)

    selector.reset()

    assert selector.locked_track_id is None
    assert _ids(selector.select(
        [person(1, 600.0), person(2, 320.0)], FRAME_W, FRAME_H)) == [2]


def test_lock_clears_when_everyone_leaves() -> None:
    selector = _selector()
    selector.select([person(1, 320.0), person(2, 600.0)], FRAME_W, FRAME_H)

    selector.select([], FRAME_W, FRAME_H)

    assert selector.locked_track_id is None


# ── 설정 검증 ───────────────────────────────────────────────────────────────


def test_config_rejects_out_of_range_values() -> None:
    with pytest.raises(ValueError):
        PrimaryPersonConfig(min_confidence=1.5)
    with pytest.raises(ValueError):
        PrimaryPersonConfig(min_height_ratio=-0.1)
    with pytest.raises(ValueError):
        PrimaryPersonConfig(enabled="yes")  # type: ignore[arg-type]


def test_select_rejects_bad_frame_size() -> None:
    selector = _selector()
    with pytest.raises(ValueError):
        selector.select([person(1, 10.0)], 0, FRAME_H)
    with pytest.raises(ValueError):
        selector.select([person(1, 10.0)], FRAME_W, -1)


# ── 파이프라인 통합 ─────────────────────────────────────────────────────────
#
# 걸러진 목록이 상태 기계로, 걸러지기 전 목록이 화면으로 가야 한다. 반대로
# 배선하면 (1) 상태 기계가 여전히 "여러 명"으로 보고 멈추거나 (2) 화면에서
# 누가 후보에서 빠졌는지 볼 수 없다.


class _FakeFrame:
    shape = (FRAME_H, FRAME_W, 3)


class _FakeCamera:
    def __init__(self, frames: int = 1) -> None:
        self._left = frames
        self.released = False

    def read(self) -> _FakeFrame:
        self._left -= 1
        return _FakeFrame()

    def release(self) -> None:
        self.released = True


class _FakeTracker:
    def __init__(self, people) -> None:
        self._people = people

    def track(self, frame):
        return self._people


class _FakeTrackingService:
    def __init__(self) -> None:
        self.seen = None

    def update(self, tracked_people, frame_width, frame_height):
        self.seen = list(tracked_people)
        return "tracking-result"


class _FakeFollowGenerator:
    def generate(self, result):
        return "follow-result"


class _FakeView:
    def __init__(self) -> None:
        self.seen = None
        self.closed = False

    def show(self, frame, tracked_people, result, follow_result) -> bool:
        self.seen = list(tracked_people)
        return False  # 한 프레임만 돌고 멈춘다

    def close(self) -> None:
        self.closed = True


def _run_once(selector):
    from bomi_vision.application import run_person_tracking

    people = [person(1, 60.0), person(2, 320.0), person(3, 600.0)]
    service, view, camera = (
        _FakeTrackingService(), _FakeView(), _FakeCamera())
    run_person_tracking(
        _FakeTracker(people), service, _FakeFollowGenerator(),
        camera, view, selector)
    assert camera.released and view.closed
    return service, view


def test_pipeline_sends_the_filtered_list_to_the_state_machine() -> None:
    service, view = _run_once(_selector())

    assert _ids(service.seen) == [2]        # 상태 기계는 한 명만 본다
    assert _ids(view.seen) == [1, 2, 3]     # 화면은 전부 보여 준다


def test_pipeline_is_unchanged_without_a_selector() -> None:
    service, view = _run_once(None)

    assert _ids(service.seen) == [1, 2, 3]
    assert _ids(view.seen) == [1, 2, 3]


def test_pipeline_is_unchanged_when_the_selector_is_off() -> None:
    service, _view = _run_once(PrimaryPersonSelector())

    assert _ids(service.seen) == [1, 2, 3]
