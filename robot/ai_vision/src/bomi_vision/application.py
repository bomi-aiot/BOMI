"""카메라 입력, 사람 탐지, 화면 표시를 순서대로 조합한다."""

from bomi_vision.adapters.detection import UltralyticsPersonDetector
from bomi_vision.adapters.opencv import OpenCVCamera, OpenCVDebugView


def run_person_detection(
    detector: UltralyticsPersonDetector,
    camera: OpenCVCamera,
    view: OpenCVDebugView,
) -> None:
    """사용자가 종료할 때까지 실시간 사람 탐지 파이프라인을 실행한다.

    Args:
        detector: 프레임에서 모든 사람을 찾는 탐지기.
        camera: 실시간 프레임을 제공하는 카메라.
        view: 탐지 결과를 표시하고 종료 입력을 확인하는 화면.

    Raises:
        RuntimeError: 카메라 읽기나 모델 추론에 실패한 경우.

    Side Effects:
        카메라를 읽고 화면을 표시하며, 종료 시 모든 자원을 정리한다.
    """
    try:
        while True:
            frame = camera.read()
            detections = detector.detect(frame)
            if not view.show(frame, detections):
                break
    finally:
        camera.release()
        view.close()
