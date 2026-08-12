"""
Jetson↔Pico 시리얼 프로토콜의 순수 로직.

ROS2와 독립적으로 구성해 하드웨어나 rclpy 없이 단위 테스트할 수 있게
한다. 형식은 robot/docs/pico-serial-protocol.md가 정한다. 이 문서와
내용이 다르면 문서를 기준으로 이 파일을 고친다.
"""

import math
from dataclasses import dataclass
from enum import Enum


PROTOCOL_VERSION = 1

# V 인자 허용 범위. 펌웨어의 MAX_TARGET_REV_S와 같은 값이어야 한다.
MAX_TARGET_REV_S = 0.8

# T 텔레메트리는 "T"를 포함해 16낱말 고정이다.
TELEMETRY_WORD_COUNT = 16

# flags 필드의 각 비트
FLAG_DRIVING = 0x01
FLAG_IMU_OK = 0x02
FLAG_WATCHDOG_STOPPED = 0x04
FLAG_FIFO_OVERFLOWED = 0x08
FLAG_OUTLIER_REJECTED = 0x10


class LineKind(str, Enum):
    """Pico가 보내는 한 줄의 첫 낱말로 정해지는 종류."""

    TELEMETRY = "telemetry"
    ACK = "ack"
    ERR = "err"
    WARN = "warn"
    COMMENT = "comment"
    VIOLATION = "violation"


def classify_line(line: str) -> LineKind:
    """첫 낱말로 줄의 종류를 정한다. 빈 줄은 호출하지 않는다."""
    first_word = line.split(" ", 1)[0] if line else ""

    if first_word == "T":
        return LineKind.TELEMETRY

    if first_word == "ACK":
        return LineKind.ACK

    if first_word == "ERR":
        return LineKind.ERR

    if first_word == "WARN":
        return LineKind.WARN

    if line.startswith("#"):
        return LineKind.COMMENT

    return LineKind.VIOLATION


@dataclass(frozen=True)
class TelemetryFrame:
    """
    T 텔레메트리 한 줄을 파싱한 결과.

    elapsed_ms는 Pico 기동 후 경과 시각이며 로봇 위치 계산에는 쓰지
    않는다. 위치는 카운트 차분으로, 속도는 rev/s 값으로 직접 얻으므로
    dt가 필요 없다.
    """

    elapsed_ms: int
    left_target_rev_s: float
    left_actual_rev_s: float
    right_target_rev_s: float
    right_actual_rev_s: float
    left_front_count: int
    left_rear_count: int
    right_front_count: int
    right_rear_count: int
    left_pwm_percent: float
    right_pwm_percent: float
    yaw_deg: float
    gyro_rate_dps: float
    distance_m: float
    flags: int

    @property
    def is_driving(self) -> bool:
        """주행 중인지 (flags 비트 0)."""
        return bool(self.flags & FLAG_DRIVING)

    @property
    def is_imu_ok(self) -> bool:
        """IMU가 정상인지 (flags 비트 1). 꺼지면 yaw·rate가 갱신되지 않는다."""
        return bool(self.flags & FLAG_IMU_OK)

    @property
    def is_watchdog_stopped(self) -> bool:
        """워치독으로 멈췄는지 (flags 비트 2)."""
        return bool(self.flags & FLAG_WATCHDOG_STOPPED)

    @property
    def is_fifo_overflowed(self) -> bool:
        """PIO FIFO가 넘쳤는지 (flags 비트 3)."""
        return bool(self.flags & FLAG_FIFO_OVERFLOWED)

    @property
    def is_outlier_rejected(self) -> bool:
        """이상치로 버린 엔코더 표본이 있었는지 (flags 비트 4)."""
        return bool(self.flags & FLAG_OUTLIER_REJECTED)


def parse_telemetry_line(line: str) -> TelemetryFrame:
    """
    T로 시작하는 텔레메트리 한 줄을 TelemetryFrame으로 바꾼다.

    형식이 어긋나면 ValueError를 낸다. 호출부는 classify_line으로
    LineKind.TELEMETRY임을 먼저 확인해야 한다.
    """
    words = line.split()

    if len(words) != TELEMETRY_WORD_COUNT or words[0] != "T":
        raise ValueError(
            f"텔레메트리는 'T'로 시작하는 {TELEMETRY_WORD_COUNT}낱말이어야 "
            f"합니다: {line!r}"
        )

    try:
        return TelemetryFrame(
            elapsed_ms=int(words[1]),
            left_target_rev_s=float(words[2]),
            left_actual_rev_s=float(words[3]),
            right_target_rev_s=float(words[4]),
            right_actual_rev_s=float(words[5]),
            left_front_count=int(words[6]),
            left_rear_count=int(words[7]),
            right_front_count=int(words[8]),
            right_rear_count=int(words[9]),
            left_pwm_percent=float(words[10]),
            right_pwm_percent=float(words[11]),
            yaw_deg=float(words[12]),
            gyro_rate_dps=float(words[13]),
            distance_m=float(words[14]),
            flags=int(words[15], 16),
        )
    except ValueError as error:
        raise ValueError(
            f"텔레메트리 필드를 숫자로 바꿀 수 없습니다: {line!r}"
        ) from error


@dataclass(frozen=True)
class WheelTargets:
    """
    cmd_vel에서 변환한 좌우 바퀴 목표 속도.

    clamped는 변환 결과가 max_target_rev_s를 넘어 줄여 맞췄는지를
    나타낸다. 노드는 이 값으로 경고 로그를 남긴다.
    """

    left_rev_s: float
    right_rev_s: float
    clamped: bool


def twist_to_wheel_targets(
    linear_x: float,
    angular_z: float,
    track_width_m: float,
    distance_per_rev_m: float,
    max_target_rev_s: float = MAX_TARGET_REV_S,
) -> WheelTargets:
    """robot/docs/pico-serial-protocol.md `## 8`의 변환식을 그대로 적용한다."""
    if not math.isfinite(linear_x) or not math.isfinite(angular_z):
        raise ValueError("linear_x와 angular_z는 유한한 값이어야 합니다.")

    if not math.isfinite(track_width_m) or track_width_m <= 0.0:
        raise ValueError("track_width_m은 유한한 양수여야 합니다.")

    if (
        not math.isfinite(distance_per_rev_m)
        or distance_per_rev_m <= 0.0
    ):
        raise ValueError("distance_per_rev_m은 유한한 양수여야 합니다.")

    left_m_s = linear_x - angular_z * track_width_m / 2.0
    right_m_s = linear_x + angular_z * track_width_m / 2.0

    left_rev_s = left_m_s / distance_per_rev_m
    right_rev_s = right_m_s / distance_per_rev_m

    # 한계를 넘으면 좌우를 같은 비율로 줄인다. 각각 따로 잘라내면 좌우 비율이
    # 바뀌어 곡률이 명령과 달라지고, 로봇은 계획된 경로 바깥으로 빗겨 나간다
    # (2026-08-10 실기: 바깥 바퀴만 0.8에 붙은 채 안쪽만 살아 남는 명령이
    # 주행 내내 259회). 같은 비율로 줄이면 v/w 가 보존되어 경로는 그대로,
    # 속도만 느려진다.
    peak_rev_s = max(abs(left_rev_s), abs(right_rev_s))
    clamped = peak_rev_s > max_target_rev_s

    if clamped:
        scale = max_target_rev_s / peak_rev_s
        left_rev_s *= scale
        right_rev_s *= scale

    return WheelTargets(
        left_rev_s=left_rev_s,
        right_rev_s=right_rev_s,
        clamped=clamped,
    )


def format_velocity_command(targets: WheelTargets) -> str:
    """좌우 목표 속도를 V 명령 문자열로 만든다. 줄 끝은 붙이지 않는다."""
    return "V {:.3f} {:.3f}".format(
        targets.left_rev_s,
        targets.right_rev_s,
    )


def flip_yaw_sign(pico_yaw_deg: float) -> float:
    """Pico의 오른쪽 회전 양수 부호를 ROS2(REP-103) 반시계 양수로 뒤집는다."""
    return -pico_yaw_deg
