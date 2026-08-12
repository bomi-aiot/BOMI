"""PySide6 이벤트 루프와 ROS 2 구독을 함께 실행하는 LCD 진입점."""

import argparse
from pathlib import Path
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from bomi_display.face_widget import FaceWidget
from bomi_display.state import DisplayStateModel, FaceState


def _parse_app_args(arguments: list[str]) -> tuple[argparse.Namespace, list[str]]:
    """UI 전용 인자를 읽고 나머지는 ROS 2에 전달한다."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--sensor-timeout", type=float, default=3.0)
    parser.add_argument("--ai-status-file", default="/tmp/bomi_ai_status")
    return parser.parse_known_args(arguments)


def main(args=None) -> None:
    """데모 또는 ROS 2 구독 모드로 LCD 표정 창을 실행한다."""
    raw_args = list(sys.argv[1:] if args is None else args)
    app_args, ros_args = _parse_app_args(raw_args)
    app = QApplication([sys.argv[0]])
    signal.signal(signal.SIGINT, lambda _signal, _frame: app.quit())
    widget = FaceWidget()
    if app_args.windowed:
        widget.resize(800, 480)
        widget.show()
    else:
        widget.showFullScreen()

    if app_args.demo:
        _start_demo(widget)
        sys.exit(app.exec())

    try:
        import rclpy
        from geometry_msgs.msg import Twist
        from rclpy.node import Node
        from std_msgs.msg import Bool, Empty, String
    except ImportError as error:
        raise RuntimeError("ROS 2 환경이 아니면 --demo 옵션으로 실행하세요") from error

    class DisplayNode(Node):
        """Nav2, TTS, MQTT, 센서 상태를 구독해 화면 모델에 전달한다."""

        def __init__(self) -> None:
            super().__init__("bomi_face_display")
            self.model = DisplayStateModel(app_args.sensor_timeout)
            self.create_subscription(String, "/bomi/nav_status", self._on_nav, 10)
            self.create_subscription(String, "/bomi/tts_status", self._on_tts, 10)
            self.create_subscription(Bool, "/bomi/mqtt_connected", self._on_mqtt, 10)
            self.create_subscription(Empty, "/bomi/sensor_heartbeat", self._on_sensor, 10)
            self.create_subscription(Twist, "/cmd_vel", self._on_velocity, 10)
            self.ai_status_file = Path(app_args.ai_status_file)
            self.ai_status_mtime_ns = -1

        def _on_nav(self, message) -> None:
            """Nav2 상태를 화면 모델에 반영한다."""
            self.model.update_nav(message.data)

        def _on_tts(self, message) -> None:
            """TTS 상태를 화면 모델에 반영한다."""
            self.model.update_tts(message.data)

        def _on_mqtt(self, message) -> None:
            """MQTT 연결 상태를 화면 모델에 반영한다."""
            self.model.update_mqtt(message.data)

        def _on_sensor(self, message) -> None:
            """센서 생존 신호의 수신 시각을 갱신한다."""
            del message
            self.model.mark_sensor_update()

        def _on_velocity(self, message) -> None:
            """최종 모터 속도 명령으로 실제 이동 여부를 판단한다."""
            moving = (
                abs(message.linear.x) > 0.01
                or abs(message.linear.y) > 0.01
                or abs(message.angular.z) > 0.01
            )
            self.model.update_motion(moving)

        def refresh_ai_status(self) -> None:
            """AI 가상환경이 기록한 대화 상태를 변경될 때만 반영한다."""
            try:
                mtime_ns = self.ai_status_file.stat().st_mtime_ns
                if mtime_ns == self.ai_status_mtime_ns:
                    return
                value = self.ai_status_file.read_text(encoding="utf-8").strip()
            except OSError:
                return
            self.ai_status_mtime_ns = mtime_ns
            if value:
                self.model.update_tts(value)

    rclpy.init(args=ros_args)
    node = DisplayNode()
    ros_timer = QTimer()
    ros_timer.timeout.connect(lambda: rclpy.spin_once(node, timeout_sec=0.0))
    ros_timer.start(10)
    view_timer = QTimer()
    def refresh_view() -> None:
        node.refresh_ai_status()
        widget.set_snapshot(node.model.snapshot())

    view_timer.timeout.connect(refresh_view)
    view_timer.start(100)
    app.aboutToQuit.connect(node.destroy_node)
    app.aboutToQuit.connect(rclpy.shutdown)
    sys.exit(app.exec())


def _start_demo(widget: FaceWidget) -> None:
    """ROS 2 없이 모든 표정을 순서대로 보여주는 데모를 시작한다."""
    states = list(FaceState)
    index = {"value": 0}

    def advance() -> None:
        state = states[index["value"] % len(states)]
        detail = "MQTT 연결 끊김" if state == FaceState.ERROR else ""
        titles = {
            FaceState.IDLE: "기다리고 있어요",
            FaceState.DRIVING: "이동 중",
            FaceState.LISTENING: "듣고 있어요",
            FaceState.THINKING: "생각하는 중",
            FaceState.SPEAKING: "말하는 중",
            FaceState.ERROR: "연결 오류",
        }
        widget.set_snapshot(type(widget.snapshot)(state, titles[state], detail))
        index["value"] += 1

    advance()
    timer = QTimer(widget)
    timer.timeout.connect(advance)
    timer.start(2500)


if __name__ == "__main__":
    main()
