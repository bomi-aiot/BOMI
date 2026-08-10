"""
Jetson과 Pico H 사이의 실제 시리얼 통신을 담당하는 ROS2 노드.

/cmd_vel을 좌우 바퀴 목표 속도로 변환해 Pico에 보내고, Pico가 보내는
텔레메트리를 파싱해 /odom과 /imu로 발행한다. 시작·종료 절차와 명령
타임아웃은 robot/docs/pico-serial-protocol.md를 따른다.

시리얼 입출력과 ROS2 노드를 이 파일에 두고, 형식 변환과 파싱은
core.pico_protocol의 순수 로직에 맡긴다.
"""

import math
import time

import rclpy
import serial
from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.time import Time
from sensor_msgs.msg import Imu
from tf2_ros import TransformBroadcaster

from core.pico_protocol import (
    FLAG_IMU_OK,
    FLAG_WATCHDOG_STOPPED,
    LineKind,
    MAX_TARGET_REV_S,
    PROTOCOL_VERSION,
    TelemetryFrame,
    classify_line,
    flip_yaw_sign,
    format_velocity_command,
    parse_telemetry_line,
    twist_to_wheel_targets,
)


# 빈 줄을 보낸 뒤 Pico가 그걸 소화하고 응답을 낼 때까지 주는 시간.
# 펌웨어는 메인 루프 한 바퀴(20 ms)에 문자 하나만 읽으므로, 앞에 남은
# 명령 조각까지 밀어내려면 몇 글자분의 여유가 필요하다. 넉넉히 잡아도
# 시작할 때 한 번뿐이라 손해가 없다.
INPUT_FLUSH_SETTLE_SEC = 0.3


class PicoDriver(Node):
    """Pico H와 시리얼로 통신하며 /cmd_vel을 주행 명령으로 바꾸는 노드."""

    def __init__(self, **node_kwargs) -> None:
        """파라미터를 읽고 검증한 뒤 Pico와 시작 절차를 밟는다."""
        super().__init__("pico_driver", **node_kwargs)

        self._declare_parameters()
        self._read_parameters()
        self._validate_parameters()

        self._pose_covariance = self._diagonal_covariance(
            self._pose_covariance_diagonal, size=6
        )
        self._twist_covariance = self._diagonal_covariance(
            self._twist_covariance_diagonal, size=6
        )

        self._last_cmd_vel = Twist()
        self._last_cmd_vel_time: Time | None = None
        self._cmd_vel_timeout_logged = False
        self._last_command_time: Time | None = None
        self._clamped_count = 0
        self._last_clamp_log_time: Time | None = None

        self._read_buffer = ""
        self._violation_count = 0
        self._last_telemetry_time: Time | None = None
        self._telemetry_timeout_logged = False
        self._previous_flags = 0
        self._first_flag_report = True

        self._previous_left_front_count: int | None = None
        self._previous_right_front_count: int | None = None
        self._x_m = 0.0
        self._y_m = 0.0
        self._yaw_rad = 0.0

        self._odom_publisher = self.create_publisher(
            Odometry,
            self._odom_topic,
            10,
        )
        self._imu_publisher = self.create_publisher(
            Imu,
            self._imu_topic,
            10,
        )
        self._tf_broadcaster = TransformBroadcaster(self)

        self._serial = serial.Serial(
            self._serial_port,
            timeout=self._handshake_timeout_sec,
        )

        # Pico는 열리기 전부터 계속 텔레메트리를 보내고 있었을 수 있다.
        # 그 잔여분을 비우지 않으면 핸드셰이크 응답이 밀린 줄 뒤에 묻힌다.
        self._serial.reset_input_buffer()

        self._gyro_bias_dps = 0.0

        try:
            self._run_startup_sequence_with_retry()
            self._measure_gyro_bias()
        except Exception:
            self._serial.close()
            raise

        self._serial.timeout = 0

        # 깊이 1이면 큐에 밀린 옛 명령을 처리하지 않고 항상 최신 명령만
        # 남는다. 조작 입력은 최신값만 의미가 있다.
        self._cmd_vel_subscription = self.create_subscription(
            Twist,
            self._cmd_vel_topic,
            self._handle_cmd_vel,
            1,
        )

        self._control_timer = self.create_timer(
            1.0 / self._control_hz,
            self._on_control_tick,
        )

        self.get_logger().info(
            "Pico 드라이버를 시작했습니다. "
            f"포트={self._serial_port}, "
            f"cmd_vel 입력={self._cmd_vel_topic}, "
            f"odom 출력={self._odom_topic}"
        )

    def _declare_parameters(self) -> None:
        """Pico 시리얼 드라이버가 쓰는 ROS2 파라미터를 선언한다."""
        self.declare_parameter("serial_port", "/dev/ttyACM0")
        self.declare_parameter("handshake_timeout_sec", 1.0)

        # Pico가 열리기 전부터 텔레메트리를 계속 보내고 있었을 수 있어
        # 응답 하나를 받기까지 밀린 줄을 한참 읽어야 할 수 있다. 개별
        # 읽기 시간(handshake_timeout_sec)과 달리 이건 전체 대기 예산이다.
        self.declare_parameter("startup_response_timeout_sec", 5.0)

        # 핸드셰이크를 몇 번까지 다시 시도할지. 부팅 직후에는 Pico가 USB
        # 열거를 막 끝낸 참이라 첫 'S'를 받지 못하고 흘리는 일이 있다.
        # 2026-08-07 리허설에서 젯슨 부팅 1분 뒤 실행한 스택이 정확히 그
        # 이유로 이 노드만 죽었고, 나머지 노드는 멀쩡해서 조이스틱이
        # 안 듣는 원인을 찾는 데 오래 걸렸다. 한 번의 실패로 노드를 죽이면
        # 스택 전체가 모터 없이 뜬다.
        self.declare_parameter("startup_attempts", 5)
        self.declare_parameter("startup_retry_delay_sec", 1.0)

        # 자이로가 보고하는 회전량에 곱하는 보정 계수.
        #
        # 2026-08-07 실기: 제자리 한 바퀴(360°)를 돌렸는데 EKF가 411°로
        # 셌다. 90° 돌 때마다 지도는 103° 돌았다고 믿으므로, 회전할 때마다
        # 방이 10~20°씩 어긋난 채 겹쳐 쌓인다. 부호는 정상이고 배율만 크다.
        #
        # 이 오차는 공간이 특징적일 때는 스캔 매칭이 가려준다. 특징 없는
        # 빈 직사각형 방에서는 매칭이 잡아줄 근거가 없어 그대로 드러난다.
        # 그래서 "예전엔 됐는데"가 성립하며, 설정을 되돌려도 낫지 않는다.
        #
        # 실측으로 정한다: scripts/lib/calibrate_gyro.py 참고.
        # 1.0은 보정하지 않는다는 뜻이다.
        self.declare_parameter("gyro_scale", 1.0)

        # 기동 시 정지 상태에서 자이로 영점을 재서 뺀다. 0이면 재지 않는다.
        # 이 치우침은 재부팅·온도마다 달라지므로 상수로 적어두면 안 된다.
        self.declare_parameter("gyro_bias_samples", 100)
        self.declare_parameter("gyro_bias_max_spread_dps", 1.0)

        self.declare_parameter("cmd_vel_topic", "/cmd_vel")
        self.declare_parameter("odom_topic", "/odom")
        self.declare_parameter("imu_topic", "/imu")
        self.declare_parameter("odom_frame_id", "odom")
        self.declare_parameter("base_frame_id", "base_link")
        self.declare_parameter("imu_frame_id", "base_link")
        self.declare_parameter("publish_tf", True)

        # robot/docs/hardware-control.md `## 7 확정한 값`과 같은 값이다.
        self.declare_parameter("track_width_m", 0.257)
        self.declare_parameter("distance_per_rev_m", 0.1929)
        self.declare_parameter("max_target_rev_s", MAX_TARGET_REV_S)
        self.declare_parameter("left_front_cpr", 979)
        self.declare_parameter("right_front_cpr", 979)

        # 텔레메트리를 읽어 발행하는 주기. 펌웨어 CONTROL_MS(20ms)와 같게
        # 두어야 한 주기에 여러 줄이 몰리지 않고 stamp가 표본 시각에 맞는다.
        self.declare_parameter("control_hz", 50.0)

        # V 명령 전송 주기. 읽기 주기와 분리한다.
        #
        # 펌웨어는 메인 루프 한 바퀴에 문자 하나만 읽는다
        # (closed_loop_speed.py의 `sys.stdin.read(1)`). V 한 줄이 18자쯤이라
        # 전송 주기를 올리면 펌웨어가 배출하는 속도를 넘어서고, 그때부터
        # USB 버퍼에 명령이 쌓여 조작 지연이 계속 누적된다.
        # 워치독이 300ms이므로 20Hz면 6배 여유가 있다.
        self.declare_parameter("command_hz", 20.0)

        # ROS 레벨 명령 타임아웃. Pico 자체 워치독(300ms)과는 별개로,
        # /cmd_vel이 끊기면 여기서 먼저 정지 명령으로 바꾼다.
        self.declare_parameter("cmd_vel_timeout_sec", 0.5)

        # 텔레메트리가 이 시간 넘게 안 오면 통신 이상으로 보고 경고한다.
        self.declare_parameter("telemetry_timeout_sec", 1.0)

        # 자이로 z축 각속도 분산 (rad/s)^2. 실측 보정 전 잠정값이다.
        # robot/docs/pico-serial-protocol.md `## 9`와 함께 다룬다.
        self.declare_parameter("angular_velocity_variance", 0.05)

        # pose/twist 공분산 대각값 [x, y, z, roll, pitch, yaw].
        # z, roll, pitch는 평면 로봇이라 관측하지 않으므로 크게 둔다.
        # 나머지도 실측 보정 전 잠정값이다.
        self.declare_parameter(
            "pose_covariance_diagonal",
            [0.05, 0.05, 1e6, 1e6, 1e6, 0.2],
        )
        self.declare_parameter(
            "twist_covariance_diagonal",
            [0.05, 1e6, 1e6, 1e6, 1e6, 0.2],
        )

    def _read_parameters(self) -> None:
        """선언한 파라미터 값을 읽어 속성으로 저장한다."""
        self._serial_port = str(
            self.get_parameter("serial_port").value
        )
        self._handshake_timeout_sec = float(
            self.get_parameter("handshake_timeout_sec").value
        )
        self._startup_response_timeout_sec = float(
            self.get_parameter("startup_response_timeout_sec").value
        )
        self._startup_attempts = int(
            self.get_parameter("startup_attempts").value
        )
        self._startup_retry_delay_sec = float(
            self.get_parameter("startup_retry_delay_sec").value
        )
        self._gyro_scale = float(self.get_parameter("gyro_scale").value)
        self._gyro_bias_samples = int(
            self.get_parameter("gyro_bias_samples").value
        )
        self._gyro_bias_max_spread_dps = float(
            self.get_parameter("gyro_bias_max_spread_dps").value
        )

        self._cmd_vel_topic = str(
            self.get_parameter("cmd_vel_topic").value
        )
        self._odom_topic = str(
            self.get_parameter("odom_topic").value
        )
        self._imu_topic = str(
            self.get_parameter("imu_topic").value
        )
        self._odom_frame_id = str(
            self.get_parameter("odom_frame_id").value
        )
        self._base_frame_id = str(
            self.get_parameter("base_frame_id").value
        )
        self._imu_frame_id = str(
            self.get_parameter("imu_frame_id").value
        )
        self._publish_tf = bool(
            self.get_parameter("publish_tf").value
        )

        self._track_width_m = float(
            self.get_parameter("track_width_m").value
        )
        self._distance_per_rev_m = float(
            self.get_parameter("distance_per_rev_m").value
        )
        self._max_target_rev_s = float(
            self.get_parameter("max_target_rev_s").value
        )
        self._left_front_cpr = int(
            self.get_parameter("left_front_cpr").value
        )
        self._right_front_cpr = int(
            self.get_parameter("right_front_cpr").value
        )

        self._control_hz = float(
            self.get_parameter("control_hz").value
        )
        self._command_hz = float(
            self.get_parameter("command_hz").value
        )
        self._cmd_vel_timeout_sec = float(
            self.get_parameter("cmd_vel_timeout_sec").value
        )
        self._telemetry_timeout_sec = float(
            self.get_parameter("telemetry_timeout_sec").value
        )

        self._angular_velocity_variance = float(
            self.get_parameter("angular_velocity_variance").value
        )
        self._pose_covariance_diagonal = [
            float(value)
            for value in self.get_parameter(
                "pose_covariance_diagonal"
            ).value
        ]
        self._twist_covariance_diagonal = [
            float(value)
            for value in self.get_parameter(
                "twist_covariance_diagonal"
            ).value
        ]

    def _validate_parameters(self) -> None:
        """시작 시 설정값의 단위와 허용 범위를 검사한다."""
        if not self._serial_port:
            raise ValueError("serial_port는 비어 있을 수 없습니다.")

        if not self._is_positive_finite(self._handshake_timeout_sec):
            raise ValueError(
                "handshake_timeout_sec는 유한한 양수여야 합니다."
            )

        if not self._is_positive_finite(
            self._startup_response_timeout_sec
        ):
            raise ValueError(
                "startup_response_timeout_sec는 유한한 양수여야 합니다."
            )

        if self._startup_attempts < 1:
            raise ValueError("startup_attempts는 1 이상이어야 합니다.")

        if not self._is_positive_finite(self._gyro_scale):
            raise ValueError("gyro_scale은 유한한 양수여야 합니다.")

        if (
            not math.isfinite(self._startup_retry_delay_sec)
            or self._startup_retry_delay_sec < 0.0
        ):
            raise ValueError(
                "startup_retry_delay_sec는 유한한 0 이상이어야 합니다."
            )

        if not self._is_positive_finite(self._track_width_m):
            raise ValueError("track_width_m은 유한한 양수여야 합니다.")

        if not self._is_positive_finite(self._distance_per_rev_m):
            raise ValueError(
                "distance_per_rev_m은 유한한 양수여야 합니다."
            )

        if not self._is_positive_finite(self._max_target_rev_s):
            raise ValueError(
                "max_target_rev_s는 유한한 양수여야 합니다."
            )

        if self._left_front_cpr <= 0 or self._right_front_cpr <= 0:
            raise ValueError(
                "left_front_cpr와 right_front_cpr는 양의 정수여야 합니다."
            )

        if not self._is_positive_finite(self._control_hz):
            raise ValueError("control_hz는 유한한 양수여야 합니다.")

        if not self._is_positive_finite(self._command_hz):
            raise ValueError("command_hz는 유한한 양수여야 합니다.")

        if self._command_hz > self._control_hz:
            raise ValueError(
                "command_hz는 control_hz보다 클 수 없습니다 "
                f"(command_hz={self._command_hz}, "
                f"control_hz={self._control_hz})."
            )

        if not self._is_positive_finite(self._cmd_vel_timeout_sec):
            raise ValueError(
                "cmd_vel_timeout_sec는 유한한 양수여야 합니다."
            )

        if not self._is_positive_finite(self._telemetry_timeout_sec):
            raise ValueError(
                "telemetry_timeout_sec는 유한한 양수여야 합니다."
            )

        if len(self._pose_covariance_diagonal) != 6:
            raise ValueError(
                "pose_covariance_diagonal은 6개 값이어야 합니다."
            )

        if len(self._twist_covariance_diagonal) != 6:
            raise ValueError(
                "twist_covariance_diagonal은 6개 값이어야 합니다."
            )

    @staticmethod
    def _is_positive_finite(value: float) -> bool:
        """값이 유한한 양수인지 확인한다."""
        return math.isfinite(value) and value > 0.0

    @staticmethod
    def _diagonal_covariance(
        diagonal: list[float],
        size: int,
    ) -> list[float]:
        """대각값 목록을 size x size 공분산 행렬(1차원)로 만든다."""
        matrix = [0.0] * (size * size)

        for index, value in enumerate(diagonal):
            matrix[index * (size + 1)] = value

        return matrix

    # -----------------------------------------------------------
    # 시작 절차 (robot/docs/pico-serial-protocol.md `## 6`)
    # -----------------------------------------------------------

    def _run_startup_sequence_with_retry(self) -> None:
        """핸드셰이크가 실패하면 잠시 쉬었다가 다시 시도한다.

        젯슨 부팅 직후에는 /dev/ttyACM0이 생긴 직후라도 Pico가 아직
        명령을 받을 준비가 안 돼 첫 'S'를 흘려버린다. 이건 몇 초 뒤면
        저절로 낫는 상태이므로, 한 번 실패했다고 노드를 죽이면 안 된다.
        노드가 죽으면 나머지 스택은 정상으로 보이는 채 /cmd_vel 구독자만
        사라져서, 조이스틱도 Nav2도 조용히 아무 일도 하지 않는다.

        프로토콜 버전 불일치(RuntimeError)는 기다린다고 낫지 않으므로
        다시 시도하지 않고 그대로 올린다.
        """
        last_error: Exception | None = None

        for attempt in range(1, self._startup_attempts + 1):
            try:
                self._run_startup_sequence()
            except (TimeoutError, ValueError) as error:
                last_error = error
                self.get_logger().warn(
                    f"Pico 핸드셰이크 실패 "
                    f"({attempt}/{self._startup_attempts}): {error}"
                )

                if attempt < self._startup_attempts:
                    # 실패한 시도가 남긴 응답 조각을 비우고 다시 건다.
                    # 남겨두면 다음 시도가 옛 줄을 읽느라 예산을 쓴다.
                    self._serial.reset_input_buffer()
                    self._serial.reset_output_buffer()
                    time.sleep(self._startup_retry_delay_sec)

                continue

            if attempt > 1:
                self.get_logger().info(
                    f"Pico 핸드셰이크가 {attempt}번째 시도에서 성공했습니다."
                )

            return

        raise TimeoutError(
            f"Pico 핸드셰이크가 {self._startup_attempts}번 모두 "
            f"실패했습니다: {last_error}"
        )

    def _run_startup_sequence(self) -> None:
        """S -> P(버전 확인) -> Z -> T 1 순서로 Pico를 초기화한다."""
        timeout = self._startup_response_timeout_sec

        self._flush_partial_command()

        self._write_line("S")
        self._expect_line_prefix("ACK", "S", timeout)

        self._write_line("P")
        response = self._expect_line_prefix("ACK P", "P", timeout)
        proto = self._parse_proto_version(response)

        if proto != PROTOCOL_VERSION:
            raise RuntimeError(
                f"Pico 프로토콜 버전이 다릅니다 (기대={PROTOCOL_VERSION}, "
                f"실제={proto}): {response!r}"
            )

        self._write_line("Z")
        self._expect_line_prefix("ACK", "Z", timeout)

        self._write_line("T 1")
        self._expect_line_prefix("ACK T", "T 1", timeout)

    def _measure_gyro_bias(self) -> None:
        """정지 상태에서 자이로 영점을 재서 이후 각속도에서 뺀다.

        왜 필요한가: 2026-08-07 실기에서 로봇이 완전히 멈춰 있는데도
        자이로가 초당 1.5555°(=93°/분)를 보고했다. EKF는 yaw를 이 자이로
        하나로만 만들므로(config/ekf.yaml), 40초짜리 제자리 회전이면 그것만
        으로 62°가 쌓여 회전할 때마다 지도가 어긋난 채 겹쳤다.

        왜 파라미터 상수가 아니라 매번 재는가: 같은 로봇에서도 재부팅과
        온도에 따라 값이 달라진다. 실제로 배율 오차로 오인해 상수를 넣었다가
        같은 측정을 두 번 했을 때 6% 어긋나는 것을 보고서야 원인을 알았다.

        로봇이 움직이는 중이면 잘못된 영점을 박아 넣게 되므로, 표본이
        흔들리면 보정을 포기한다. 안 하는 편이 틀리게 하는 것보다 낫다.
        """
        if self._gyro_bias_samples <= 0:
            return

        deadline = time.monotonic() + 10.0
        rates: list[float] = []

        while len(rates) < self._gyro_bias_samples:
            if time.monotonic() > deadline:
                self.get_logger().warning(
                    "자이로 영점 표본을 다 모으지 못했습니다 "
                    f"({len(rates)}/{self._gyro_bias_samples}). 보정 없이 갑니다."
                )
                return

            raw = self._serial.readline()
            line = self._decode_line(raw) if raw else None

            if line is None or classify_line(line) is not LineKind.TELEMETRY:
                continue

            try:
                frame = parse_telemetry_line(line)
            except ValueError:
                continue

            if not frame.is_imu_ok:
                self.get_logger().warning(
                    "IMU가 비정상이라 자이로 영점을 재지 않습니다."
                )
                return

            rates.append(frame.gyro_rate_dps)

        spread = max(rates) - min(rates)

        if spread > self._gyro_bias_max_spread_dps:
            self.get_logger().warning(
                f"자이로 영점 측정 중 각속도가 {spread:.2f}°/초 흔들렸습니다. "
                "로봇이 움직이는 것으로 보고 보정을 건너뜁니다. "
                "로봇을 완전히 세운 채 다시 실행하세요."
            )
            return

        self._gyro_bias_dps = sum(rates) / len(rates)

        self.get_logger().info(
            f"자이로 영점 {self._gyro_bias_dps:+.4f}°/초 "
            f"({self._gyro_bias_dps * 60.0:+.1f}°/분)를 재서 뺍니다. "
            f"표본 {len(rates)}개, 흔들림 {spread:.3f}°/초."
        )

    def _flush_partial_command(self) -> None:
        """Pico 입력 버퍼에 남은 명령 조각을 빈 줄로 끊는다.

        앞선 세션이 명령을 쓰다가 강제 종료되면 Pico 버퍼에 완성되지 않은
        줄이 남는다. 그 상태에서 'S'를 보내면 조각 뒤에 이어붙어 하나의
        잘못된 명령이 되고, Pico는 'ERR usage: ...'로 답한다. 우리가 기다리는
        'ACK'는 영영 오지 않는다. 2026-08-07 리허설의 실제 실패가 이것이다
        (S 대기 중 'ERR usage: T <0|1>' 수신).

        빈 줄은 규약상 무시되므로(robot/docs/pico-serial-protocol.md `## 1`)
        버퍼가 이미 깨끗해도 부작용이 없다.
        """
        self._write_line("")
        time.sleep(INPUT_FLUSH_SETTLE_SEC)

        # 끊긴 조각에 대한 ERR과 밀린 텔레메트리를 버린다. 남겨두면
        # 다음 응답을 기다리는 예산을 옛 줄 읽는 데 쓴다.
        self._serial.reset_input_buffer()

    def _expect_line_prefix(
        self,
        prefix: str,
        command_for_log: str,
        overall_timeout_sec: float = 5.0,
    ) -> str:
        """
        지정한 접두어로 시작하는 줄이 올 때까지 읽는다.

        Pico는 열리기 전부터 텔레메트리를 계속 보내고 있었을 수 있어
        응답 앞에 밀린 줄이 여러 개 쌓여 있을 수 있다. 그래서 횟수가
        아니라 전체 대기 시간으로 얼마나 기다릴지를 정한다. 기다리는
        동안 다른 줄(WARN, 배너, 밀린 텔레메트리 등)도 정상 경로로
        처리한다.
        """
        deadline = time.monotonic() + overall_timeout_sec

        while time.monotonic() < deadline:
            raw = self._serial.readline()

            if not raw:
                continue

            line = self._decode_line(raw)

            if line is None:
                continue

            self._handle_incoming_line(line)

            if line.startswith(prefix):
                return line

        raise TimeoutError(
            f"'{command_for_log}' 명령에 대한 '{prefix}' 응답을 "
            f"{overall_timeout_sec}초 안에 받지 못했습니다."
        )

    @staticmethod
    def _parse_proto_version(response: str) -> int:
        """'ACK P proto=1 fw=...' 응답에서 프로토콜 버전을 뽑는다."""
        for word in response.split():
            if word.startswith("proto="):
                try:
                    return int(word.split("=", 1)[1])
                except ValueError:
                    break

        raise ValueError(f"P 응답에서 proto 값을 찾을 수 없습니다: {response!r}")

    # -----------------------------------------------------------
    # 시리얼 입출력
    # -----------------------------------------------------------

    def _write_line(self, text: str) -> None:
        """명령 한 줄을 줄바꿈과 함께 Pico로 보낸다."""
        self._serial.write((text + "\n").encode("ascii"))

    @staticmethod
    def _decode_line(raw: bytes) -> str | None:
        """읽은 바이트를 ASCII 줄로 바꾼다. 빈 줄이면 None을 돌려준다."""
        line = raw.decode("ascii", errors="replace").strip()
        return line or None

    def _drain_serial(self) -> None:
        """대기 중인 바이트를 모두 읽어 완성된 줄만큼 처리한다."""
        waiting = self._serial.in_waiting

        if waiting:
            chunk = self._serial.read(waiting)
            self._read_buffer += chunk.decode(
                "ascii", errors="replace"
            )

        while "\n" in self._read_buffer:
            raw_line, self._read_buffer = self._read_buffer.split(
                "\n", 1
            )
            line = raw_line.strip("\r\n ")

            if line:
                self._handle_incoming_line(line)

    def _handle_incoming_line(self, line: str) -> None:
        """줄 종류에 따라 텔레메트리 처리나 로그 기록으로 나눈다."""
        kind = classify_line(line)

        if kind is LineKind.TELEMETRY:
            self._handle_telemetry_line(line)
        elif kind is LineKind.ACK:
            self.get_logger().debug(f"Pico: {line}")
        elif kind is LineKind.WARN:
            self.get_logger().warning(f"Pico: {line}")
        elif kind is LineKind.ERR:
            self.get_logger().error(f"Pico: {line}")
        elif kind is LineKind.COMMENT:
            pass
        else:
            self._violation_count += 1
            self.get_logger().warning(
                f"Pico 시리얼 규칙 위반 줄 (누적 {self._violation_count}건): "
                f"{line!r}"
            )

    # -----------------------------------------------------------
    # 텔레메트리 처리
    # -----------------------------------------------------------

    def _handle_telemetry_line(self, line: str) -> None:
        """텔레메트리를 파싱해 /odom과 /imu로 발행한다."""
        try:
            frame = parse_telemetry_line(line)
        except ValueError as error:
            self.get_logger().warning(f"텔레메트리 파싱 실패: {error}")
            return

        self._last_telemetry_time = self.get_clock().now()
        self._telemetry_timeout_logged = False

        self._log_flag_transitions(frame)
        self._previous_flags = frame.flags

        stamp = self._last_telemetry_time.to_msg()

        self._publish_imu(frame, stamp)
        self._publish_odometry(frame, stamp)

    def _log_flag_transitions(self, frame: TelemetryFrame) -> None:
        """지속형 플래그(워치독, IMU)는 바뀔 때만 로그를 남긴다."""
        was_watchdog_stopped = bool(
            self._previous_flags & FLAG_WATCHDOG_STOPPED
        )
        was_imu_ok = bool(self._previous_flags & FLAG_IMU_OK)

        # 첫 프레임에는 비교할 이전 상태가 없다. 전환만 보면 "처음부터
        # 비정상"인 경우를 통째로 놓친다 — 2026-08-07 실기에서 재부팅 뒤
        # IMU가 죽은 채로 떴는데 아무 로그도 남지 않아, 지도가 회전마다
        # 겹치는 원인을 찾는 데 오래 걸렸다. EKF는 yaw를 이 자이로 하나로만
        # 만들므로(core/config/ekf.yaml), IMU가 죽으면 yaw가 아예 갱신되지
        # 않고 지도는 회전에서만 무너진다. 그래서 첫 프레임 상태를 반드시
        # 남긴다.
        if self._first_flag_report:
            self._first_flag_report = False

            if frame.is_imu_ok:
                self.get_logger().info("Pico IMU 정상 — yaw를 자이로로 만든다.")
            else:
                self.get_logger().error(
                    "Pico IMU가 비정상 상태로 시작했습니다. "
                    "yaw가 갱신되지 않아 회전하면 지도와 위치가 무너집니다. "
                    "Pico USB를 다시 꽂아 펌웨어를 재기동하세요."
                )

            was_imu_ok = frame.is_imu_ok

        if frame.is_watchdog_stopped and not was_watchdog_stopped:
            self.get_logger().error("Pico가 워치독으로 정지했습니다.")

        if not frame.is_imu_ok and was_imu_ok:
            self.get_logger().error(
                "Pico IMU가 비정상입니다. yaw/rate를 더 이상 믿지 않습니다."
            )

        if frame.is_imu_ok and not was_imu_ok:
            self.get_logger().info("Pico IMU가 정상으로 돌아왔습니다.")

        if frame.is_fifo_overflowed:
            self.get_logger().warning("Pico PIO FIFO가 넘쳤습니다.")

        if frame.is_outlier_rejected:
            self.get_logger().debug("Pico가 엔코더 이상치를 버렸습니다.")

    def _publish_imu(self, frame: TelemetryFrame, stamp) -> None:
        """sensor_msgs/Imu를 만든다. 채울 수 없는 필드는 규약대로 비운다."""
        message = Imu()
        message.header.stamp = stamp
        message.header.frame_id = self._imu_frame_id

        # 자세(쿼터니언)와 선가속도는 펌웨어가 채우지 않는다.
        # 첫 값을 -1로 두는 것은 "이 필드는 쓸 수 없다"는 표준 표시다.
        message.orientation_covariance[0] = -1.0
        message.linear_acceleration_covariance[0] = -1.0

        if frame.is_imu_ok:
            # 영점을 뺀 뒤 부호를 뒤집는다. 순서가 중요하다 — 영점은 Pico
            # 부호계에서 잰 값이므로 뒤집기 전에 빼야 한다.
            corrected_dps = frame.gyro_rate_dps - self._gyro_bias_dps
            rate_rad_s = math.radians(
                flip_yaw_sign(corrected_dps) * self._gyro_scale
            )
            message.angular_velocity.z = rate_rad_s

            # x, y는 측정하지 않으므로 분산을 크게 둬 사실상 무시하게
            # 한다. z만 실제로 측정한 값이다.
            message.angular_velocity_covariance[0] = 1e6
            message.angular_velocity_covariance[4] = 1e6
            message.angular_velocity_covariance[8] = (
                self._angular_velocity_variance
            )
        else:
            # IMU가 비정상이면 z도 더 이상 믿지 않는다.
            message.angular_velocity_covariance[0] = -1.0

        self._imu_publisher.publish(message)

    def _publish_odometry(self, frame: TelemetryFrame, stamp) -> None:
        """
        카운트 차분과 yaw로 위치를 적분해 /odom을 발행한다.

        앞바퀴(lf, rf) 카운트만 쓴다. 뒷바퀴는 무시한다
        (robot/docs/hardware-control.md 근거).
        """
        if self._previous_left_front_count is None:
            self._previous_left_front_count = frame.left_front_count
            self._previous_right_front_count = frame.right_front_count
        else:
            left_delta = (
                frame.left_front_count
                - self._previous_left_front_count
            )
            right_delta = (
                frame.right_front_count
                - self._previous_right_front_count
            )
            self._previous_left_front_count = frame.left_front_count
            self._previous_right_front_count = (
                frame.right_front_count
            )

            left_distance_m = (
                left_delta
                / self._left_front_cpr
                * self._distance_per_rev_m
            )
            right_distance_m = (
                right_delta
                / self._right_front_cpr
                * self._distance_per_rev_m
            )
            travel_delta_m = (
                left_distance_m + right_distance_m
            ) / 2.0

            # 각속도와 같은 계수로 보정한다. 한쪽만 보정하면 /imu 로 만든
            # TF 와 /odom 의 x·y 적분이 서로 다른 회전을 믿게 된다.
            self._yaw_rad = math.radians(
                flip_yaw_sign(frame.yaw_deg) * self._gyro_scale
            )
            self._x_m += travel_delta_m * math.cos(self._yaw_rad)
            self._y_m += travel_delta_m * math.sin(self._yaw_rad)

        quaternion_z = math.sin(self._yaw_rad / 2.0)
        quaternion_w = math.cos(self._yaw_rad / 2.0)

        if frame.is_imu_ok:
            angular_z_rad_s = math.radians(
                flip_yaw_sign(frame.gyro_rate_dps)
            )
        else:
            angular_z_rad_s = 0.0

        linear_x_m_s = (
            (frame.left_actual_rev_s + frame.right_actual_rev_s)
            / 2.0
            * self._distance_per_rev_m
        )

        odometry = Odometry()
        odometry.header.stamp = stamp
        odometry.header.frame_id = self._odom_frame_id
        odometry.child_frame_id = self._base_frame_id

        odometry.pose.pose.position.x = self._x_m
        odometry.pose.pose.position.y = self._y_m
        odometry.pose.pose.orientation.z = quaternion_z
        odometry.pose.pose.orientation.w = quaternion_w
        odometry.pose.covariance = self._pose_covariance

        odometry.twist.twist.linear.x = linear_x_m_s
        odometry.twist.twist.angular.z = angular_z_rad_s
        odometry.twist.covariance = self._twist_covariance

        self._odom_publisher.publish(odometry)

        if self._publish_tf:
            transform = TransformStamped()
            transform.header.stamp = stamp
            transform.header.frame_id = self._odom_frame_id
            transform.child_frame_id = self._base_frame_id
            transform.transform.translation.x = self._x_m
            transform.transform.translation.y = self._y_m
            transform.transform.rotation.z = quaternion_z
            transform.transform.rotation.w = quaternion_w

            self._tf_broadcaster.sendTransform(transform)

    # -----------------------------------------------------------
    # 주기 제어
    # -----------------------------------------------------------

    def _handle_cmd_vel(self, message: Twist) -> None:
        """최신 이동 명령과 수신 시각을 기록한다."""
        self._last_cmd_vel = message
        self._last_cmd_vel_time = self.get_clock().now()

    def _on_control_tick(self) -> None:
        """
        수신 처리와 타임아웃 확인을 매 주기 하고, 전송은 따로 제한한다.

        읽기는 텔레메트리 주기(50Hz)에 맞춰야 stamp가 정확하지만, 전송은
        펌웨어가 문자를 배출하는 속도를 넘으면 지연이 누적된다.
        """
        self._drain_serial()
        self._check_telemetry_timeout()

        if self._is_command_due():
            self._send_velocity_command()

    def _is_command_due(self) -> bool:
        """V 명령을 보낼 차례인지 확인하고, 보낼 때 시각을 기록한다."""
        now = self.get_clock().now()

        if self._last_command_time is not None:
            elapsed_sec = (
                now - self._last_command_time
            ).nanoseconds / 1_000_000_000

            # 제어 주기의 절반을 여유로 둔다. 이게 없으면 전송 주기가
            # 항상 한 주기씩 밀려 목표보다 느려진다.
            due_sec = 1.0 / self._command_hz - 0.5 / self._control_hz

            if elapsed_sec < due_sec:
                return False

        self._last_command_time = now
        return True

    def _check_telemetry_timeout(self) -> None:
        """텔레메트리가 오래 끊기면 경고한다 (한 번만)."""
        if self._last_telemetry_time is None:
            return

        if self._telemetry_timeout_logged:
            return

        elapsed_sec = (
            self.get_clock().now() - self._last_telemetry_time
        ).nanoseconds / 1_000_000_000

        if elapsed_sec <= self._telemetry_timeout_sec:
            return

        self._telemetry_timeout_logged = True
        self.get_logger().error(
            "Pico 텔레메트리 수신이 "
            f"{elapsed_sec:.2f}초 동안 끊겼습니다."
        )

    def _send_velocity_command(self) -> None:
        """cmd_vel 타임아웃을 확인하고 V 명령을 만들어 보낸다."""
        linear_x = 0.0
        angular_z = 0.0

        if self._last_cmd_vel_time is not None:
            elapsed_sec = (
                self.get_clock().now() - self._last_cmd_vel_time
            ).nanoseconds / 1_000_000_000

            if elapsed_sec <= self._cmd_vel_timeout_sec:
                linear_x = self._last_cmd_vel.linear.x
                angular_z = self._last_cmd_vel.angular.z
                self._cmd_vel_timeout_logged = False
            elif not self._cmd_vel_timeout_logged:
                self._cmd_vel_timeout_logged = True
                self.get_logger().warning(
                    "cmd_vel 수신이 끊겨 정지 명령을 보냅니다."
                )

        targets = twist_to_wheel_targets(
            linear_x,
            angular_z,
            self._track_width_m,
            self._distance_per_rev_m,
            self._max_target_rev_s,
        )

        if targets.clamped:
            self._log_clamped(targets)

        self._write_line(format_velocity_command(targets))

    def _log_clamped(self, targets) -> None:
        """
        잘린 명령을 1초에 한 번만 묶어서 경고한다.

        조이스틱을 대각선으로 밀면 매 주기 잘리는데, 그때마다 화면에
        찍으면 콘솔 출력이 노드 주기를 잡아먹어 조작이 밀린다.
        """
        self._clamped_count += 1
        now = self.get_clock().now()

        if self._last_clamp_log_time is not None:
            elapsed_sec = (
                now - self._last_clamp_log_time
            ).nanoseconds / 1_000_000_000

            if elapsed_sec < 1.0:
                return

        self._last_clamp_log_time = now
        self.get_logger().warning(
            "목표 속도가 최대치를 넘어 잘렸습니다 "
            f"(누적 {self._clamped_count}회): "
            f"left={targets.left_rev_s:.3f} "
            f"right={targets.right_rev_s:.3f}"
        )

    def shutdown(self) -> None:
        """정지 명령을 최선을 다해 보내고 포트를 닫는다."""
        try:
            self._write_line("S")
            self._write_line("T 0")
        except Exception as error:
            self.get_logger().error(
                f"종료 중 정지 명령 전송에 실패했습니다: {error}"
            )
        finally:
            try:
                self._serial.close()
            except Exception:
                pass


def main(args=None) -> None:
    """Pico 시리얼 드라이버 노드를 실행한다."""
    rclpy.init(args=args)

    node: PicoDriver | None = None

    try:
        node = PicoDriver()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.shutdown()
            node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
