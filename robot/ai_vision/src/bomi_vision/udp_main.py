"""BOMI 사람 추적 결과를 실제 로봇으로 UDP 전송한다."""

import argparse
import os

from bomi_vision.adapters.opencv import OpenCVCamera
from bomi_vision.adapters.tracking import UltralyticsByteTracker
from bomi_vision.adapters.udp import UdpFollowView
from bomi_vision.application import run_person_tracking
from bomi_vision.follow import FollowCommandGenerator
from bomi_vision.main import build_parser, build_primary_person_selector
from bomi_vision.tracking import UserTrackingService

DEFAULT_UDP_PORT = 5005


def parse_udp_port(value: str) -> int:
    """유효한 UDP 포트 번호를 파싱한다."""
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "UDP port must be an integer."
        ) from error

    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(
            "UDP port must be from 1 to 65535."
        )
    return port


def build_udp_parser() -> argparse.ArgumentParser:
    """기존 사람 추적 인자에 실제 로봇 UDP 설정을 추가한다."""
    parser = build_parser()
    parser.description = (
        "Track a person and send follow commands to the BOMI robot over UDP."
    )
    parser.add_argument(
        "--host",
        default=os.getenv("BOMI_ROBOT_HOST"),
        help=(
            "Jetson IP or hostname. "
            "It can also be set with BOMI_ROBOT_HOST."
        ),
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_UDP_PORT,
        type=parse_udp_port,
        help="Jetson UDP receiver port (default: 5005).",
    )
    parser.add_argument(
        "--no-window",
        action="store_true",
        help="Send results without opening the OpenCV debug window.",
    )
    return parser


def main() -> int:
    """카메라 추적 결과를 실제 로봇으로 연속 전송한다."""
    parser = build_udp_parser()
    args = parser.parse_args()

    if not isinstance(args.host, str) or not args.host.strip():
        parser.error(
            "--host or the BOMI_ROBOT_HOST environment variable is required."
        )

    camera: OpenCVCamera | None = None

    try:
        tracker = UltralyticsByteTracker(
            args.model,
            args.confidence,
            args.tracker,
        )
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
        output = UdpFollowView(
            args.host,
            args.port,
            show_window=not args.no_window,
        )

        print(
            "BOMI UDP tracking sender started: "
            f"destination={args.host}:{args.port}, "
            f"primary_person_selection="
            f"{'on' if args.select_primary_person else 'off'}"
        )

        run_person_tracking(
            tracker,
            tracking_service,
            follow_command_generator,
            camera,
            output,
            build_primary_person_selector(args),
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}")
        if camera is not None:
            camera.release()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
