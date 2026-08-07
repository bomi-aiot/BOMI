"""ROS 점유지도와 웨이포인트 YAML을 다루는 순수 로직이다."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import yaml


class WaypointEditorError(ValueError):
    """지도 또는 웨이포인트 입력이 올바르지 않을 때 발생한다."""


@dataclass(frozen=True)
class MapMetadata:
    """ROS map_server 지도 좌표 변환에 필요한 메타데이터다."""

    yaml_path: Path
    image_path: Path
    resolution: float
    origin_x: float
    origin_y: float
    origin_yaw: float


@dataclass(frozen=True)
class Waypoint:
    """지도 좌표계의 이름 있는 순찰 지점을 나타낸다."""

    name: str
    x: float
    y: float
    yaw: float


def load_map_metadata(path: str | Path) -> MapMetadata:
    """map_server YAML을 읽고 이미지 경로와 좌표 정보를 검증한다."""

    yaml_path = Path(path).resolve()
    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise WaypointEditorError(f"지도 YAML을 읽을 수 없습니다: {error}") from error

    if not isinstance(raw, dict):
        raise WaypointEditorError("지도 YAML 최상위 값은 객체여야 합니다.")

    image = raw.get("image")
    origin = raw.get("origin")
    resolution = raw.get("resolution")
    if not isinstance(image, str) or not image.strip():
        raise WaypointEditorError("지도 YAML에 image 경로가 필요합니다.")
    if not isinstance(origin, list) or len(origin) != 3:
        raise WaypointEditorError("지도 origin은 [x, y, yaw] 형식이어야 합니다.")

    values = [resolution, *origin]
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise WaypointEditorError("resolution과 origin은 유한한 숫자여야 합니다.")
    numbers = [float(value) for value in values]
    if not all(math.isfinite(value) for value in numbers) or numbers[0] <= 0.0:
        raise WaypointEditorError("resolution은 양수이고 origin은 유한해야 합니다.")

    image_path = Path(image).expanduser()
    if not image_path.is_absolute():
        image_path = yaml_path.parent / image_path
    image_path = image_path.resolve()
    if not image_path.is_file():
        raise WaypointEditorError(f"지도 이미지를 찾을 수 없습니다: {image_path}")

    return MapMetadata(
        yaml_path=yaml_path,
        image_path=image_path,
        resolution=numbers[0],
        origin_x=numbers[1],
        origin_y=numbers[2],
        origin_yaw=numbers[3],
    )


def pixel_to_world(
    pixel_x: float,
    pixel_y: float,
    image_height: int,
    metadata: MapMetadata,
) -> tuple[float, float]:
    """이미지의 좌상단 픽셀 좌표를 ROS 지도 좌표로 변환한다."""

    local_x = pixel_x * metadata.resolution
    local_y = (image_height - pixel_y) * metadata.resolution
    cosine = math.cos(metadata.origin_yaw)
    sine = math.sin(metadata.origin_yaw)
    return (
        metadata.origin_x + cosine * local_x - sine * local_y,
        metadata.origin_y + sine * local_x + cosine * local_y,
    )


def world_to_pixel(
    world_x: float,
    world_y: float,
    image_height: int,
    metadata: MapMetadata,
) -> tuple[float, float]:
    """ROS 지도 좌표를 이미지의 좌상단 픽셀 좌표로 변환한다."""

    delta_x = world_x - metadata.origin_x
    delta_y = world_y - metadata.origin_y
    cosine = math.cos(metadata.origin_yaw)
    sine = math.sin(metadata.origin_yaw)
    local_x = cosine * delta_x + sine * delta_y
    local_y = -sine * delta_x + cosine * delta_y
    return (
        local_x / metadata.resolution,
        image_height - local_y / metadata.resolution,
    )


def load_waypoint_document(path: str | Path) -> tuple[list[Waypoint], dict[str, Any]]:
    """웨이포인트와 순찰 옵션을 YAML 문서에서 읽는다."""

    waypoint_path = Path(path)
    try:
        raw = yaml.safe_load(waypoint_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise WaypointEditorError(f"웨이포인트 YAML을 읽을 수 없습니다: {error}") from error
    if not isinstance(raw, dict):
        raise WaypointEditorError("웨이포인트 YAML 최상위 값은 객체여야 합니다.")

    raw_waypoints = raw.pop("waypoints", [])
    if not isinstance(raw_waypoints, list):
        raise WaypointEditorError("waypoints는 목록이어야 합니다.")

    waypoints: list[Waypoint] = []
    for index, item in enumerate(raw_waypoints):
        if not isinstance(item, dict):
            raise WaypointEditorError(f"waypoints[{index}]가 객체가 아닙니다.")
        try:
            waypoint = Waypoint(
                name=str(item["name"]).strip(),
                x=float(item["x"]),
                y=float(item["y"]),
                yaw=float(item["yaw"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WaypointEditorError(f"waypoints[{index}] 형식이 올바르지 않습니다.") from error
        if not waypoint.name or not all(
            math.isfinite(value) for value in (waypoint.x, waypoint.y, waypoint.yaw)
        ):
            raise WaypointEditorError(f"waypoints[{index}] 값이 올바르지 않습니다.")
        waypoints.append(waypoint)
    return waypoints, raw


def dump_waypoint_document(
    waypoints: list[Waypoint], patrol_options: dict[str, Any]
) -> str:
    """편집한 웨이포인트와 기존 순찰 옵션을 YAML 문자열로 만든다."""

    document: dict[str, Any] = {
        "waypoints": [
            {
                "name": waypoint.name,
                "x": round(waypoint.x, 3),
                "y": round(waypoint.y, 3),
                "yaw": round(waypoint.yaw, 3),
            }
            for waypoint in waypoints
        ]
    }
    document.update(patrol_options)
    return yaml.safe_dump(document, allow_unicode=True, sort_keys=False)
