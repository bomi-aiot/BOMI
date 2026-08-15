# TurtleBot3 Nav2 통합 시뮬레이션 실행

`nav2_patrol_sim.launch.py`는 Gazebo Classic의 TurtleBot3 Waffle,
저장 지도, AMCL, Nav2, RViz와 waypoint 순찰 노드를 한 번에
실행합니다. 기본 지도와 월드는 `nav2_bringup`이 제공하는
TurtleBot3 샘플이며 BOMI 전용 지도나 시뮬레이션은 아닙니다.

BOMI 모델로 자율주행을 확인할 때는 [`../README.md`](../README.md)의
`bomi_navigation_sim.launch.py`를 사용하세요.

처음 실행할 때 의존성을 설치하고 `core`를 빌드합니다.

```bash
cd <저장소>/robot/ros2_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install --packages-select core
source install/setup.bash
```

## WSL에서 안전하게 실행

첫 번째 WSL 터미널에서는 Gazebo와 RViz GUI를 모두 끄고,
Gazebo 서버에 소프트웨어 렌더링을 적용해 시뮬레이션을
실행합니다. 이 구성은 WSL의 D3D12 장치 초기화 실패를 피하면서
GUI 렌더링 부하는 만들지 않습니다.

```bash
ros2 launch core nav2_patrol_sim.launch.py \
  headless:=True \
  use_rviz:=False \
  force_software_rendering:=True
```

첫 번째 터미널에서 다음 로그가 순서대로 나올 때까지 기다립니다.

```text
Nav2 bt_navigator 활성화 대기 중
Nav2 bt_navigator 활성화 완료
목표 전송: sofa
```

마지막 줄의 `sofa` 는 waypoint 파일의 **첫 지점 이름**입니다. `waypoint_file:=`
로 다른 파일을 주면 그 파일의 첫 이름이 찍힙니다.

그다음 두 번째 WSL 터미널을 열고 RViz만 별도로 실행합니다.
RViz에도 Gazebo와 같은 시뮬레이션 시간을 적용해야 지도와 TF가
표시됩니다. `LP_NUM_THREADS`와 `nice`는 소프트웨어 렌더링이
컴퓨터 전체를 느리게 만들지 않도록 부하를 제한합니다.

```bash
source /opt/ros/humble/setup.bash
source <저장소>/robot/ros2_ws/install/setup.bash

LIBGL_ALWAYS_SOFTWARE=1 \
GALLIUM_DRIVER=llvmpipe \
LP_NUM_THREADS=2 \
QT_XCB_GL_INTEGRATION=none \
nice -n 10 \
rviz2 -d /opt/ros/humble/share/nav2_bringup/rviz/nav2_default_view.rviz \
  --ros-args -p use_sim_time:=True
```

RViz가 열리면 `Global Options`의 `Frame Rate`를 `10`으로
낮춥니다. 종료할 때는 RViz 터미널을 먼저 `Ctrl+C`로 종료하고,
그다음 시뮬레이션 터미널을 `Ctrl+C`로 종료합니다.

그래픽 가속이 안정적인 네이티브 Linux 환경에서는 RViz를
통합 실행할 수 있습니다.

```bash
ros2 launch core nav2_patrol_sim.launch.py \
  headless:=True \
  use_rviz:=True
```

Gazebo GUI와 RViz를 모두 표시하려면 `headless:=False`를
사용합니다. WSL에서는 그래픽 부하가 매우 커질 수 있으므로
권장하지 않습니다.

기본값은 시스템 그래픽 드라이버를 사용합니다. 검은 화면,
OpenGL 초기화 오류 또는 `D3D12: Removing Device`가 발생하는
환경에서만 `force_software_rendering:=True`를 사용합니다. 이
옵션을 Gazebo GUI나 RViz와 함께 사용하면 CPU 사용량이 크게
높아질 수 있으므로 WSL의 최초 검증에서는 위의 GUI 없는 명령만
사용합니다.

## 실행 순서와 환경 적용

Gazebo가 `/spawn_entity` 서비스를 준비한 뒤 TurtleBot3와 Nav2가
순서대로 실행됩니다. TurtleBot3 생성이 끝난 뒤에만 Nav2를
시작하여 `odom`과 TF 준비 전 lifecycle 전환을 방지합니다. 순찰
노드는 `/bt_navigator`가 `active` 상태인지 ROS 2 서비스로 직접
확인합니다. AMCL 초기 위치는 시뮬레이션 시간으로 5회 발행하며,
Nav2가 활성화된 뒤에만 첫 목표를 전송하므로 첫 목표 전송까지
시간이 걸릴 수 있습니다. 새 터미널에서 실행할 때마다 ROS 2와
워크스페이스 환경을 다시 적용해야 합니다.

```bash
source /opt/ros/humble/setup.bash
source <저장소>/robot/ros2_ws/install/setup.bash
```

## 사용자 지도와 월드 지정

사용자 지도, Gazebo 월드와 waypoint를 검증하려면 서로 같은
좌표계를 사용하는 파일의 절대 경로를 전달합니다.

```bash
ros2 launch core nav2_patrol_sim.launch.py \
  headless:=True \
  use_rviz:=False \
  force_software_rendering:=True \
  map:=/absolute/path/to/map.yaml \
  world:=/absolute/path/to/world.model \
  waypoint_file:=/absolute/path/to/room_waypoints.yaml
```

`map.yaml`과 Gazebo 월드가 일치하지 않으면 RViz의 장애물 위치와
Gazebo의 실제 장애물 위치가 달라져 정상적인 경로 검증이
불가능합니다.

## 파라미터 파일 공유 주의

이 launch는 `core/config/nav2_safe_params.yaml`을
`bomi_navigation_sim.launch.py`와 공유합니다. BOMI 기준으로 조정한
목표 반경과 코스트맵 설정이 이 순찰에도 함께 적용되므로, 한쪽을
변경할 때는 다른 쪽 동작도 확인해야 합니다.
