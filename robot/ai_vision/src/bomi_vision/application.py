"""카메라 입력, 사람 추적, 상태 판단과 화면 표시를 순서대로 조합한다."""

from bomi_vision.adapters.opencv import OpenCVCamera, OpenCVDebugView
from bomi_vision.adapters.tracking import UltralyticsByteTracker
from bomi_vision.tracking import UserTrackingService


def run_person_tracking(
    tracker: UltralyticsByteTracker,
    tracking_service: UserTrackingService,
    camera: OpenCVCamera,
    view: OpenCVDebugView,
) -> None:
    """사용자가 종료할 때까지 실시간 사람 추적 파이프라인을 실행한다.

    Args:
        tracker: 프레임에서 ByteTrack으로 모든 사람을 추적하는 어댑터.
        tracking_service: 사람 수와 누락 상태를 판단하는 서비스.
        camera: 실시간 프레임을 제공하는 카메라.
        view: 탐지 결과를 표시하고 종료 입력을 확인하는 화면.

    Raises:
        RuntimeError: 카메라 읽기나 모델 추론에 실패한 경우.

    Side Effects:
        카메라를 읽고 화면을 표시하며, 종료 시 모든 자원을 정리한다.

    Note:
        카메라에서 읽은 원본 프레임을 좌우 반전하지 않고 탐지, 위치 계산,
        디버그 표시에 동일하게 사용한다.
    """
    try:
        while True:
            frame = camera.read()
            tracked_people = tracker.track(frame)
            frame_height, frame_width = frame.shape[:2]
            result = tracking_service.update(
                tracked_people,
                frame_width=frame_width,
                frame_height=frame_height,
            )
            if not view.show(frame, tracked_people, result):
                break
    finally:
        camera.release()
        view.close()
