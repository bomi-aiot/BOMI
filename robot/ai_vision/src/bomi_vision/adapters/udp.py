"""사람 추종 결과를 실제 로봇으로 UDP 전송하는 출력 어댑터."""

from collections.abc import Sequence
import json
import socket
from typing import Any

from bomi_vision.adapters.opencv import Frame, OpenCVDebugView
from bomi_vision.domain import (
    FollowCommand,
    FollowCommandResult,
    TrackedPerson,
    TrackingResult,
    TrackingResultStatus,
)


class UdpFollowView(OpenCVDebugView):
    """매 프레임의 사람 추종 결과를 UDP JSON으로 전송한다.

    디버그 창 사용 여부와 관계없이 동일한 추적 결과를 로봇으로 전달한다.
    프로세스가 정상 종료될 때에는 마지막으로 정지 명령을 전송한다.
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        show_window: bool = True,
        window_name: str = "BOMI Person Tracking UDP",
    ) -> None:
        """UDP 목적지와 선택적 디버그 창을 초기화한다."""
        if not isinstance(host, str) or not host.strip():
            raise ValueError("UDP host must not be empty.")
        if isinstance(port, bool) or not isinstance(port, int):
            raise ValueError("UDP port must be an integer.")
        if not 1 <= port <= 65535:
            raise ValueError("UDP port must be from 1 to 65535.")

        super().__init__(window_name)
        self._destination = (host.strip(), port)
        self._show_window = show_window
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._closed = False

    def show(
        self,
        frame: Frame,
        tracked_people: Sequence[TrackedPerson],
        result: TrackingResult,
        follow_result: FollowCommandResult,
    ) -> bool:
        """현재 추종 결과를 전송하고 필요하면 디버그 화면을 표시한다."""
        if self._closed:
            raise RuntimeError("UDP follow view is already closed.")

        self._send_payload(
            {
                "status": result.status.value,
                "command": follow_result.command.value,
                "track_id": follow_result.track_id,
                "reason": follow_result.reason,
            }
        )

        if not self._show_window:
            return True

        return super().show(
            frame,
            tracked_people,
            result,
            follow_result,
        )

    def close(self) -> None:
        """마지막 정지 명령을 보낸 뒤 UDP 소켓과 화면을 정리한다."""
        if self._closed:
            return

        try:
            self._send_payload(
                {
                    "status": TrackingResultStatus.NOT_DETECTED.value,
                    "command": FollowCommand.STOP.value,
                    "track_id": None,
                    "reason": "udp_sender_shutdown",
                }
            )
        except OSError:
            # 종료 중 전송 실패가 원래 종료 원인을 가리지 않도록 한다.
            pass
        finally:
            self._closed = True
            self._socket.close()
            super().close()

    def _send_payload(self, payload: dict[str, Any]) -> None:
        """JSON 메시지 하나를 설정된 실제 로봇 주소로 전송한다."""
        packet = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        self._socket.sendto(packet, self._destination)
