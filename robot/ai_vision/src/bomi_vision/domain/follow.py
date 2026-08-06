"""사용자 위치에서 생성한 추종 희망 명령의 도메인 계약을 정의한다.

이 명령은 후속 주행 제어 모듈이 참고할 희망 방향이며 모터의 선속도나
각속도를 직접 제어하거나 안전한 주행을 보장하지 않는다.
"""

from dataclasses import dataclass
from enum import Enum


class FollowCommand(str, Enum):
    """비전 모듈이 생성할 수 있는 추종 희망 방향을 표현한다."""

    STOP = "stop"
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"
    MOVE_FORWARD = "move_forward"


@dataclass(frozen=True)
class FollowCommandResult:
    """한 프레임의 추종 희망 명령과 판단 근거를 표현한다.

    ``track_id``는 실제 사용자 신원이 아니라 명령 판단에 사용한 현재
    영상 흐름의 임시 추적 식별자다. 대상을 신뢰할 수 없으면 ``None``이다.
    """

    command: FollowCommand
    reason: str
    track_id: int | None

    def __post_init__(self) -> None:
        """판단 이유와 선택적 Track ID의 최소 계약을 검증한다."""
        if not self.reason:
            raise ValueError("Follow command reason must not be empty.")
        if self.track_id is not None and (
            isinstance(self.track_id, bool)
            or not isinstance(self.track_id, int)
            or self.track_id < 0
        ):
            raise ValueError("Follow command Track ID must be a non-negative integer.")
