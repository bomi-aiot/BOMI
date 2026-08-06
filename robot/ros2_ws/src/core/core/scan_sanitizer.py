"""
손상된 LaserScan을 걸러내고 성한 스캔만 다시 발행하는 ROS2 노드.

모터가 돌기 시작하면 YDLIDAR 드라이버가 한 바퀴의 경계를 놓쳐, 각도 범위가
360°를 넘는 스캔을 정상 스캔과 섞어 내보낸다. 실측(2026-08-06)에서는 정지
중에는 430점(정확히 360.0°)만 나오다가, 제자리 회전 0.5초 뒤부터 480점
스캔이 섞여 나왔고 발행 주기도 10Hz에서 22.7Hz로 뛰었다. 480점은 점당
0.8392°이므로 402°, 즉 42°가 중복된 스캔이며 그 42°는 실제와 다른 방향에
벽을 그린다. 회전할 때만 나타나므로 지도가 회전마다 어긋나 겹친다.

배선과 전원을 손대지 않고 SLAM 입력을 성하게 만들기 위해, 두 가지 기준으로
스캔을 버린다.

1. 각도 범위: (점 개수 - 1) x angle_increment가 360°에서 벗어나면 버린다.
   한 바퀴가 아닌 스캔은 어느 방향으로도 옳게 놓을 수 없다.
2. 간격: 직전에 통과시킨 스캔과 너무 붙어 오면 버린다. 고장 구간에서는
   같은 한 바퀴가 두 조각으로 쪼개져 두 배 주기로 올라온다.

버리는 개수를 주기적으로 로그에 남겨, 지도가 나빠질 때 라이다 상태를
숫자로 확인할 수 있게 한다.
"""

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

FULL_TURN_RAD = 2.0 * math.pi

REASON_SPAN = "span"
REASON_INTERVAL = "interval"


class ScanGate:
    """스캔을 통과시킬지 판단하는 순수 로직."""

    def __init__(
        self,
        span_tolerance_rad: float,
        minimum_interval_sec: float,
    ) -> None:
        """허용 각도 오차와 최소 간격을 받아 판정기를 만든다."""
        if not math.isfinite(span_tolerance_rad) or span_tolerance_rad <= 0.0:
            raise ValueError(
                "span_tolerance_rad는 유한한 양수여야 합니다."
            )

        if (
            not math.isfinite(minimum_interval_sec)
            or minimum_interval_sec < 0.0
        ):
            raise ValueError(
                "minimum_interval_sec는 0 이상의 유한한 값이어야 합니다."
            )

        self._span_tolerance_rad = span_tolerance_rad
        self._minimum_interval_sec = minimum_interval_sec
        self._last_passed_sec: float | None = None

    @staticmethod
    def span_rad(point_count: int, angle_increment: float) -> float:
        """스캔이 실제로 덮는 각도를 rad로 계산한다."""
        if point_count < 2:
            return 0.0

        return (point_count - 1) * angle_increment

    def judge(
        self,
        point_count: int,
        angle_increment: float,
        stamp_sec: float,
    ) -> str | None:
        """
        통과면 None, 버릴 이유가 있으면 그 이유를 돌려준다.

        통과시킨 스캔의 시각만 기억한다. 버린 스캔은 간격 기준에 영향을
        주지 않는다. 버린 것까지 기준으로 삼으면 고장 구간에서 성한 스캔이
        연달아 버려진다.
        """
        span = self.span_rad(point_count, angle_increment)

        if abs(span - FULL_TURN_RAD) > self._span_tolerance_rad:
            return REASON_SPAN

        if self._last_passed_sec is not None:
            elapsed = stamp_sec - self._last_passed_sec

            if 0.0 <= elapsed < self._minimum_interval_sec:
                return REASON_INTERVAL

        self._last_passed_sec = stamp_sec
        return None


class ScanSanitizer(Node):
    """손상된 스캔을 버리고 나머지를 그대로 다시 발행하는 노드."""

    def __init__(self, **node_kwargs) -> None:
        """파라미터를 읽고 입출력 토픽을 연결한다."""
        super().__init__("scan_sanitizer", **node_kwargs)

        self.declare_parameter("input_topic", "/scan_raw")
        self.declare_parameter("output_topic", "/scan")

        # 실측 430점 x 0.8392° = 360.0°. 5°까지는 정상으로 본다.
        self.declare_parameter("span_tolerance_deg", 5.0)

        # 정상은 10Hz(0.1초)다. 0.07초면 정상 스캔은 모두 통과하고,
        # 두 배 주기로 쪼개져 오는 조각만 걸러진다.
        self.declare_parameter("minimum_interval_sec", 0.07)

        self.declare_parameter("report_interval_sec", 5.0)

        input_topic = str(self.get_parameter("input_topic").value)
        output_topic = str(self.get_parameter("output_topic").value)

        if input_topic == output_topic:
            raise ValueError(
                "input_topic과 output_topic이 같으면 스스로를 구독합니다: "
                f"{input_topic}"
            )

        span_tolerance_deg = float(
            self.get_parameter("span_tolerance_deg").value
        )
        minimum_interval_sec = float(
            self.get_parameter("minimum_interval_sec").value
        )
        self._report_interval_sec = float(
            self.get_parameter("report_interval_sec").value
        )

        self._gate = ScanGate(
            span_tolerance_rad=math.radians(span_tolerance_deg),
            minimum_interval_sec=minimum_interval_sec,
        )

        self._passed = 0
        self._dropped = {REASON_SPAN: 0, REASON_INTERVAL: 0}
        self._last_report_sec: float | None = None

        self._publisher = self.create_publisher(
            LaserScan,
            output_topic,
            qos_profile_sensor_data,
        )
        self._subscription = self.create_subscription(
            LaserScan,
            input_topic,
            self._on_scan,
            qos_profile_sensor_data,
        )

        self.get_logger().info(
            "스캔 위생 노드를 시작했습니다. "
            f"입력={input_topic}, 출력={output_topic}, "
            f"허용 각도 오차={span_tolerance_deg}°, "
            f"최소 간격={minimum_interval_sec}초"
        )

    def _on_scan(self, message: LaserScan) -> None:
        """스캔을 판정해 통과분만 다시 발행한다."""
        stamp_sec = (
            message.header.stamp.sec
            + message.header.stamp.nanosec / 1_000_000_000
        )

        reason = self._gate.judge(
            point_count=len(message.ranges),
            angle_increment=message.angle_increment,
            stamp_sec=stamp_sec,
        )

        if reason is None:
            self._passed += 1
            self._publisher.publish(message)
        else:
            self._dropped[reason] += 1

        self._report(stamp_sec, message)

    def _report(self, stamp_sec: float, message: LaserScan) -> None:
        """일정 시간마다 통과·폐기 개수를 로그로 남긴다."""
        if self._last_report_sec is None:
            self._last_report_sec = stamp_sec
            return

        if stamp_sec - self._last_report_sec < self._report_interval_sec:
            return

        elapsed = stamp_sec - self._last_report_sec
        self._last_report_sec = stamp_sec

        dropped_total = sum(self._dropped.values())
        level = (
            self.get_logger().warning
            if dropped_total > 0
            else self.get_logger().info
        )
        point_count = len(message.ranges)
        span_deg = math.degrees(
            ScanGate.span_rad(point_count, message.angle_increment)
        )
        level(
            f"스캔 {elapsed:.1f}초: 통과 {self._passed}, "
            f"각도 범위 이상 {self._dropped[REASON_SPAN]}, "
            f"간격 과밀 {self._dropped[REASON_INTERVAL]} "
            f"(마지막 스캔 {point_count}점, {span_deg:.1f}°)"
        )

        self._passed = 0
        self._dropped = {REASON_SPAN: 0, REASON_INTERVAL: 0}


def main(args=None) -> None:
    """스캔 위생 노드를 실행한다."""
    rclpy.init(args=args)

    node = None

    try:
        node = ScanSanitizer()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
