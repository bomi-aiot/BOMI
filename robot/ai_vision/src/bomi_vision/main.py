"""명령행 설정으로 BOMI 실시간 사람 추적 애플리케이션을 실행한다."""

import argparse

from bomi_vision.adapters.detection import validate_confidence
from bomi_vision.adapters.opencv import OpenCVCamera, OpenCVDebugView
from bomi_vision.adapters.tracking import UltralyticsByteTracker
from bomi_vision.application import run_person_tracking
from bomi_vision.follow import FollowCommandGenerator
from bomi_vision.tracking import UserTrackingService

# YOLO11의 가장 작은 사전 학습 모델로 노트북 MVP에서 빠른 확인을 우선한다.
DEFAULT_MODEL = "yolo11n.pt"
# 일반적으로 노트북 내장 카메라가 운영체제의 첫 번째 장치로 등록된다.
DEFAULT_CAMERA_INDEX = 0
# 지나치게 불확실한 박스를 줄이면서 기본 탐지를 쉽게 확인할 수 있는 시작값이다.
DEFAULT_CONFIDENCE = 0.8
# Ultralytics가 제공하는 공식 ByteTrack 기본 설정을 사용한다.
DEFAULT_TRACKER = "bytetrack.yaml"
# 30 FPS 기준 약 0.1초의 순간 누락을 흡수하되 오래된 대상을 유지하지 않는다.
DEFAULT_LOST_TOLERANCE_FRAMES = 3
# 30 FPS 기준 약 0.17초 동안 두 명 이상이 유지돼야 다중 인물로 확정해 순간 중복
# 탐지와 지나가는 방문자를 흡수한다.
DEFAULT_MULTIPLE_CONFIRM_FRAMES = 5
# 다중 인물이 해제된 직후 잘못된 대상을 추적하지 않도록 확인 기준보다 길게 잡은
# 30 FPS 기준 약 0.33초의 안정화 구간이다.
DEFAULT_SINGLE_RECOVERY_FRAMES = 10
# 실제 카메라에서 조정할 초기 수평 중앙 허용 범위다.
DEFAULT_HORIZONTAL_DEAD_ZONE = 0.15
# 실제 장비에서 조정할 초기 전진 정지용 화면 높이 비율이다.
DEFAULT_FORWARD_THRESHOLD = 0.45


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


def parse_lost_tolerance_frames(value: str) -> int:
    """0 이상의 추적 누락 허용 프레임 수를 파싱한다."""
    try:
        frames = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Lost tolerance must be an integer.") from error
    if frames < 0:
        raise argparse.ArgumentTypeError("Lost tolerance must be zero or greater.")
    return frames


def parse_multiple_confirm_frames(value: str) -> int:
    """다중 인물을 확정할 1 이상의 연속 프레임 수를 파싱한다."""
    return _parse_positive_frames(value, "Multiple confirm frames")


def parse_single_recovery_frames(value: str) -> int:
    """정상 추적으로 복귀할 1 이상의 연속 프레임 수를 파싱한다."""
    return _parse_positive_frames(value, "Single recovery frames")


def _parse_positive_frames(value: str, option_description: str) -> int:
    """상태 전환에 사용할 1 이상의 프레임 수를 공통 규칙으로 파싱한다.

    Args:
        value: 명령행에서 받은 프레임 수 문자열.
        option_description: 오류 메시지에 사용할 옵션 설명.

    Returns:
        검증된 프레임 수.

    Raises:
        argparse.ArgumentTypeError: 정수가 아니거나 1 미만인 경우.
    """
    try:
        frames = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{option_description} must be an integer.") from error
    if frames < 1:
        raise argparse.ArgumentTypeError(f"{option_description} must be one or greater.")
    return frames


def parse_horizontal_dead_zone(value: str) -> float:
    """0.0 이상 1.0 미만의 수평 중앙 허용 범위를 파싱한다."""
    try:
        dead_zone = float(value)
        FollowCommandGenerator(dead_zone, DEFAULT_FORWARD_THRESHOLD)
        return dead_zone
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def parse_forward_threshold(value: str) -> float:
    """0.0 이상 1.0 이하의 전진 정지 임계값을 파싱한다."""
    try:
        threshold = float(value)
        FollowCommandGenerator(DEFAULT_HORIZONTAL_DEAD_ZONE, threshold)
        return threshold
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
        "--tracker",
        default=DEFAULT_TRACKER,
        help="Ultralytics tracker configuration (default: bytetrack.yaml).",
    )
    parser.add_argument(
        "--lost-tolerance-frames",
        default=DEFAULT_LOST_TOLERANCE_FRAMES,
        type=parse_lost_tolerance_frames,
        help="Temporary tracking loss tolerance in frames (default: 3).",
    )
    parser.add_argument(
        "--multiple-confirm-frames",
        default=DEFAULT_MULTIPLE_CONFIRM_FRAMES,
        type=parse_multiple_confirm_frames,
        help="Frames of two or more people needed to confirm multiple persons (default: 5).",
    )
    parser.add_argument(
        "--single-recovery-frames",
        default=DEFAULT_SINGLE_RECOVERY_FRAMES,
        type=parse_single_recovery_frames,
        help="Stable single person frames needed to resume tracking (default: 10).",
    )
    parser.add_argument(
        "--confidence",
        default=DEFAULT_CONFIDENCE,
        type=parse_confidence,
        help="Detection confidence from 0.0 to 1.0 (default: 0.5).",
    )
    parser.add_argument(
        "--horizontal-dead-zone",
        default=DEFAULT_HORIZONTAL_DEAD_ZONE,
        type=parse_horizontal_dead_zone,
        help="Centered horizontal offset range (default: 0.15).",
    )
    parser.add_argument(
        "--forward-threshold",
        default=DEFAULT_FORWARD_THRESHOLD,
        type=parse_forward_threshold,
        help="Centered forward stop height ratio (default: 0.45).",
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
        tracker = UltralyticsByteTracker(args.model, args.confidence, args.tracker)
        tracking_service = UserTrackingService(
            lost_tolerance_frames=args.lost_tolerance_frames,
            multiple_confirm_frames=args.multiple_confirm_frames,
            single_recovery_frames=args.single_recovery_frames,
        )
        follow_command_generator = FollowCommandGenerator(
            args.horizontal_dead_zone,
            args.forward_threshold,
        )
        camera = OpenCVCamera(args.camera)
        run_person_tracking(
            tracker,
            tracking_service,
            follow_command_generator,
            camera,
            OpenCVDebugView(),
        )
    except (RuntimeError, ValueError) as error:
        # CLI 경계에서 간결한 메시지로 바꾸되 원인은 adapter 예외 연결에 보존한다.
        print(f"Error: {error}")
        if camera is not None:
            camera.release()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
