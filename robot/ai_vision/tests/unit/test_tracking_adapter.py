"""Ultralytics 객체 없이 ByteTrack 후보의 도메인 변환을 검증한다."""

import pytest

from bomi_vision.adapters.tracking import TrackingCandidate, convert_tracked_people

pytestmark = pytest.mark.unit


def candidate(
    *,
    track_id: int | None = 4,
    class_id: int = 0,
    confidence: float = 0.8,
) -> TrackingCandidate:
    """추적 후보의 필수 경곗값만 간단히 구성한다."""
    return TrackingCandidate(track_id, class_id, confidence, 10.0, 20.0, 110.0, 220.0)


def test_converts_person_with_track_id() -> None:
    """유효한 사람 후보의 Track ID와 박스를 내부 계약으로 변환한다."""
    people = convert_tracked_people([candidate()], 0.5)
    assert len(people) == 1
    assert people[0].track_id == 4


def test_ignores_result_without_track_id() -> None:
    """추적 ID가 아직 없는 외부 결과를 대표 후보로 사용하지 않는다."""
    assert convert_tracked_people([candidate(track_id=None)], 0.5) == []


def test_ignores_non_person_and_low_confidence_results() -> None:
    """사람이 아니거나 최소 신뢰도 미만인 결과를 제외한다."""
    assert convert_tracked_people([candidate(class_id=2), candidate(confidence=0.49)], 0.5) == []
