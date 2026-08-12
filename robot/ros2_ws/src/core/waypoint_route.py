"""지도 위 순찰 지점 목록을 검증하고 순서를 관리한다."""

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Waypoint:
    """Nav2 목표로 전달할 지도 좌표와 방향을 표현한다."""

    name: str
    x: float
    y: float
    yaw: float


class WaypointConfigError(ValueError):
    """순찰 지점 설정이 잘못되었을 때 발생하는 예외."""


class PatrolRoute:
    """현재 목표와 다음 목표를 관리한다."""

    def __init__(
        self,
        waypoints: list[Waypoint],
        loop: bool,
        waypoint_delay_sec: float = 0.0,
        loop_delay_sec: float = 0.0,
        max_goal_retries: int = 3,
        goal_retry_delay_sec: float = 5.0,
    ) -> None:
        """순찰 지점, 반복 여부와 목표 재시도 정책을 초기화한다."""
        if not waypoints:
            raise WaypointConfigError("waypoints must not be empty")

        if (
            isinstance(max_goal_retries, bool)
            or not isinstance(max_goal_retries, int)
            or max_goal_retries < 0
        ):
            raise WaypointConfigError(
                "max_goal_retries must be zero or greater"
            )

        if (
            isinstance(goal_retry_delay_sec, bool)
            or not isinstance(goal_retry_delay_sec, (int, float))
            or not math.isfinite(goal_retry_delay_sec)
            or goal_retry_delay_sec < 0.0
        ):
            raise WaypointConfigError(
                "goal_retry_delay_sec must be zero or greater"
            )

        if max_goal_retries > 0 and goal_retry_delay_sec == 0.0:
            raise WaypointConfigError(
                "goal_retry_delay_sec must be greater than zero "
                "when retries are enabled"
            )

        self.waypoints = waypoints
        self.loop = loop
        self.waypoint_delay_sec = waypoint_delay_sec
        self.loop_delay_sec = loop_delay_sec
        self.max_goal_retries = max_goal_retries
        self.goal_retry_delay_sec = float(goal_retry_delay_sec)
        self.goal_failure_count = 0
        self.current_index = 0
        self.completed = False

    def current(self) -> Waypoint | None:
        """현재 이동해야 하는 순찰 지점을 반환한다."""
        if self.completed:
            return None

        return self.waypoints[self.current_index]

    def move_to_next(self) -> Waypoint | None:
        """다음 지점으로 이동하고 새 목표를 반환한다."""
        if self.completed:
            return None

        self.goal_failure_count = 0

        if self.current_index + 1 < len(self.waypoints):
            self.current_index += 1
            return self.current()

        if self.loop:
            self.current_index = 0
            return self.current()

        self.completed = True
        return None

    def record_goal_failure(self) -> int | None:
        """실패 횟수를 기록하고 허용된 재시도 번호를 반환한다."""
        if self.goal_failure_count >= self.max_goal_retries:
            return None

        self.goal_failure_count += 1
        return self.goal_failure_count


def load_patrol_route(path: str | Path) -> PatrolRoute:
    """YAML 파일에서 순찰 경로를 만든다."""
    config_path = Path(path)

    with config_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict):
        raise WaypointConfigError("waypoint file must contain a mapping")

    raw_waypoints = data.get("waypoints")
    if not isinstance(raw_waypoints, list):
        raise WaypointConfigError("waypoints must be a list")

    waypoints = [
        _parse_waypoint(raw_waypoint, index)
        for index, raw_waypoint in enumerate(raw_waypoints)
    ]
    loop = data.get("loop", True)

    if not isinstance(loop, bool):
        raise WaypointConfigError("loop must be true or false")

    raw_waypoint_delay_sec = data.get("waypoint_delay_sec", 0.0)

    if (
        isinstance(raw_waypoint_delay_sec, bool)
        or not isinstance(raw_waypoint_delay_sec, (int, float))
    ):
        raise WaypointConfigError(
            "waypoint_delay_sec must be a number"
        )

    waypoint_delay_sec = float(raw_waypoint_delay_sec)

    if (
        not math.isfinite(waypoint_delay_sec)
        or waypoint_delay_sec < 0.0
    ):
        raise WaypointConfigError(
            "waypoint_delay_sec must be zero or greater"
        )

    raw_loop_delay_sec = data.get("loop_delay_sec", 0.0)

    if (
        isinstance(raw_loop_delay_sec, bool)
        or not isinstance(raw_loop_delay_sec, (int, float))
    ):
        raise WaypointConfigError(
            "loop_delay_sec must be a number"
        )

    loop_delay_sec = float(raw_loop_delay_sec)

    if not math.isfinite(loop_delay_sec) or loop_delay_sec < 0.0:
        raise WaypointConfigError(
            "loop_delay_sec must be zero or greater"
        )

    max_goal_retries = data.get("max_goal_retries", 3)
    goal_retry_delay_sec = data.get("goal_retry_delay_sec", 5.0)

    return PatrolRoute(
        waypoints=waypoints,
        loop=loop,
        waypoint_delay_sec=waypoint_delay_sec,
        loop_delay_sec=loop_delay_sec,
        max_goal_retries=max_goal_retries,
        goal_retry_delay_sec=goal_retry_delay_sec,
    )


def yaw_to_quaternion(yaw: float) -> tuple[float, float, float, float]:
    """Z축 yaw 각도를 quaternion의 x, y, z, w 값으로 변환한다."""
    if not math.isfinite(yaw):
        raise WaypointConfigError("yaw must be finite")

    half_yaw = yaw / 2.0
    return 0.0, 0.0, math.sin(half_yaw), math.cos(half_yaw)


def _parse_waypoint(raw_waypoint: Any, index: int) -> Waypoint:
    if not isinstance(raw_waypoint, dict):
        raise WaypointConfigError(
            f"waypoint at index {index} must be a mapping"
        )

    name = raw_waypoint.get("name", f"waypoint_{index}")
    if not isinstance(name, str) or not name.strip():
        raise WaypointConfigError(
            f"waypoint at index {index} has invalid name"
        )

    x = _parse_finite_float(raw_waypoint, "x", index)
    y = _parse_finite_float(raw_waypoint, "y", index)
    yaw = _parse_finite_float(raw_waypoint, "yaw", index)

    return Waypoint(
        name=name,
        x=x,
        y=y,
        yaw=yaw,
    )


def _parse_finite_float(
    raw_waypoint: dict[str, Any],
    key: str,
    index: int,
) -> float:
    value = raw_waypoint.get(key)

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WaypointConfigError(
            f"waypoint at index {index} has invalid {key}"
        )

    parsed_value = float(value)
    if not math.isfinite(parsed_value):
        raise WaypointConfigError(
            f"waypoint at index {index} has non-finite {key}"
        )

    return parsed_value
