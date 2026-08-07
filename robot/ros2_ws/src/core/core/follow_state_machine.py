"""
사람 추종 주행의 안전 상태 전환을 관리한다.

비전 AI 결과를 바탕으로 추종 허용 여부를 결정한다.
여러 사람이 감지되면 즉시 정지하고, 다시 한 명만 감지되면
같은 Track ID가 설정 시간 동안 유지된 뒤 추종을 재개한다.
"""

import math
from dataclasses import dataclass
from enum import Enum


class VisionTrackingStatus(str, Enum):
    """비전 AI가 제공하는 사람 추적 상태."""

    NOT_DETECTED = "not_detected"
    TRACKING = "tracking"
    TEMPORARILY_LOST = "temporarily_lost"
    MULTIPLE_PENDING = "multiple_pending"
    MULTIPLE_PERSONS = "multiple_persons"
    SINGLE_RECOVERY = "single_recovery"
    INVALID = "invalid"


class FollowState(str, Enum):
    """로봇 사람 추종 기능의 현재 상태."""

    WAITING_TARGET = "waiting_target"
    FOLLOWING = "following"
    MULTIPLE_OBSERVING = "multiple_observing"
    MULTIPLE_LOCKED = "multiple_locked"
    TEMPORARILY_LOST = "temporarily_lost"
    DISABLED = "disabled"


@dataclass(frozen=True)
class FollowDecision:
    """상태 머신이 결정한 현재 추종 동작."""

    state: FollowState
    movement_allowed: bool
    reason: str
    target_track_id: int | None


class FollowStateMachine:
    """사람 추종의 시작, 정지와 다중 인물 상태를 관리한다."""

    def __init__(
        self,
        multiple_observation_sec: float = 3.0,
        single_recovery_sec: float = 1.0,
        lost_timeout_sec: float = 1.0,
        target_confirm_sec: float = 0.5,
    ) -> None:
        """사람 추종 상태 전환에 사용할 시간 기준을 설정한다."""
        self._validate_positive(
            "multiple_observation_sec",
            multiple_observation_sec,
        )
        self._validate_positive(
            "single_recovery_sec",
            single_recovery_sec,
        )
        self._validate_positive(
            "lost_timeout_sec",
            lost_timeout_sec,
        )
        self._validate_positive(
            "target_confirm_sec",
            target_confirm_sec,
        )

        self.multiple_observation_sec = float(
            multiple_observation_sec
        )
        self.single_recovery_sec = float(single_recovery_sec)
        self.lost_timeout_sec = float(lost_timeout_sec)
        self.target_confirm_sec = float(target_confirm_sec)

        self.state = FollowState.WAITING_TARGET
        self.target_track_id: int | None = None

        self._state_entered_at = 0.0
        self._last_update_sec: float | None = None

        self._candidate_track_id: int | None = None
        self._candidate_started_at: float | None = None

        self._multiple_started_at: float | None = None
        self._single_recovery_started_at: float | None = None

    def update(
        self,
        status: VisionTrackingStatus | str,
        track_id: int | None,
        now_sec: float,
    ) -> FollowDecision:
        """새 비전 결과를 반영해 추종 상태와 이동 허용 여부를 결정한다."""
        self._validate_time(now_sec)

        if (
            self._last_update_sec is not None
            and now_sec < self._last_update_sec
        ):
            self._last_update_sec = now_sec

            if self.state is FollowState.DISABLED:
                return self._decision(
                    False,
                    "following_disabled",
                )

            if self.state is FollowState.MULTIPLE_LOCKED:
                return self._decision(
                    False,
                    "multiple_people_locked",
                )

            self._reset_internal(now_sec)

            return self._decision(
                False,
                "clock_moved_backward",
            )

        self._last_update_sec = now_sec
        tracking_status = self._convert_status(status)

        if not self._is_valid_track_id(track_id):
            track_id = None

            if tracking_status is VisionTrackingStatus.TRACKING:
                tracking_status = VisionTrackingStatus.INVALID

        if self.state is FollowState.DISABLED:
            return self._decision(False, "following_disabled")

        if self.state is FollowState.MULTIPLE_LOCKED:
            return self._decision(False, "multiple_people_locked")

        if tracking_status is VisionTrackingStatus.MULTIPLE_PENDING:
            self._clear_candidate()
            self._single_recovery_started_at = None

            return self._decision(
                False,
                "multiple_people_pending",
            )

        if tracking_status is VisionTrackingStatus.MULTIPLE_PERSONS:
            return self._handle_multiple_people(now_sec)

        if tracking_status is VisionTrackingStatus.SINGLE_RECOVERY:
            self._clear_target()
            self._single_recovery_started_at = None

            if self.state is not FollowState.MULTIPLE_OBSERVING:
                self._transition(
                    FollowState.MULTIPLE_OBSERVING,
                    now_sec,
                )

            return self._decision(
                False,
                "single_recovery_stabilizing",
            )

        if self.state is FollowState.MULTIPLE_OBSERVING:
            return self._handle_multiple_observing(
                tracking_status,
                track_id,
                now_sec,
            )

        if self.state is FollowState.TEMPORARILY_LOST:
            return self._handle_temporarily_lost(
                tracking_status,
                track_id,
                now_sec,
            )

        if self.state is FollowState.FOLLOWING:
            return self._handle_following(
                tracking_status,
                track_id,
                now_sec,
            )

        return self._handle_waiting_target(
            tracking_status,
            track_id,
            now_sec,
        )

    def handle_vision_timeout(
        self,
        now_sec: float,
    ) -> FollowDecision:
        """비전 입력이 끊겼을 때 안전한 상태로 전환한다."""
        self._validate_time(now_sec)

        if (
            self._last_update_sec is not None
            and now_sec < self._last_update_sec
        ):
            self._last_update_sec = now_sec

            if self.state is FollowState.DISABLED:
                return self._decision(
                    False,
                    "following_disabled",
                )

            if self.state is FollowState.MULTIPLE_LOCKED:
                return self._decision(
                    False,
                    "multiple_people_locked",
                )

            self._reset_internal(now_sec)

            return self._decision(
                False,
                "clock_moved_backward",
            )

        self._last_update_sec = now_sec

        if self.state is FollowState.DISABLED:
            return self._decision(False, "following_disabled")

        if self.state is FollowState.MULTIPLE_LOCKED:
            return self._decision(False, "multiple_people_locked")

        if self.state is FollowState.MULTIPLE_OBSERVING:
            self._reset_internal(now_sec)

            return self._decision(
                False,
                "vision_timeout_during_multiple_observation",
            )

        self._reset_internal(now_sec)

        return self._decision(
            False,
            "vision_command_timeout",
        )

    def disable(self, now_sec: float) -> FollowDecision:
        """사람 추종 기능을 비활성화하고 즉시 정지 상태로 전환한다."""
        self._validate_time(now_sec)

        self._last_update_sec = now_sec
        self._clear_target()
        self._clear_multiple_observation()
        self._transition(FollowState.DISABLED, now_sec)

        return self._decision(False, "following_disabled")

    def enable(self, now_sec: float) -> FollowDecision:
        """비활성화된 기능을 다시 대상 대기 상태로 전환한다."""
        self._validate_time(now_sec)

        self._last_update_sec = now_sec
        self._reset_internal(now_sec)

        return self._decision(False, "waiting_for_target")

    def reset_lock(self, now_sec: float) -> FollowDecision:
        """다중 인물 추종 잠금을 해제하고 새 대상을 기다린다."""
        self._validate_time(now_sec)
        self._last_update_sec = now_sec

        if self.state is not FollowState.MULTIPLE_LOCKED:
            return self._decision(
                self.state is FollowState.FOLLOWING,
                "following_lock_not_active",
            )

        self._reset_internal(now_sec)

        return self._decision(False, "following_lock_reset")

    def _handle_waiting_target(
        self,
        status: VisionTrackingStatus,
        track_id: int | None,
        now_sec: float,
    ) -> FollowDecision:
        """한 명의 대상이 안정적으로 확인될 때까지 정지한다."""
        if (
            status is not VisionTrackingStatus.TRACKING
            or track_id is None
        ):
            self._clear_candidate()
            return self._decision(False, "waiting_for_target")

        if self._candidate_track_id != track_id:
            self._candidate_track_id = track_id
            self._candidate_started_at = now_sec

            return self._decision(False, "confirming_target")

        if self._candidate_started_at is None:
            self._candidate_started_at = now_sec

            return self._decision(False, "confirming_target")

        elapsed_sec = now_sec - self._candidate_started_at

        if elapsed_sec < self.target_confirm_sec:
            return self._decision(False, "confirming_target")

        self.target_track_id = track_id
        self._clear_candidate()
        self._transition(FollowState.FOLLOWING, now_sec)

        return self._decision(True, "target_confirmed")

    def _handle_following(
        self,
        status: VisionTrackingStatus,
        track_id: int | None,
        now_sec: float,
    ) -> FollowDecision:
        """현재 추종 대상이 계속 유효한지 확인한다."""
        if status is VisionTrackingStatus.TRACKING:
            if track_id == self.target_track_id:
                return self._decision(True, "target_tracking")

            self._clear_target()
            self._transition(FollowState.WAITING_TARGET, now_sec)

            if track_id is not None:
                self._candidate_track_id = track_id
                self._candidate_started_at = now_sec

            return self._decision(False, "target_changed")

        if status is VisionTrackingStatus.TEMPORARILY_LOST:
            self._transition(
                FollowState.TEMPORARILY_LOST,
                now_sec,
            )

            return self._decision(
                False,
                "target_temporarily_lost",
            )

        self._clear_target()
        self._transition(FollowState.WAITING_TARGET, now_sec)

        if status is VisionTrackingStatus.NOT_DETECTED:
            return self._decision(False, "target_not_found")

        return self._decision(
            False,
            "invalid_tracking_result",
        )

    def _handle_temporarily_lost(
        self,
        status: VisionTrackingStatus,
        track_id: int | None,
        now_sec: float,
    ) -> FollowDecision:
        """일시적으로 놓친 기존 대상의 복귀를 기다린다."""
        if status is VisionTrackingStatus.TRACKING:
            if track_id == self.target_track_id:
                self._transition(FollowState.FOLLOWING, now_sec)

                return self._decision(
                    True,
                    "target_recovered",
                )

            self._clear_target()
            self._transition(FollowState.WAITING_TARGET, now_sec)

            if track_id is not None:
                self._candidate_track_id = track_id
                self._candidate_started_at = now_sec

            return self._decision(
                False,
                "different_target_detected",
            )

        elapsed_sec = now_sec - self._state_entered_at

        if elapsed_sec >= self.lost_timeout_sec:
            self._clear_target()
            self._transition(FollowState.WAITING_TARGET, now_sec)

            return self._decision(
                False,
                "target_lost_timeout",
            )

        return self._decision(
            False,
            "target_temporarily_lost",
        )

    def _handle_multiple_people(
        self,
        now_sec: float,
    ) -> FollowDecision:
        """여러 사람이 보이면 즉시 정지한다."""
        self._clear_candidate()
        self._single_recovery_started_at = None
        self.target_track_id = None

        if self.state is not FollowState.MULTIPLE_OBSERVING:
            self._transition(
                FollowState.MULTIPLE_OBSERVING,
                now_sec,
            )

        return self._decision(
            False,
            "multiple_people_observing",
        )

    def _handle_multiple_observing(
        self,
        status: VisionTrackingStatus,
        track_id: int | None,
        now_sec: float,
    ) -> FollowDecision:
        """같은 Track ID가 안정적으로 유지될 때만 추종을 재개한다."""
        if (
            status is not VisionTrackingStatus.TRACKING
            or track_id is None
        ):
            self._clear_candidate()
            self._single_recovery_started_at = None

            return self._decision(
                False,
                "multiple_people_observing",
            )

        if self._candidate_track_id != track_id:
            self._candidate_track_id = track_id
            self._single_recovery_started_at = now_sec

            return self._decision(
                False,
                "single_target_recovery_confirming",
            )

        if self._single_recovery_started_at is None:
            self._single_recovery_started_at = now_sec

            return self._decision(
                False,
                "single_target_recovery_confirming",
            )

        elapsed_sec = now_sec - self._single_recovery_started_at

        if elapsed_sec < self.single_recovery_sec:
            return self._decision(
                False,
                "single_target_recovery_confirming",
            )

        self.target_track_id = track_id
        self._clear_candidate()
        self._clear_multiple_observation()
        self._transition(FollowState.FOLLOWING, now_sec)

        return self._decision(
            True,
            "single_target_recovered",
        )

    def _lock_multiple_people(self, now_sec: float) -> None:
        """여러 사람 상태가 지속되면 자동 추종을 잠근다."""
        self._clear_target()
        self._clear_multiple_observation()
        self._transition(FollowState.MULTIPLE_LOCKED, now_sec)

    def _reset_internal(self, now_sec: float) -> None:
        """모든 추적 정보를 지우고 대상 대기 상태로 초기화한다."""
        self._clear_target()
        self._clear_multiple_observation()
        self._transition(FollowState.WAITING_TARGET, now_sec)

    def _clear_target(self) -> None:
        """현재 추종 대상과 후보 정보를 제거한다."""
        self.target_track_id = None
        self._clear_candidate()

    def _clear_candidate(self) -> None:
        """대상 확인 중 저장한 후보 정보를 제거한다."""
        self._candidate_track_id = None
        self._candidate_started_at = None

    def _clear_multiple_observation(self) -> None:
        """다중 인물 관찰에 사용한 시간 정보를 제거한다."""
        self._multiple_started_at = None
        self._single_recovery_started_at = None

    def _transition(
        self,
        new_state: FollowState,
        now_sec: float,
    ) -> None:
        """현재 상태와 상태 진입 시각을 변경한다."""
        self.state = new_state
        self._state_entered_at = now_sec

    def _decision(
        self,
        movement_allowed: bool,
        reason: str,
    ) -> FollowDecision:
        """현재 상태를 바탕으로 불변 결정 객체를 생성한다."""
        return FollowDecision(
            state=self.state,
            movement_allowed=movement_allowed,
            reason=reason,
            target_track_id=self.target_track_id,
        )

    @staticmethod
    def _convert_status(
        status: VisionTrackingStatus | str,
    ) -> VisionTrackingStatus:
        """문자열 또는 열거형 입력을 비전 상태로 변환한다."""
        try:
            return VisionTrackingStatus(status)
        except ValueError:
            return VisionTrackingStatus.INVALID

    @staticmethod
    def _is_valid_track_id(track_id: int | None) -> bool:
        """Track ID가 선택적 비음수 정수인지 확인한다."""
        return (
            track_id is None
            or (
                not isinstance(track_id, bool)
                and isinstance(track_id, int)
                and track_id >= 0
            )
        )

    @staticmethod
    def _validate_positive(
        name: str,
        value: float,
    ) -> None:
        """시간 설정값이 유한한 양수인지 확인한다."""
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0.0
        ):
            raise ValueError(
                f"{name} must be a positive number."
            )

    @staticmethod
    def _validate_time(now_sec: float) -> None:
        """현재 시각이 유한한 숫자인지 확인한다."""
        if (
            isinstance(now_sec, bool)
            or not isinstance(now_sec, (int, float))
            or not math.isfinite(now_sec)
        ):
            raise ValueError(
                "now_sec must be a finite number."
            )
