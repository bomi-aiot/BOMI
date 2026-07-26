"""명령행 설정으로 BOMI 실시간 사람 탐지 애플리케이션을 실행한다."""

import argparse

from bomi_vision.adapters.detection import (
    UltralyticsPersonDetector,
    validate_confidence,
)
from bomi_vision.adapters.opencv import OpenCVCamera, OpenCVDebugView
from bomi_vision.application import run_person_detection

# YOLO11의 가장 작은 사전 학습 모델로 노트북 MVP에서 빠른 확인을 우선한다.
DEFAULT_MODEL = "yolo11n.pt"
# 일반적으로 노트북 내장 카메라가 운영체제의 첫 번째 장치로 등록된다.
DEFAULT_CAMERA_INDEX = 0
# 지나치게 불확실한 박스를 줄이면서 기본 탐지를 쉽게 확인할 수 있는 시작값이다.
DEFAULT_CONFIDENCE = 0.5


def parse_camera_index(value: str) -> int:
    """0 이상의 카메라 인덱스를 파싱한다.

    Args:
        value: 명령행에서 받은 카메라 번호 문자열.

    Returns:
        검증된 카메라 인덱스.

    Raises:
        argparse.ArgumentTypeError: 정수가 아니거나 음수인 경우.
    """
    try:
        camera_index = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Camera index must be an integer.") from error
    if camera_index < 0:
        raise argparse.ArgumentTypeError("Camera index must be zero or greater.")
    return camera_index


def parse_confidence(value: str) -> float:
    """0.0 이상 1.0 이하의 신뢰도를 파싱한다.

    Args:
        value: 명령행에서 받은 신뢰도 문자열.

    Returns:
        검증된 신뢰도.

    Raises:
        argparse.ArgumentTypeError: 숫자가 아니거나 허용 범위 밖인 경우.
    """
    try:
        confidence = float(value)
        return validate_confidence(confidence)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def build_parser() -> argparse.ArgumentParser:
    """사람 탐지 실행에 필요한 명령행 파서를 생성한다."""
    parser = argparse.ArgumentParser(description="Detect people from a laptop camera.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="YOLO model name or path.")
    parser.add_argument(
        "--camera",
        default=DEFAULT_CAMERA_INDEX,
        type=parse_camera_index,
        help="Camera index (default: 0).",
    )
    parser.add_argument(
        "--confidence",
        default=DEFAULT_CONFIDENCE,
        type=parse_confidence,
        help="Detection confidence from 0.0 to 1.0 (default: 0.5).",
    )
    return parser


def main() -> int:
    """명령행 인자를 적용해 실시간 사람 탐지를 실행한다.

    Returns:
        정상 종료 시 0, 사용자에게 안내한 실행 오류가 발생하면 1.
    """
    args = build_parser().parse_args()
    camera: OpenCVCamera | None = None
    try:
        detector = UltralyticsPersonDetector(args.model, args.confidence)
        camera = OpenCVCamera(args.camera)
        run_person_detection(detector, camera, OpenCVDebugView())
    except (RuntimeError, ValueError) as error:
        # CLI 경계에서 간결한 메시지로 바꾸되 원인은 adapter 예외 연결에 보존한다.
        print(f"Error: {error}")
        if camera is not None:
            camera.release()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
