"""
사람 추종 상태와 비전 명령을 로봇 속도 명령으로 변환한다.

ROS2와 독립된 순수 제어 로직으로 구성하여 실제 로봇, Gazebo,
단위 테스트에서 동일한 계산 결과를 사용할 수 있게 한다.
"""

import math
from dataclasses import dataclass
from enum import Enum


class FollowCommand(str, Enum):
    """비전 AI가 생성하는 추종 희망 명령."""

    STOP = "stop"
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"
    MOVE_FORWARD = "move_forward"


@dataclass(frozen=True)
class VelocityCommand:
    """로봇에 전달할 평면 이동 속도 명령."""

    linear_x: float
    angular_z: float
    reason: str


class PersonFollowingController:
    """추종 명령과 라이다 거리를 안전한 속도로 변환한다."""

    def __init__(
        self,
        linear_speed: float = 0.15,
        angular_speed: float = 0.5,
        person_stop_distance_m: float = 0.5,
        person_resume_distance_m: float = 1.0,
        emergency_stop_distance_m: float = 0.3,
    ) -> None:
        """
        주행 속도와 거리별 정지 기준을 설정한다.

        사람과 0.5m 이하이면 정지하고, 정지한 뒤에는 사람이
        1.0m보다 멀어졌을 때만 전진을 다시 허용한다.
        """
        self._validate_positive(
            "linear_speed",
            linear_speed,
        )
        self._validate_positive(
            "angular_speed",
            angular_speed,
        )
        self._validate_positive(
            "person_stop_distance_m",
            person_stop_distance_m,
        )
        self._validate_positive(
            "person_resume_distance_m",
            person_resume_distance_m,
        )
        self._validate_positive(
            "emergency_stop_distance_m",
            emergency_stop_distance_m,
        )

        if person_resume_distance_m <= person_stop_distance_m:
            raise ValueError(
                "person_resume_distance_m must be greater "
                "than person_stop_distance_m."
            )

        if emergency_stop_distance_m > person_stop_distance_m:
            raise ValueError(
                "emergency_stop_distance_m must not be greater "
                "than person_stop_distance_m."
            )

        self.linear_speed = float(linear_speed)
        self.angular_speed = float(angular_speed)

        self.person_stop_distance_m = float(
            person_stop_distance_m
        )
        self.person_resume_distance_m = float(
            person_resume_distance_m
        )
        self.emergency_stop_distance_m = float(
            emergency_stop_distance_m
        )

        self._approach_enabled = False

    def calculate_velocity(
        self,
        command: FollowCommand | str,
        movement_allowed: bool,
        person_distance_m: float | None = None,
        emergency_obstacle_distance_m: float | None = None,
    ) -> VelocityCommand:
        """
        비전 명령과 라이다 거리로 로봇 속도를 계산한다.

        다중 인물이나 대상 미검출로 이동이 금지된 경우 정지한다.
        전방 장애물이 긴급 정지 거리 안에 있으면 모든 비전 명령보다
        정지를 우선한다.
        """
        if not isinstance(movement_allowed, bool):
            self._approach_enabled = False
            return self._stop(
                "invalid_movement_permission"
            )

        if not movement_allowed:
            self._approach_enabled = False
            return self._stop(
                "movement_not_allowed"
            )

        emergency_result = self._check_emergency_obstacle(
            emergency_obstacle_distance_m
        )
        if emergency_result is not None:
            return emergency_result

        person_result = self._update_person_distance(
            person_distance_m
        )
        if person_result is not None:
            return person_result

        follow_command = self._convert_command(command)

        if follow_command is FollowCommand.TURN_LEFT:
            return VelocityCommand(
                linear_x=0.0,
                angular_z=self.angular_speed,
                reason="turning_left",
            )

        if follow_command is FollowCommand.TURN_RIGHT:
            return VelocityCommand(
                linear_x=0.0,
                angular_z=-self.angular_speed,
                reason="turning_right",
            )

        if follow_command is FollowCommand.MOVE_FORWARD:
            if person_distance_m is None:
                self._approach_enabled = False
                return self._stop(
                    "person_distance_unavailable"
                )

            if not self._approach_enabled:
                return self._stop(
                    "waiting_for_person_resume_distance"
                )

            return VelocityCommand(
                linear_x=self.linear_speed,
                angular_z=0.0,
                reason="moving_forward",
            )

        self._approach_enabled = False
        return self._stop(
            "stop_requested"
        )

    def _check_emergency_obstacle(
        self,
        distance_m: float | None,
    ) -> VelocityCommand | None:
        """긴급 정지용 장애물 거리를 검사한다."""
        if distance_m is None:
            return None

        if not self._is_valid_distance(distance_m):
            self._approach_enabled = False
            return self._stop(
                "invalid_emergency_obstacle_distance"
            )

        if distance_m <= self.emergency_stop_distance_m:
            self._approach_enabled = False
            return self._stop(
                "emergency_obstacle_too_close"
            )

        return None

    def _update_person_distance(
        self,
        distance_m: float | None,
    ) -> VelocityCommand | None:
        """사람 거리로 접근 가능 상태를 갱신한다."""
        if distance_m is None:
            return None

        if not self._is_valid_distance(distance_m):
            self._approach_enabled = False
            return self._stop(
                "invalid_person_distance"
            )

        if distance_m <= self.person_stop_distance_m:
            self._approach_enabled = False
            return self._stop(
                "person_too_close"
            )

        if distance_m > self.person_resume_distance_m:
            self._approach_enabled = True

        return None

    @staticmethod
    def _convert_command(
        command: FollowCommand | str,
    ) -> FollowCommand:
        """문자열 또는 열거형 명령을 추종 명령으로 변환한다."""
        try:
            return FollowCommand(command)
        except ValueError:
            return FollowCommand.STOP

    @staticmethod
    def _stop(reason: str) -> VelocityCommand:
        """정지 속도 명령을 생성한다."""
        return VelocityCommand(
            linear_x=0.0,
            angular_z=0.0,
            reason=reason,
        )

    @staticmethod
    def _is_valid_distance(distance_m: float) -> bool:
        """거리가 유한한 비음수 값인지 확인한다."""
        return (
            not isinstance(distance_m, bool)
            and isinstance(distance_m, (int, float))
            and math.isfinite(distance_m)
            and distance_m >= 0.0
        )

    @staticmethod
    def _validate_positive(
        name: str,
        value: float,
    ) -> None:
        """설정값이 유한한 양수인지 검사한다."""
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0.0
        ):
            raise ValueError(
                f"{name} must be a positive number."
            )
