"""브릿지 노드의 모든 파라미터가 launch 인자로 노출되는지 검사한다.

노드가 ``declare_parameter`` 로 받는 값을 launch 가 노출하지 않으면, launch
경로로 실행하는 사람은 그 값을 바꿀 방법이 없다. 그런데도 노드에는 기본값이
있으므로 조용히 동작해서 문제가 드러나지 않는다.

실제로 ``waypoint_file`` 이 이렇게 빠져 있었다. 좌표를 담은 YAML 경로를 줄 수
없어 launch 경로에서는 설치본(share/core/config)만 읽혔고, 좌표를 고친 뒤
colcon build 를 빼먹으면 옛 좌표로 주행하면서도 원인이 로그에 드러나지 않았다.
같은 종류가 다시 생기지 않게 두 파일을 맞춰 본다.

launch 파일과 노드 소스를 정규식으로 읽는다. rclpy 를 실행하거나 launch 를
띄우지 않으므로 하드웨어도 ROS 2 실행 환경도 필요 없다.
"""

from pathlib import Path
import re

BRIDGE_ROOT = Path(__file__).resolve().parents[1]
NODE_SOURCE = BRIDGE_ROOT / "bridge" / "mqtt_bridge_node.py"
LAUNCH_SOURCE = BRIDGE_ROOT / "launch" / "mqtt_bridge.launch.py"

# 여러 줄로 쓰인 선언도 잡으려면 여는 괄호와 이름 사이의 공백/개행을 허용해야
# 한다. 실제로 이 부분을 한 줄짜리 정규식으로 세면 선언 절반을 놓친다.
_DECLARE_PARAMETER = re.compile(r'declare_parameter\(\s*"([a-z_0-9]+)"')
_DECLARE_LAUNCH_ARGUMENT = re.compile(
    r'DeclareLaunchArgument\(\s*"([a-z_0-9]+)"'
)


def _node_parameters() -> set[str]:
    return set(
        _DECLARE_PARAMETER.findall(
            NODE_SOURCE.read_text(encoding="utf-8")
        )
    )


def _launch_arguments() -> set[str]:
    return set(
        _DECLARE_LAUNCH_ARGUMENT.findall(
            LAUNCH_SOURCE.read_text(encoding="utf-8")
        )
    )


def test_the_regex_actually_finds_declarations() -> None:
    """정규식이 아무것도 못 찾는데 통과하는 상황을 먼저 배제한다."""
    assert len(_node_parameters()) > 10
    assert len(_launch_arguments()) > 10


def test_every_node_parameter_is_exposed_as_a_launch_argument() -> None:
    """노드가 받는 파라미터는 전부 launch 인자로 바꿀 수 있어야 한다."""
    missing = sorted(_node_parameters() - _launch_arguments())

    assert missing == []


def test_waypoint_file_is_exposed() -> None:
    """좌표 파일 경로를 launch 로 줄 수 있어야 한다.

    전수 검사와 겹치지만, 이 인자가 없으면 좌표를 고쳐도 반영되지 않는다는
    구체적인 회귀를 이름으로 남겨 둔다.
    """
    assert "waypoint_file" in _launch_arguments()


def test_launch_passes_every_declared_argument_to_the_node() -> None:
    """선언만 하고 노드에 넘기지 않은 인자가 없어야 한다.

    DeclareLaunchArgument 만 있고 parameters 딕셔너리에 없으면, 사용자는 값을
    줄 수 있는데 노드는 그 값을 못 받는다. 선언보다 더 조용한 실패다.
    """
    launch_text = LAUNCH_SOURCE.read_text(encoding="utf-8")
    unused = [
        argument
        for argument in sorted(_launch_arguments())
        if f'"{argument}":' not in launch_text
    ]

    assert unused == []
