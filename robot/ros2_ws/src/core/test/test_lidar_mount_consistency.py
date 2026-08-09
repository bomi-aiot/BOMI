"""매핑과 주행이 같은 LiDAR 장착값을 쓰는지 검증한다.

왜 이 검사가 필요한가
    지도는 LiDAR 높이에서 잘라낸 방의 단면이다. 24cm에서 그린 지도는 소파
    하단과 의자 다리를 담고, 46.6cm에서 그린 지도는 좌석과 좌탁 상판을
    담는다 — 같은 방인데 실루엣이 다르다. 그래서 그릴 때와 다른 높이로
    주행하면 스캔이 지도와 맞지 않는다.

    그 실패는 에러로 나타나지 않는다. AMCL이 조용히 위치를 놓치고, 복귀가
    엉뚱한 곳으로 가거나 실패할 뿐이다. 원인을 거슬러 올라가기가 매우
    어려운 종류의 고장이라, 값이 어긋나는 순간 여기서 잡는다.

    x도 같은 이유로 함께 본다. LiDAR가 회전 중심에서 벗어나 있으면 제자리
    회전에서 스캔 원점이 원을 그리는데, 매핑과 주행이 서로 다른 x를 믿으면
    그 보정이 어긋난다(2026-08-07 오전 실기의 증상).

무엇을 보는가
    robot/scripts/bomi_map.sh          매핑이 실제로 넘기는 값(LASER_X/Y/Z)
    core/launch/bomi_navigation_real   주행 기본값(laser_x/y/z)

    joystick_slam_robot.launch.py 와 mapping/mapping_real.launch.py 의
    기본값 0.0 은 여기서 보지 않는다. 전자는 bomi_map.sh 가 항상 값을
    넘겨 주고, 후자는 손에 들고 도는 별도 워크플로(robot/docs/
    handheld-lidar-mapping.md)라 로봇 장착값과 무관하다.
"""

from pathlib import Path
import re

import pytest

_ROBOT_ROOT = Path(__file__).resolve().parents[4]
_MAP_SCRIPT = _ROBOT_ROOT / "scripts" / "bomi_map.sh"
_NAV_LAUNCH = (
    Path(__file__).resolve().parents[1]
    / "launch"
    / "bomi_navigation_real.launch.py"
)

_AXES = ("x", "y", "z")


def _mapping_value(axis: str) -> float:
    """bomi_map.sh 의 LASER_<AXIS>=${BOMI_LASER_<AXIS>:-<값>} 을 읽는다."""
    text = _MAP_SCRIPT.read_text(encoding="utf-8")
    pattern = (
        rf"^LASER_{axis.upper()}=\$\{{BOMI_LASER_{axis.upper()}:-([-0-9.]+)\}}"
    )
    match = re.search(pattern, text, re.MULTILINE)
    assert match is not None, (
        f"bomi_map.sh 에서 LASER_{axis.upper()} 기본값을 찾지 못했습니다. "
        "형식이 바뀌었다면 이 검사도 함께 고쳐야 합니다."
    )
    return float(match.group(1))


def _navigation_value(axis: str) -> float:
    """bomi_navigation_real.launch.py 의 laser_<axis> 기본값을 읽는다."""
    text = _NAV_LAUNCH.read_text(encoding="utf-8")
    pattern = (
        rf'"laser_{axis}",\s*\n\s*default_value="([-0-9.]+)"'
    )
    match = re.search(pattern, text)
    assert match is not None, (
        f"bomi_navigation_real.launch.py 에서 laser_{axis} 기본값을 찾지 "
        "못했습니다. 형식이 바뀌었다면 이 검사도 함께 고쳐야 합니다."
    )
    return float(match.group(1))


@pytest.mark.parametrize("axis", _AXES)
def test_mapping_and_navigation_agree_on_the_lidar_mount(axis: str) -> None:
    """매핑이 넘기는 값과 주행 기본값이 축마다 같아야 한다."""
    mapping = _mapping_value(axis)
    navigation = _navigation_value(axis)

    assert mapping == navigation, (
        f"LiDAR 장착 {axis} 가 어긋났습니다: "
        f"bomi_map.sh={mapping} vs bomi_navigation_real.launch.py={navigation}. "
        "지도는 LiDAR 높이의 단면이라, 그릴 때와 다른 값으로 주행하면 "
        "AMCL 이 조용히 위치를 놓칩니다. 한쪽을 고쳤다면 다른 쪽도 고치고 "
        "재매핑하세요."
    )


def test_mount_height_is_not_left_at_zero() -> None:
    """높이를 0으로 두면 '아직 안 쟀다'는 뜻이라 실기에 나가면 안 된다."""
    assert _mapping_value("z") > 0.0
