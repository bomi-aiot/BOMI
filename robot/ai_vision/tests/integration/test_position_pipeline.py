"""가짜 프레임 경계로 탐지부터 위치 결과 전달까지의 연결을 검증한다."""

from collections.abc import Sequence
from typing import cast

import numpy as np
from numpy.typing import NDArray
import pytest

from bomi_vision.adapters.detection import UltralyticsPersonDetector
from bomi_vision.adapters.opencv import OpenCVCamera, OpenCVDebugView
from bomi_vision.application import run_person_detection
from bomi_vision.domain import (
    PersonDetection,
    VisionPositionResult,
    VisionResultStatus,
)

pytestmark = pytest.mark.integration

Frame = NDArray[np.uint8]


class FakeDetector:
    """모델 없이 정해진 사람 탐지 결과를 반환한다."""

    def __init__(self) -> None:
        """탐지기에 전달된 프레임을 기록할 공간을 초기화한다."""
        self.observed_frame: object | None = None

    def detect(self, frame: object) -> list[PersonDetection]:
        """프레임 중앙의 한 사람을 반환한다."""
        self.observed_frame = frame
        return [PersonDetection(0.9, 270.0, 140.0, 370.0, 340.0)]


class FakeCamera:
    """장비 없이 640x480 프레임과 해제 상태를 제공한다."""

    def __init__(self) -> None:
        """좌우가 구분되는 원본 프레임과 해제 여부를 초기화한다."""
        self.released = False
        self.frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.frame[:, 0, 0] = 10
        self.frame[:, -1, 0] = 200

    def read(self) -> Frame:
        """위치 계산에 필요한 크기를 가진 빈 프레임을 반환한다."""
        return self.frame

    def release(self) -> None:
        """파이프라인의 카메라 정리 호출을 기록한다."""
        self.released = True


class RecordingView:
    """표시 대신 전달된 위치 결과와 종료 동작을 기록한다."""

    def __init__(self) -> None:
        """결과와 종료 상태를 초기화한다."""
        self.result: VisionPositionResult | None = None
        self.observed_frame: Frame | None = None
        self.closed = False

    def show(
        self,
        frame: Frame,
        detections: Sequence[PersonDetection],
        result: VisionPositionResult,
    ) -> bool:
        """첫 결과를 기록하고 반복을 종료한다."""
        self.observed_frame = frame
        self.result = result
        return False

    def close(self) -> None:
        """파이프라인의 화면 정리 호출을 기록한다."""
        self.closed = True


def test_pipeline_delivers_position_result_and_releases_resources() -> None:
    """탐지 결과가 위치 결과로 전달되고 모든 자원이 정리된다."""
    camera = FakeCamera()
    detector = FakeDetector()
    view = RecordingView()

    run_person_detection(
        cast(UltralyticsPersonDetector, detector),
        cast(OpenCVCamera, camera),
        cast(OpenCVDebugView, view),
    )

    assert view.result is not None
    assert view.result.status is VisionResultStatus.USER_DETECTED
    assert view.result.position is not None
    assert view.result.position.offset_x == pytest.approx(0.0)
    assert camera.released is True
    assert view.closed is True


def test_pipeline_uses_unflipped_camera_frame_for_detection_and_view() -> None:
    """탐지와 디버그 표시가 좌우 반전하지 않은 동일 원본 프레임을 사용한다."""
    camera = FakeCamera()
    detector = FakeDetector()
    view = RecordingView()

    run_person_detection(
        cast(UltralyticsPersonDetector, detector),
        cast(OpenCVCamera, camera),
        cast(OpenCVDebugView, view),
    )

    assert detector.observed_frame is camera.frame
    assert view.observed_frame is camera.frame
    assert camera.frame[0, 0, 0] == 10
    assert camera.frame[0, -1, 0] == 200
