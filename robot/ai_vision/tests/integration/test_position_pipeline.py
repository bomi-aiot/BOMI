"""가짜 프레임 경계로 추적부터 위치 결과 전달까지의 연결을 검증한다."""

from collections.abc import Sequence
from typing import cast

import numpy as np
from numpy.typing import NDArray
import pytest

from bomi_vision.adapters.opencv import OpenCVCamera, OpenCVDebugView
from bomi_vision.adapters.tracking import UltralyticsByteTracker
from bomi_vision.application import run_person_tracking
from bomi_vision.domain import (
    FollowCommand,
    FollowCommandResult,
    TrackedPerson,
    TrackingResult,
    TrackingResultStatus,
)
from bomi_vision.follow import FollowCommandGenerator
from bomi_vision.tracking import UserTrackingService

pytestmark = pytest.mark.integration

Frame = NDArray[np.uint8]


def tracking_service() -> UserTrackingService:
    """파이프라인 연결 검증에 사용할 기본 상태 머신을 생성한다."""
    return UserTrackingService(
        lost_tolerance_frames=2,
        multiple_confirm_frames=5,
        single_recovery_frames=10,
    )


class FakeTracker:
    """모델 없이 정해진 사람 추적 결과를 반환한다."""

    def __init__(self) -> None:
        """탐지기에 전달된 프레임을 기록할 공간을 초기화한다."""
        self.observed_frame: object | None = None

    def track(self, frame: object) -> list[TrackedPerson]:
        """프레임 중앙의 한 사람과 임시 Track ID를 반환한다."""
        self.observed_frame = frame
        return [TrackedPerson(5, 0.9, 270.0, 140.0, 370.0, 340.0)]


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
        self.result: TrackingResult | None = None
        self.follow_result: FollowCommandResult | None = None
        self.observed_frame: Frame | None = None
        self.closed = False

    def show(
        self,
        frame: Frame,
        tracked_people: Sequence[TrackedPerson],
        result: TrackingResult,
        follow_result: FollowCommandResult,
    ) -> bool:
        """첫 결과를 기록하고 반복을 종료한다."""
        self.observed_frame = frame
        self.result = result
        self.follow_result = follow_result
        return False

    def close(self) -> None:
        """파이프라인의 화면 정리 호출을 기록한다."""
        self.closed = True


def test_pipeline_delivers_position_result_and_releases_resources() -> None:
    """탐지 결과가 위치 결과로 전달되고 모든 자원이 정리된다."""
    camera = FakeCamera()
    tracker = FakeTracker()
    view = RecordingView()

    run_person_tracking(
        cast(UltralyticsByteTracker, tracker),
        tracking_service(),
        FollowCommandGenerator(0.15, 0.45),
        cast(OpenCVCamera, camera),
        cast(OpenCVDebugView, view),
    )

    assert view.result is not None
    assert view.result.status is TrackingResultStatus.TRACKING
    assert view.result.track_id == 5
    assert view.result.position is not None
    assert view.result.position.offset_x == pytest.approx(0.0)
    assert view.follow_result is not None
    assert view.follow_result.command is FollowCommand.MOVE_FORWARD
    assert view.follow_result.track_id == 5
    assert camera.released is True
    assert view.closed is True


def test_pipeline_uses_unflipped_camera_frame_for_detection_and_view() -> None:
    """탐지와 디버그 표시가 좌우 반전하지 않은 동일 원본 프레임을 사용한다."""
    camera = FakeCamera()
    tracker = FakeTracker()
    view = RecordingView()

    run_person_tracking(
        cast(UltralyticsByteTracker, tracker),
        tracking_service(),
        FollowCommandGenerator(0.15, 0.45),
        cast(OpenCVCamera, camera),
        cast(OpenCVDebugView, view),
    )

    assert tracker.observed_frame is camera.frame
    assert view.observed_frame is camera.frame
    assert camera.frame[0, 0, 0] == 10
    assert camera.frame[0, -1, 0] == 200
