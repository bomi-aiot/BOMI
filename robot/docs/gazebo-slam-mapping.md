# Gazebo에서 SLAM 지도 생성하기

Gazebo 시뮬레이션에서 BOMI 차동구동 모델을 움직이며 LiDAR 스캔으로
지도를 생성하는 절차입니다. 실물 LiDAR로 지도를 만들 때는
[`handheld-lidar-mapping.md`](handheld-lidar-mapping.md)를 참고하세요.

통합 launch를 실행하면 다음 구성 요소가 함께 시작됩니다.

- Gazebo 테스트 월드와 BOMI 로봇 모델
- `/cmd_vel`, `/scan`, `/odom`, `/tf`, `/clock` 토픽 브리지
- SLAM Toolbox
- 지도와 LiDAR 스캔을 확인할 수 있는 RViz

시뮬레이션 모델은 차동구동 로봇을 기준으로 합니다. 실제 차량의 바퀴 지름과
좌우 바퀴 간 거리는 아직 측정하지 않았으므로, 이 모델의 치수가 실물과 일치하는
것은 아닙니다.

## 1. 시뮬레이션 의존성 설치

[`../README.md`](../README.md)의 개발 환경 설정과 `rosdep` 초기화를 완료한 뒤
실행합니다.

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
sudo apt install -y ros-humble-nav2-map-server
```

Gazebo와 RViz는 GUI 프로그램입니다. WSL2에서는 WSLg가 활성화된 Windows
11 환경을 사용하거나 별도의 X 서버를 준비해야 합니다.

## 2. 워크스페이스 빌드

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

새 터미널을 열 때마다 ROS 2와 워크스페이스 환경을 다시 불러와야 합니다.

```bash
source /opt/ros/humble/setup.bash
source /mnt/c/S15P11E102/robot/ros2_ws/install/setup.bash
```

## 3. Gazebo, SLAM Toolbox, RViz 통합 실행

첫 번째 터미널에서 다음 명령을 실행합니다.

```bash
ros2 launch mapping mapping_sim.launch.py
```

Gazebo에 테스트 월드와 로봇이 나타나고 RViz의 `Map`, `LaserScan`, `TF`
화면에서 지도 생성을 확인할 수 있습니다. 시뮬레이션 시작 후 SLAM Toolbox는
센서와 TF가 준비될 시간을 확보하기 위해 약 5초 뒤 실행됩니다.

## 4. 키보드로 로봇 이동

두 번째 터미널에서 환경을 불러온 뒤 실행합니다.

```bash
ros2 run core keyboard_teleop
```

`w`, `s`, `a`, `d`로 이동하고 `Space`로 정지합니다. 대각선 조작은
`q`, `e`, `z`, `c`를 사용하며 `x`를 누르면 키보드 제어가 종료됩니다.
벽과 장애물 주변을 천천히 주행하면서 RViz에서 지도가 확장되는지 확인합니다.

전체 조작키는 [`turtlesim-teleop.md`](turtlesim-teleop.md)의 조작키 표와 같습니다.

## 5. 지도 저장

지도가 충분히 생성되면 세 번째 터미널에서 워크스페이스 환경을 불러오고
다음 명령을 실행합니다.

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
ros2 run nav2_map_server map_saver_cli \
  -f src/mapping/maps/bomi_test_map
```

다음 두 파일이 생성됩니다.

```text
src/mapping/maps/bomi_test_map.pgm
src/mapping/maps/bomi_test_map.yaml
```

같은 이름의 지도가 이미 있으면 덮어쓰므로, 기존 지도를 보존하려면 다른
파일 이름을 사용하세요.

## 주요 토픽과 TF

| 이름 | 역할 |
| --- | --- |
| `/cmd_vel` | ROS 2에서 Gazebo 차동구동 플러그인으로 전달되는 속도 명령 |
| `/scan` | Gazebo LiDAR의 `sensor_msgs/LaserScan` 데이터 |
| `/odom` | 시뮬레이션 로봇의 오도메트리 |
| `/tf` | `odom`, `base_link`, `lidar_link` 사이의 좌표 변환 |
| `/clock` | Gazebo 시뮬레이션 시간 |
| `/map` | SLAM Toolbox가 생성하는 점유 격자 지도 |

토픽 수신 여부는 다음 명령으로 확인할 수 있습니다.

```bash
ros2 topic list
ros2 topic hz /scan
ros2 topic echo /odom --once
ros2 topic echo /map --once
```

## 문제 해결

- `Package 'mapping' not found`: `colcon build --symlink-install` 후
  `source install/setup.bash`를 다시 실행합니다.
- `slam_toolbox.yaml`을 찾지 못함: 최신 브랜치를 받고
  `src/mapping/config/slam_toolbox.yaml`이 존재하는지 확인한 뒤 다시
  빌드합니다.
- RViz에서 지도가 보이지 않음: `/scan`, `/odom`, `/tf`, `/clock`이
  발행되는지 확인하고 RViz의 Fixed Frame이 `map`인지 확인합니다.
- 로봇이 움직이지 않음: `ros2 topic echo /cmd_vel`로 키보드 명령이
  발행되는지 확인합니다.
- Gazebo 또는 RViz 창이 열리지 않음: WSLg나 X 서버 등 GUI 실행 환경을
  확인합니다.
## 조이스틱 수동주행 + SLAM 지도 생성 (시뮬레이션)

아래 경로는 각 PC의 실제 `robot/ros2_ws` 경로로 변경합니다.

### 1. 최초 1회 설치 및 빌드

Gazebo, RViz, SLAM, 조이스틱 관련 패키지를 설치합니다. 최초 설치와 첫 빌드는
다운로드가 많아 시간이 걸릴 수 있습니다.

```bash
sudo apt update
sudo apt install -y \
  ros-humble-desktop \
  ros-humble-gazebo-ros-pkgs \
  ros-humble-slam-toolbox \
  ros-humble-nav2-map-server \
  ros-humble-joy \
  ros-humble-joy-linux \
  ros-humble-teleop-twist-joy \
  ros-humble-twist-mux \
  ros-humble-twist-mux-msgs \
  joystick \
  python3-colcon-common-extensions \
  python3-rosdep
```

```bash
cd /path/to/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash

rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
```

조이스틱이 WSL에 연결되어 `/dev/input/js0`가 보여야 합니다.

```bash
ls -l /dev/input/js*
jstest /dev/input/js0
```

### 2. 실행

```bash
cd /path/to/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

unset QT_XCB_GL_INTEGRATION
unset QT_OPENGL
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
export LP_NUM_THREADS=2

ros2 launch core joystick_slam_mapping.launch.py
```

Gazebo와 RViz가 열린 뒤 약 10초 기다리고 조이스틱으로 천천히 이동합니다.
RViz에서 `/map`이 주행 영역에 따라 확장되면 정상입니다.

### 3. 지도 저장

통합 launch를 끄지 않고 새 Ubuntu 터미널에서 실행합니다.

```bash
cd /path/to/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

mkdir -p ~/bomi_maps

ros2 run nav2_map_server map_saver_cli \
  -f ~/bomi_maps/bomi_slam_map
```

저장 결과:

```text
~/bomi_maps/bomi_slam_map.pgm
~/bomi_maps/bomi_slam_map.yaml
```

### 4. 저장 지도에서 좌표 찍기

SLAM 통합 launch를 종료한 뒤 저장 지도를 다시 불러옵니다.

첫 번째 터미널:

```bash
source /opt/ros/humble/setup.bash

ros2 run nav2_map_server map_server --ros-args \
  -p yaml_filename:=$HOME/bomi_maps/bomi_slam_map.yaml
```

두 번째 터미널:

```bash
source /opt/ros/humble/setup.bash

ros2 lifecycle set /map_server configure
ros2 lifecycle set /map_server activate
```

세 번째 터미널:

```bash
source /opt/ros/humble/setup.bash

export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
export LP_NUM_THREADS=2

rviz2
```

RViz에서 `Fixed Frame`을 `map`으로 설정하고 `Map`을 추가한 뒤 Topic을
`/map`으로 지정합니다.

새 터미널에서 좌표 출력을 확인합니다.

```bash
source /opt/ros/humble/setup.bash
ros2 topic echo /goal_pose
```

RViz 상단의 `2D Goal Pose`를 선택하고 지도에서 원하는 위치를 누른 뒤,
로봇이 바라볼 방향으로 드래그합니다.

기록할 값:

```text
position.x
position.y
orientation.z
orientation.w
```

좌표는 현재 저장된 지도 기준이므로 지도를 새로 만들면 다시 지정합니다.
