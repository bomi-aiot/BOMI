"""외부 장비 없이 사람 추종 결과의 UDP 전송 계약을 검증한다."""

import json
import socket

import numpy as np
import pytest

from bomi_vision.adapters.udp import UdpFollowView
from bomi_vision.domain import (
    FollowCommand,
    FollowCommandResult,
    TrackingResult,
    TrackingResultStatus,
)

pytestmark = pytest.mark.unit


def open_local_receiver() -> socket.socket:
    """테스트 프로세스 안에서 사용할 임시 UDP 수신 소켓을 생성한다."""
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(2.0)
    return receiver


def receive_json(receiver: socket.socket) -> dict[str, object]:
    """UDP 패킷 하나를 수신해 JSON 객체로 변환한다."""
    packet, _ = receiver.recvfrom(4096)
    payload = json.loads(packet.decode("utf-8"))

    assert isinstance(payload, dict)
    return payload


def test_sends_follow_result_as_udp_json() -> None:
    """사람 추종 상태와 희망 명령을 정해진 JSON 계약으로 전송한다."""
    receiver = open_local_receiver()
    host, port = receiver.getsockname()

    view = UdpFollowView(
        host,
        port,
        show_window=False,
    )

    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    tracking_result = TrackingResult(
        TrackingResultStatus.NOT_DETECTED,
        0,
        None,
        None,
    )
    follow_result = FollowCommandResult(
        FollowCommand.STOP,
        "tracking_not_available",
        None,
    )

    try:
        keep_running = view.show(
            frame,
            [],
            tracking_result,
            follow_result,
        )

        assert keep_running is True
        assert receive_json(receiver) == {
            "status": "not_detected",
            "command": "stop",
            "track_id": None,
            "reason": "tracking_not_available",
        }
    finally:
        view.close()
        receiver.close()


def test_close_sends_final_stop_packet() -> None:
    """송신부 종료 시 실제 로봇에 마지막 정지 명령을 전송한다."""
    receiver = open_local_receiver()
    host, port = receiver.getsockname()

    view = UdpFollowView(
        host,
        port,
        show_window=False,
    )

    try:
        view.close()

        assert receive_json(receiver) == {
            "status": "not_detected",
            "command": "stop",
            "track_id": None,
            "reason": "udp_sender_shutdown",
        }
    finally:
        view.close()
        receiver.close()


@pytest.mark.parametrize(
    ("host", "port"),
    [
        ("", 5005),
        ("   ", 5005),
        ("127.0.0.1", 0),
        ("127.0.0.1", 65536),
    ],
)
def test_rejects_invalid_destination(
    host: str,
    port: int,
) -> None:
    """비어 있는 주소와 허용 범위 밖의 UDP 포트를 거부한다."""
    with pytest.raises(ValueError):
        UdpFollowView(
            host,
            port,
            show_window=False,
        )
