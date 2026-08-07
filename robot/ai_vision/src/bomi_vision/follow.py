"""사용자 추적 결과를 안전한 추종 희망 명령으로 변환한다.

외부 비전 및 모터 라이브러리에 의존하지 않으며 현재 프레임의 대표 위치만
사용한다. 불확실한 추적 상태나 유효하지 않은 값은 항상 정지로 변환한다.
"""

import math

from bomi_vision.domain import (
    FollowCommand,
    FollowCommandResult,
    TrackingResult,
    TrackingResultStatus,
)


class FollowCommandGenerator:
    """화면 위치 임계값으로 추종 희망 방향과 판단 이유를 생성한다.

    수평 정렬을 거리 판단보다 우선하며, 중앙에 정렬된 경우에만 화면 대비
    사용자 높이로 전진 여부를 판단한다. 후진 명령은 생성하지 않는다.
    """

    def __init__(
        self,
        horizontal_dead_zone: float,
        forward_threshold: float,
    ) -> None:
        """카메라 환경에 맞춰 조정할 초기 판단 임계값을 검증한다.

        Args:
            horizontal_dead_zone: 중앙으로 취급할 수평 오프셋 절댓값의 상한.
            forward_threshold: 전진을 멈출 화면 높이 대비 사용자 박스 비율.

        Raises:
            ValueError: 임계값이 유한하지 않거나 허용 범위를 벗어난 경우.
        """
        if (
            isinstance(horizontal_dead_zone, bool)
            or not isinstance(horizontal_dead_zone, (int, float))
            or not math.isfinite(horizontal_dead_zone)
            or not 0.0 <= horizontal_dead_zone < 1.0
        ):
            raise ValueError("Horizontal dead zone must be from 0.0 inclusive to 1.0 exclusive.")
        if (
            isinstance(forward_threshold, bool)
            or not isinstance(forward_threshold, (int, float))
            or not math.isfinite(forward_threshold)
            or not 0.0 <= forward_threshold <= 1.0
        ):
            raise ValueError("Forward threshold must be between 0.0 and 1.0.")
        self._horizontal_dead_zone = float(horizontal_dead_zone)
        self._forward_threshold = float(forward_threshold)

    def generate(self, tracking_result: TrackingResult) -> FollowCommandResult:
        """현재 프레임의 추적 결과에서 추종 희망 명령을 생성한다.

        유효하지 않은 조합이나 위치값은 예외를 전파해 이동을 계속하지 않고
        ``STOP``과 ``invalid_tracking_result`` 이유로 안전하게 반환한다.
        """
        if tracking_result.status is TrackingResultStatus.NOT_DETECTED:
            return self._stop("tracking_not_available")
        if tracking_result.status is TrackingResultStatus.TEMPORARILY_LOST:
            return self._stop("temporarily_lost")
        if tracking_result.status is TrackingResultStatus.MULTIPLE_PENDING:
            return self._stop("multiple_people_pending")
        if tracking_result.status is TrackingResultStatus.MULTIPLE_PERSONS:
            return self._stop("multiple_people_detected")
        if tracking_result.status is TrackingResultStatus.SINGLE_RECOVERY:
            return self._stop("single_recovery_stabilizing")
        if tracking_result.status is not TrackingResultStatus.TRACKING:
            return self._stop("invalid_tracking_result")
        if tracking_result.position is None:
            return self._stop("position_missing")
        if tracking_result.track_id is None:
            return self._stop("track_id_missing")

        position = tracking_result.position
        if not self._is_valid_position(position.offset_x, position.height_ratio):
            return self._stop("invalid_tracking_result")
        if position.offset_x < -self._horizontal_dead_zone:
            return FollowCommandResult(
                FollowCommand.TURN_LEFT,
                "user_left_of_center",
                tracking_result.track_id,
            )
        if position.offset_x > self._horizontal_dead_zone:
            return FollowCommandResult(
                FollowCommand.TURN_RIGHT,
                "user_right_of_center",
                tracking_result.track_id,
            )
        if position.height_ratio < self._forward_threshold:
            return FollowCommandResult(
                FollowCommand.MOVE_FORWARD,
                "user_far_and_centered",
                tracking_result.track_id,
            )
        return FollowCommandResult(
            FollowCommand.STOP,
            "safe_follow_distance_reached",
            tracking_result.track_id,
        )

    @staticmethod
    def _is_valid_position(offset_x: float, height_ratio: float) -> bool:
        """추종 판단에 필요한 정규화 위치값의 범위를 검사한다."""
        return (
            math.isfinite(offset_x)
            and math.isfinite(height_ratio)
            and -1.0 <= offset_x <= 1.0
            and 0.0 <= height_ratio <= 1.0
        )

    @staticmethod
    def _stop(reason: str) -> FollowCommandResult:
        """대표 대상이 불확실할 때 Track ID 없이 정지 결과를 생성한다."""
        return FollowCommandResult(FollowCommand.STOP, reason, None)
