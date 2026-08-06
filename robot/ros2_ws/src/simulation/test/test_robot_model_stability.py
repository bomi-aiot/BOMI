"""
BOMI 로봇 모델이 주행 중 수평을 유지하는 조건을 검증한다.

구동륜 회전축이 뒤집히거나 지지 다각형이 무게중심을 감싸지 못하면 로봇이
주행 중 기울어지고, 기울어진 LiDAR가 바닥을 가짜 장애물로 인식해 Nav2가
목표를 중단한다. 이 모듈은 그 조건을 모델 파일에서 직접 확인한다.
"""

import math
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_SRC = PACKAGE_ROOT.parent
MODEL_FILE = (
    WORKSPACE_SRC / "description" / "models" / "bomi_robot" / "model.sdf"
)
SIMULATION_LAUNCH = PACKAGE_ROOT / "launch" / "bomi_sim.launch.py"

WHEEL_JOINTS = ("left_wheel_joint", "right_wheel_joint")
CASTER_LINKS = ("front_caster", "rear_caster")
GROUND_CONTACT_TOLERANCE_M = 1e-6


def _parse_pose(text):
    """SDF pose 문자열을 (x, y, z, roll, pitch, yaw) 실수 튜플로 바꾼다."""
    values = [float(part) for part in text.split()]
    values += [0.0] * (6 - len(values))
    return tuple(values[:6])


def _link_pose(link):
    """링크의 모델 좌표계 기준 pose를 돌려준다. 생략되면 원점으로 본다."""
    pose = link.find("pose")
    return _parse_pose(pose.text) if pose is not None else (0.0,) * 6


def _model():
    return ElementTree.parse(MODEL_FILE).getroot().find("model")


def _links():
    return {link.get("name"): link for link in _model().findall("link")}


def _center_of_mass():
    """모델 좌표계에서 전체 질량과 무게중심 (x, z)를 계산한다."""
    total_mass = 0.0
    moment_x = 0.0
    moment_z = 0.0

    for link in _model().findall("link"):
        inertial = link.find("inertial")
        if inertial is None:
            continue

        mass = float(inertial.find("mass").text)
        link_x, _, link_z = _link_pose(link)[:3]

        offset = inertial.find("pose")
        offset_x, _, offset_z = (
            _parse_pose(offset.text)[:3] if offset is not None else (0.0, 0.0, 0.0)
        )

        total_mass += mass
        moment_x += mass * (link_x + offset_x)
        moment_z += mass * (link_z + offset_z)

    return total_mass, moment_x / total_mass, moment_z / total_mass


def _ground_contacts():
    """지면에 닿는 링크의 (이름, x, 접지 높이)를 모은다."""
    contacts = []

    for name, link in _links().items():
        link_x, _, link_z = _link_pose(link)[:3]
        collision = link.find("collision")
        if collision is None:
            continue

        geometry = collision.find("geometry")
        sphere = geometry.find("sphere")
        cylinder = geometry.find("cylinder")

        if sphere is not None:
            radius = float(sphere.find("radius").text)
        elif cylinder is not None and name.endswith("_wheel"):
            radius = float(cylinder.find("radius").text)
        else:
            continue

        contacts.append((name, link_x, link_z - radius))

    return contacts


def test_wheel_joint_axis_is_expressed_in_model_frame():
    """
    구동륜 회전축이 모델 좌표계의 +Y로 명시됐는지 확인한다.

    바퀴 링크는 X축으로 90도 돌아가 있어 표현 좌표계를 생략하면 축이
    모델 좌표계의 -Y가 되고, DiffDrive가 전진 명령에 후진한다.
    """
    joints = {joint.get("name"): joint for joint in _model().findall("joint")}

    for joint_name in WHEEL_JOINTS:
        axis = joints[joint_name].find("axis").find("xyz")

        assert axis.get("expressed_in") == "__model__"
        assert [float(part) for part in axis.text.split()] == [0.0, 1.0, 0.0]


def test_robot_has_front_and_rear_ground_support():
    """구동륜 축의 앞뒤 모두에 접지점이 있는지 확인한다."""
    contacts = _ground_contacts()
    contact_names = {name for name, _, _ in contacts}

    for caster_name in CASTER_LINKS:
        assert caster_name in contact_names

    contact_x = [x for _, x, _ in contacts]

    assert min(contact_x) < 0.0
    assert max(contact_x) > 0.0


def test_all_ground_contacts_share_the_same_height():
    """모든 접지점이 같은 높이여야 로봇이 정지 상태에서 기울지 않는다."""
    heights = [height for _, _, height in _ground_contacts()]

    assert max(heights) - min(heights) < GROUND_CONTACT_TOLERANCE_M


def test_center_of_mass_stays_inside_the_support_polygon():
    """
    무게중심이 지지 다각형 안쪽에 충분한 여유를 두는지 확인한다.

    Nav2의 감속 한계 2.5 m/s^2에서도 넘어지지 않으려면 전복 임계 가속도가
    그보다 커야 한다. 임계 가속도는 g * (여유 거리) / (무게중심 높이)다.
    """
    _, com_x, com_z = _center_of_mass()
    contact_x = [x for _, x, _ in _ground_contacts()]

    front_margin = max(contact_x) - com_x
    rear_margin = com_x - min(contact_x)

    assert front_margin > 0.0
    assert rear_margin > 0.0

    tipping_accel = 9.81 * min(front_margin, rear_margin) / com_z

    assert tipping_accel > 2.5


def test_casters_do_not_grip_the_ground():
    """고정 캐스터가 주행과 제자리 회전을 방해하지 않도록 마찰이 0인지 확인한다."""
    links = _links()

    for caster_name in CASTER_LINKS:
        friction = links[caster_name].find("collision").find("surface").find("friction")
        ode = friction.find("ode")

        assert math.isclose(float(ode.find("mu").text), 0.0)
        assert math.isclose(float(ode.find("mu2").text), 0.0)


def test_robot_spawns_just_above_the_ground():
    """스폰 높이가 낙하 충격 없이 접지할 만큼 낮은지 확인한다."""
    launch_source = SIMULATION_LAUNCH.read_text(encoding="utf-8")
    match = re.search(r'"-z",\s*"([-\d.]+)"', launch_source)

    assert match is not None
    assert 0.0 <= float(match.group(1)) <= 0.05
