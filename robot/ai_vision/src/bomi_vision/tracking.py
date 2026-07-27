"""추적된 사람 수와 누락 프레임을 바탕으로 안전한 추적 상태를 계산한다.

외부 모델 없이 실행할 수 있는 애플리케이션 핵심 로직이며 기존 화면 위치
계산을 재사용해 한 명일 때만 대표 위치를 생성한다.
"""

from collections.abc import Sequence

from bomi_vision.domain import TrackedPerson, TrackingResult, TrackingResultStatus
from bomi_vision.position import calculate_vision_position


class UserTrackingService:
    """프레임 간 단순 누락 상태를 관리하고 최종 추적 결과를 생성한다.

    마지막 정상 Track ID의 존재 여부와 연속 누락 프레임 수만 관리한다.
    다중 인물에서는 기존 ID를 대표 사용자로 유지하지 않는다.
    """

    def __init__(self, lost_tolerance_frames: int) -> None:
        """일시 누락으로 허용할 최대 연속 프레임 수를 설정한다.

        Raises:
            ValueError: 허용 프레임 수가 음수이거나 정수가 아닌 경우.
        """
        if (
            isinstance(lost_tolerance_frames, bool)
            or not isinstance(lost_tolerance_frames, int)
            or lost_tolerance_frames < 0
        ):
            raise ValueError("Lost tolerance frames must be a non-negative integer.")
        self._lost_tolerance_frames = lost_tolerance_frames
        self._lost_frames = 0
        self._had_single_target = False

    def update(
        self,
        tracked_people: Sequence[TrackedPerson],
        frame_width: int,
        frame_height: int,
    ) -> TrackingResult:
        """현재 추적 목록을 사람 수 상태와 대표 위치 결과로 변환한다."""
        person_count = len(tracked_people)
        if person_count >= 2:
            self._clear_target()
            return TrackingResult(
                TrackingResultStatus.MULTIPLE_PEOPLE,
                person_count,
                None,
                None,
            )
        if person_count == 1:
            person = tracked_people[0]
            position_result = calculate_vision_position(
                [person.to_detection()],
                frame_width,
                frame_height,
            )
            if position_result.position is None:
                raise ValueError("A tracked person must produce a position.")
            self._had_single_target = True
            self._lost_frames = 0
            return TrackingResult(
                TrackingResultStatus.TRACKING,
                1,
                person.track_id,
                position_result.position,
            )

        if self._had_single_target:
            self._lost_frames += 1
            if self._lost_frames <= self._lost_tolerance_frames:
                return TrackingResult(
                    TrackingResultStatus.TEMPORARILY_LOST,
                    0,
                    None,
                    None,
                )
            self._clear_target()
        return TrackingResult(TrackingResultStatus.NOT_FOUND, 0, None, None)

    def _clear_target(self) -> None:
        """대표 사용자를 유지하지 않아야 하는 상태에서 누락 이력을 초기화한다."""
        self._had_single_target = False
        self._lost_frames = 0
