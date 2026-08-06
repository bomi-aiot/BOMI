"""외부 모델과 카메라 없이 사람 탐지 변환 계약을 검증한다."""

import pytest

from bomi_vision.adapters.detection import (
    DetectionCandidate,
    convert_person_detections,
)

pytestmark = pytest.mark.unit


def candidate(
    *,
    class_id: int = 0,
    confidence: float = 0.8,
    x1: float = 10.0,
    y1: float = 20.0,
    x2: float = 110.0,
    y2: float = 220.0,
) -> DetectionCandidate:
    """테스트에서 관심 있는 탐지 후보 필드만 쉽게 변경한다."""
    return DetectionCandidate(class_id, confidence, x1, y1, x2, y2)


def test_converts_person_candidate() -> None:
    """사람 클래스의 신뢰도와 픽셀 좌표를 그대로 변환한다."""
    detections = convert_person_detections([candidate()], 0.5)

    assert len(detections) == 1
    assert detections[0].confidence == 0.8
    assert (detections[0].x1, detections[0].y1) == (10.0, 20.0)
    assert (detections[0].x2, detections[0].y2) == (110.0, 220.0)


def test_excludes_non_person_class() -> None:
    """COCO person 식별자가 아닌 탐지 후보를 제외한다."""
    assert convert_person_detections([candidate(class_id=2)], 0.5) == []


def test_excludes_candidate_below_confidence_threshold() -> None:
    """최소 신뢰도보다 낮은 사람 탐지 후보를 제외한다."""
    assert convert_person_detections([candidate(confidence=0.49)], 0.5) == []


def test_returns_empty_list_for_no_candidates() -> None:
    """탐지 후보가 없으면 정상적인 빈 목록을 반환한다."""
    assert convert_person_detections([], 0.5) == []


def test_returns_all_person_candidates() -> None:
    """여러 사람이 탐지되면 특정 사람을 고르지 않고 모두 반환한다."""
    detections = convert_person_detections(
        [candidate(confidence=0.7), candidate(confidence=0.9, x1=200.0, x2=300.0)],
        0.5,
    )

    assert [detection.confidence for detection in detections] == [0.7, 0.9]


@pytest.mark.parametrize(
    "invalid_candidate",
    [
        candidate(x1=-1.0),
        candidate(x1=10.0, x2=10.0),
        candidate(y1=20.0, y2=19.0),
    ],
)
def test_rejects_invalid_person_coordinates(
    invalid_candidate: DetectionCandidate,
) -> None:
    """음수 또는 면적이 없는 사람 박스를 오류로 처리한다."""
    with pytest.raises(ValueError, match="Detection"):
        convert_person_detections([invalid_candidate], 0.5)
