"""사람 수와 이전 상태로 보호대상자 추적 상태 머신을 갱신한다.

`docs/state-machine.md` §3의 6개 상태와 §10 전환표를 구현한다. 외부 모델 없이
실행할 수 있는 애플리케이션 핵심 로직이며, 기존 화면 위치 계산을 재사용해
정상 추적 상태에서만 대표 위치를 생성한다.

입력은 현재 프레임의 추적 목록과 프레임 크기이고 출력은 `TrackingResult`다.
한 프레임의 관찰만으로 다중 인물 확정이나 정상 추적 복귀를 결정하지 않으므로,
같은 사람 수를 입력해도 이전 상태에 따라 결과가 달라진다는 점에 주의한다.
"""

from collections.abc import Sequence

from bomi_vision.domain import TrackedPerson, TrackingResult, TrackingResultStatus
from bomi_vision.position import calculate_vision_position


class UserTrackingService:
    """프레임 간 사람 수 관찰을 누적해 보호대상자 추적 상태를 관리한다.

    현재 상태와 세 개의 히스테리시스 카운터(일시 누락 프레임, 다중 인물 확인
    프레임, 한 명 복귀 안정화 프레임)를 내부 상태로 유지하므로 인스턴스를
    프레임마다 새로 만들면 안 되고, 여러 영상 흐름에서 공유해서도 안 된다.

    다중 인물 상황에서는 기존 Track ID를 대표 사용자로 유지하지 않는다.
    상태 판단은 외부 라이브러리에 의존하지 않으며 대표 위치 계산만
    기존 위치 계산 함수에 위임한다.
    """

    def __init__(
        self,
        *,
        lost_tolerance_frames: int,
        multiple_confirm_frames: int,
        single_recovery_frames: int,
    ) -> None:
        """상태 전환에 사용할 프레임 기준값을 검증하고 초기 상태를 설정한다.

        기본값은 코드에 두지 않고 실행 설정에서 주입한다
        (`docs/state-machine.md` §25).

        Args:
            lost_tolerance_frames: 일시 누락으로 허용할 최대 연속 0명 프레임 수.
                0이면 한 프레임만 놓쳐도 대상을 폐기한다.
            multiple_confirm_frames: 다중 인물을 확정할 연속 2명 이상 프레임 수.
            single_recovery_frames: 정상 추적으로 복귀할 연속 1명 프레임 수.

        Raises:
            ValueError: 누락 허용 프레임 수가 음수이거나, 확인 및 복귀 프레임
                수가 1 미만이거나, 정수가 아닌 경우.
        """
        if (
            isinstance(lost_tolerance_frames, bool)
            or not isinstance(lost_tolerance_frames, int)
            or lost_tolerance_frames < 0
        ):
            raise ValueError("Lost tolerance frames must be a non-negative integer.")
        # 확인과 복귀는 최소 한 프레임의 관찰이 필요하다(vision-requirements §9.4).
        if (
            isinstance(multiple_confirm_frames, bool)
            or not isinstance(multiple_confirm_frames, int)
            or multiple_confirm_frames < 1
        ):
            raise ValueError("Multiple confirm frames must be a positive integer.")
        if (
            isinstance(single_recovery_frames, bool)
            or not isinstance(single_recovery_frames, int)
            or single_recovery_frames < 1
        ):
            raise ValueError("Single recovery frames must be a positive integer.")
        self._lost_tolerance_frames = lost_tolerance_frames
        self._multiple_confirm_frames = multiple_confirm_frames
        self._single_recovery_frames = single_recovery_frames
        # 첫 프레임이 들어오기 전에는 보호대상자가 없다(state-machine §11).
        self._state = TrackingResultStatus.NOT_DETECTED
        self._lost_frames = 0
        self._multiple_frames = 0
        self._recovery_frames = 0
        # 다중 인물 완충 중 모든 사람이 사라졌을 때의 전환 대상을 결정하는 이력이다.
        self._had_single_target = False

    @property
    def state(self) -> TrackingResultStatus:
        """현재 보관 중인 사람 추적 상태를 반환한다."""
        return self._state

    def update_state(self, person_count: int) -> TrackingResultStatus:
        """현재 프레임의 사람 수를 반영해 추적 상태를 갱신한다.

        한 프레임의 다중 인물 검출을 즉시 확정하지 않고, 다중 인물 상태에서
        한 명으로 돌아온 경우에도 안정화가 끝날 때까지 정상 추적을 허용하지
        않는다(`docs/state-machine.md` §10).

        Args:
            person_count: 현재 프레임에서 유효하다고 판단된 사람 수.

        Returns:
            이전 상태와 현재 사람 수를 반영한 새로운 추적 상태.

        Raises:
            ValueError: 사람 수가 0 이상의 정수가 아닌 경우.

        Side Effects:
            내부 상태와 히스테리시스 카운터를 갱신한다.
        """
        # 잘못된 사람 수를 0명으로 대체하면 미검출과 구분할 수 없다(state-machine §12).
        if isinstance(person_count, bool) or not isinstance(person_count, int):
            raise ValueError("Person count must be a non-negative integer.")
        if person_count < 0:
            raise ValueError("Person count must be a non-negative integer.")

        if self._state is TrackingResultStatus.TRACKING:
            self._state = self._next_from_tracking(person_count)
        elif self._state is TrackingResultStatus.TEMPORARILY_LOST:
            self._state = self._next_from_temporarily_lost(person_count)
        elif self._state is TrackingResultStatus.MULTIPLE_PENDING:
            self._state = self._next_from_multiple_pending(person_count)
        elif self._state is TrackingResultStatus.MULTIPLE_PERSONS:
            self._state = self._next_from_multiple_persons(person_count)
        elif self._state is TrackingResultStatus.SINGLE_RECOVERY:
            self._state = self._next_from_single_recovery(person_count)
        else:
            self._state = self._next_from_not_detected(person_count)
        return self._state

    def update(
        self,
        tracked_people: Sequence[TrackedPerson],
        frame_width: int,
        frame_height: int,
    ) -> TrackingResult:
        """현재 추적 목록을 상태 머신에 반영하고 최종 추적 결과를 만든다.

        Args:
            tracked_people: 현재 프레임에서 추적된 모든 사람.
            frame_width: 픽셀 단위 프레임 너비.
            frame_height: 픽셀 단위 프레임 높이.

        Returns:
            갱신된 상태와, 정상 추적일 때의 대표 Track ID 및 화면 위치.

        Raises:
            ValueError: 프레임 크기나 한 명의 추적 결과가 유효하지 않은 경우.

        Side Effects:
            내부 상태와 히스테리시스 카운터를 갱신한다.
        """
        person_count = len(tracked_people)
        status = self.update_state(person_count)
        if status is not TrackingResultStatus.TRACKING:
            # 안전 규칙: 완충 및 예외 상태에서는 대표 대상을 제공하지 않는다
            # (vision-requirements §7.3, state-machine §7.3, §9.3).
            return TrackingResult(status, person_count, None, None)

        person = tracked_people[0]
        position_result = calculate_vision_position(
            [person.to_detection()],
            frame_width,
            frame_height,
        )
        if position_result.position is None:
            raise ValueError("A tracked person must produce a position.")
        return TrackingResult(
            TrackingResultStatus.TRACKING,
            1,
            person.track_id,
            position_result.position,
        )

    def _next_from_not_detected(self, person_count: int) -> TrackingResultStatus:
        """미검출 상태에서의 전환을 결정한다(state-machine §4.4)."""
        if person_count == 0:
            return self._enter_not_detected()
        if person_count == 1:
            return self._enter_tracking()
        return self._enter_multiple_pending()

    def _next_from_tracking(self, person_count: int) -> TrackingResultStatus:
        """정상 추적 상태에서의 전환을 결정한다(state-machine §5.4)."""
        if person_count == 0:
            return self._enter_temporarily_lost()
        if person_count == 1:
            return self._enter_tracking()
        return self._enter_multiple_pending()

    def _next_from_temporarily_lost(self, person_count: int) -> TrackingResultStatus:
        """일시 누락 상태에서의 전환을 결정한다(state-machine §6.5)."""
        if person_count == 0:
            return self._continue_temporarily_lost()
        if person_count == 1:
            return self._enter_tracking()
        return self._enter_multiple_pending()

    def _next_from_multiple_pending(self, person_count: int) -> TrackingResultStatus:
        """다중 인물 확인 중의 전환을 결정한다(state-machine §7.5)."""
        if person_count == 0:
            # 다중 인물 검출 직전까지 한 명을 추적하고 있었다면 순간적인 가림일 수
            # 있으므로 곧바로 대상을 폐기하지 않고 일시 누락으로 완충한다.
            if self._had_single_target:
                return self._enter_temporarily_lost()
            return self._enter_not_detected()
        if person_count == 1:
            return self._enter_tracking()
        return self._continue_multiple_pending()

    def _next_from_multiple_persons(self, person_count: int) -> TrackingResultStatus:
        """다중 인물 확정 상태에서의 전환을 결정한다(state-machine §8.4)."""
        if person_count == 0:
            return self._enter_not_detected()
        if person_count == 1:
            return self._enter_single_recovery()
        return self._confirm_multiple_persons()

    def _next_from_single_recovery(self, person_count: int) -> TrackingResultStatus:
        """한 명 복귀 안정화 상태에서의 전환을 결정한다(state-machine §9.5)."""
        if person_count == 0:
            return self._enter_not_detected()
        if person_count == 1:
            return self._continue_single_recovery()
        # 이미 확정된 다중 인물이 다시 관찰됐으므로 확인 단계를 거치지 않는다.
        return self._confirm_multiple_persons()

    def _enter_not_detected(self) -> TrackingResultStatus:
        """대상을 폐기하고 모든 관찰 이력을 초기화한다."""
        self._lost_frames = 0
        self._multiple_frames = 0
        self._recovery_frames = 0
        self._had_single_target = False
        return TrackingResultStatus.NOT_DETECTED

    def _enter_tracking(self) -> TrackingResultStatus:
        """정상 추적으로 진입하거나 유지하며 완충 카운터를 초기화한다."""
        self._lost_frames = 0
        self._multiple_frames = 0
        self._recovery_frames = 0
        self._had_single_target = True
        return TrackingResultStatus.TRACKING

    def _enter_temporarily_lost(self) -> TrackingResultStatus:
        """직전 단일 대상 이력을 근거로 일시 누락 관찰을 시작한다.

        다중 인물 완충을 거쳐 돌아온 경우에도 관찰 창을 다시 시작한다. 일시
        누락은 대표 대상을 제공하지 않는 상태이므로 창을 연장해도 안전 정책이
        완화되지 않는다.
        """
        self._multiple_frames = 0
        self._recovery_frames = 0
        self._lost_frames = 1
        if self._lost_frames > self._lost_tolerance_frames:
            return self._enter_not_detected()
        return TrackingResultStatus.TEMPORARILY_LOST

    def _continue_temporarily_lost(self) -> TrackingResultStatus:
        """누락이 이어지는 동안 허용 범위 초과 여부를 확인한다."""
        self._lost_frames += 1
        if self._lost_frames > self._lost_tolerance_frames:
            return self._enter_not_detected()
        return TrackingResultStatus.TEMPORARILY_LOST

    def _enter_multiple_pending(self) -> TrackingResultStatus:
        """다중 인물 확인을 시작한다.

        한 프레임의 중복 탐지나 순간적인 방문자로 확정 상태에 가지 않도록
        첫 프레임은 확인 기준과 무관하게 완충 상태로 처리한다
        (vision-requirements §4.6.1).
        """
        self._lost_frames = 0
        self._recovery_frames = 0
        self._multiple_frames = 1
        return TrackingResultStatus.MULTIPLE_PENDING

    def _continue_multiple_pending(self) -> TrackingResultStatus:
        """다중 인물 검출이 확인 기준까지 지속됐는지 판단한다."""
        self._multiple_frames += 1
        if self._multiple_frames >= self._multiple_confirm_frames:
            return self._confirm_multiple_persons()
        return TrackingResultStatus.MULTIPLE_PENDING

    def _confirm_multiple_persons(self) -> TrackingResultStatus:
        """다중 인물을 확정하고 이전 단일 대상 이력을 신뢰하지 않는다."""
        self._lost_frames = 0
        self._recovery_frames = 0
        self._had_single_target = False
        return TrackingResultStatus.MULTIPLE_PERSONS

    def _enter_single_recovery(self) -> TrackingResultStatus:
        """한 명 복귀 안정화를 시작한다.

        다중 인물이 해제된 직후의 한 명이 기존 보호대상자인지 확인할 수 없으므로
        복귀 기준과 무관하게 첫 프레임은 안정화 상태로 처리한다
        (vision-requirements §4.6.6).
        """
        self._lost_frames = 0
        self._multiple_frames = 0
        self._recovery_frames = 1
        return TrackingResultStatus.SINGLE_RECOVERY

    def _continue_single_recovery(self) -> TrackingResultStatus:
        """한 명 상태가 복귀 기준까지 안정적으로 유지됐는지 판단한다."""
        self._recovery_frames += 1
        if self._recovery_frames >= self._single_recovery_frames:
            return self._enter_tracking()
        return TrackingResultStatus.SINGLE_RECOVERY
