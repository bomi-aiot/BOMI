"""Windows 비전 결과를 UDP로 수신해 ROS2 토픽으로 전달한다."""

import socket

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class VisionUdpBridge(Node):
    """UDP 패킷을 ROS2 String 메시지로 중계한다."""

    def __init__(self) -> None:
        """UDP 소켓, ROS2 발행자와 폴링 타이머를 생성한다."""
        super().__init__("vision_udp_bridge")

        self.declare_parameter("bind_host", "0.0.0.0")
        self.declare_parameter("bind_port", 5005)
        self.declare_parameter(
            "output_topic",
            "/vision/follow_result",
        )
        self.declare_parameter("poll_interval_sec", 0.01)
        self.declare_parameter("max_packet_bytes", 4096)
        self.declare_parameter("max_packets_per_poll", 20)

        bind_host = str(
            self.get_parameter("bind_host").value
        )
        bind_port = int(
            self.get_parameter("bind_port").value
        )
        output_topic = str(
            self.get_parameter("output_topic").value
        )
        poll_interval_sec = float(
            self.get_parameter("poll_interval_sec").value
        )
        self._max_packet_bytes = int(
            self.get_parameter("max_packet_bytes").value
        )
        self._max_packets_per_poll = int(
            self.get_parameter(
                "max_packets_per_poll"
            ).value
        )

        if not 1 <= bind_port <= 65535:
            raise ValueError(
                "bind_port는 1부터 65535 사이여야 합니다."
            )

        if poll_interval_sec <= 0.0:
            raise ValueError(
                "poll_interval_sec는 양수여야 합니다."
            )

        if self._max_packet_bytes <= 0:
            raise ValueError(
                "max_packet_bytes는 양수여야 합니다."
            )

        if self._max_packets_per_poll <= 0:
            raise ValueError(
                "max_packets_per_poll은 양수여야 합니다."
            )

        self._publisher = self.create_publisher(
            String,
            output_topic,
            10,
        )

        self._socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )
        self._socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )
        self._socket.bind((bind_host, bind_port))
        self._socket.setblocking(False)

        self._timer = self.create_timer(
            poll_interval_sec,
            self._poll_socket,
        )

        self.get_logger().info(
            "비전 UDP 브리지를 시작했습니다. "
            f"수신={bind_host}:{bind_port}, "
            f"ROS2 출력={output_topic}"
        )

    def _poll_socket(self) -> None:
        """대기 중인 UDP 패킷을 ROS2 메시지로 발행한다."""
        for _ in range(self._max_packets_per_poll):
            try:
                data, address = self._socket.recvfrom(
                    self._max_packet_bytes
                )
            except BlockingIOError:
                return
            except OSError as error:
                self.get_logger().error(
                    f"UDP 수신 오류: {error}"
                )
                return

            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                self.get_logger().warning(
                    "UTF-8이 아닌 UDP 패킷을 무시합니다."
                )
                continue

            if not text.strip():
                self.get_logger().warning(
                    "빈 UDP 패킷을 무시합니다."
                )
                continue

            message = String()
            message.data = text
            self._publisher.publish(message)

            self.get_logger().debug(
                "비전 UDP 메시지 전달: "
                f"sender={address}, data={text}"
            )

    def close_socket(self) -> None:
        """UDP 소켓을 닫는다."""
        self._socket.close()


def main(args=None) -> None:
    """UDP-ROS2 브리지 노드를 실행한다."""
    rclpy.init(args=args)

    node: VisionUdpBridge | None = None

    try:
        node = VisionUdpBridge()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.close_socket()
            node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
