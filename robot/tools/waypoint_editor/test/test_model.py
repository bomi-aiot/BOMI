"""웨이포인트 편집기의 지도 좌표와 YAML 변환을 검증한다."""

from pathlib import Path

import pytest

from waypoint_editor.model import (
    MapMetadata,
    Waypoint,
    dump_waypoint_document,
    pixel_to_world,
    world_to_pixel,
)


def _metadata(*, yaw: float = 0.0) -> MapMetadata:
    """좌표 변환 테스트용 지도 메타데이터를 만든다."""

    return MapMetadata(Path("map.yaml"), Path("map.pgm"), 0.05, -1.0, -2.0, yaw)


def test_top_left_pixel_uses_ros_bottom_left_origin() -> None:
    """이미지 Y축이 ROS 지도 Y축과 반대인지 확인한다."""

    x, y = pixel_to_world(0, 0, 100, _metadata())
    assert x == pytest.approx(-1.0)
    assert y == pytest.approx(3.0)


@pytest.mark.parametrize("yaw", [0.0, 0.3, -1.2])
def test_world_and_pixel_conversions_are_inverse(yaw: float) -> None:
    """회전된 지도에서도 좌표 변환 왕복 결과가 유지되는지 확인한다."""

    metadata = _metadata(yaw=yaw)
    world = pixel_to_world(23.4, 81.2, 140, metadata)
    pixel = world_to_pixel(*world, 140, metadata)
    assert pixel == pytest.approx((23.4, 81.2))


def test_dump_preserves_patrol_options() -> None:
    """편집 결과에 기존 순찰 반복과 지연 설정이 유지되는지 확인한다."""

    text = dump_waypoint_document(
        [Waypoint("sofa", 1.23456, -0.1, 3.14159)],
        {"loop": True, "waypoint_delay_sec": 5.0},
    )
    assert "name: sofa" in text
    assert "x: 1.235" in text
    assert "yaw: 3.142" in text
    assert "loop: true" in text
    assert "waypoint_delay_sec: 5.0" in text
