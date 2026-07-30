# BOMI Robot

Ubuntu 22.04, ROS 2 Humble, Python 3.10을 기준으로 하는 로봇 워크스페이스입니다.

현재 `robot/ros2_ws/src` 아래에는 이동 명령과 기본 상태 처리를 담당하는
`core`, Gazebo 실행을 담당하는 `simulation`, 로봇 모델을 제공하는
`description`, SLAM 지도 생성을 담당하는 `mapping` 패키지가 있습니다.
`core`는 Mock 단계이며 실제 모터나 조향 서보를 제어하지 않습니다.

| 패키지 | 역할 |
| --- | --- |
| `core` | 키보드 이동 명령, 상태 발행, Mock 모터 드라이버 |
| `description` | Gazebo용 BOMI 차동구동 로봇과 LiDAR 모델 |
| `simulation` | 테스트 월드, 로봇 배치, Gazebo·ROS 2 토픽 브리지 |
| `mapping` | SLAM Toolbox 설정, 통합 launch, RViz 설정과 지도 파일 |

| 실행 명령 | 현재 동작 |
| --- | --- |
| `ros2 run core status_publisher` | `/bomi/status`에 `bomi is ready`를 1초마다 발행 |
| `ros2 run core keyboard_teleop` | 키보드 입력을 `/cmd_vel`의 `geometry_msgs/Twist`로 발행 |
| `ros2 run core mock_motor_driver` | `/cmd_vel`을 구독해 값을 로그로 출력 |
| `ros2 run core nav2_waypoint_patrol` | YAML 순찰 지점을 Nav2 `NavigateToPose` 목표로 순서대로 전송 |

현재 차량은 GA25-370 모터 1개와 MG996R 조향 서보 1개를 사용하는 자동차형 구조입니다. 4개 엔코더 모터, MDD10A와 Pico H를 사용하는 차동구동 장비는 개조를 위한 목표 구성으로, 아직 장착 및 검증이 완료되지 않았습니다. 자세한 하드웨어 구성과 안전한 검증 순서는 [`docs/hardware-control.md`](docs/hardware-control.md)를 참고하세요.

## SLAM 지도 기반 waypoint 순찰

`nav2_waypoint_patrol`은 SLAM으로 생성한 지도 위의 고정 지점들을 Nav2 목표로 순서대로 보내는 노드입니다. 이 노드는 모터를 직접 제어하지 않고, Nav2의 `navigate_to_pose` 액션 서버에 목표 pose만 전달합니다. 전역 경로는 NavFn Planner의 A* 탐색으로 계산하며, 실제 `/cmd_vel` 생성과 장애물 회피는 Nav2가 담당합니다.

기본 waypoint 예시는 `ros2_ws/src/core/config/room_waypoints.yaml`에 있습니다.

```yaml
waypoints:
  - name: sofa
    x: 0.0
    y: 0.0
    yaw: 0.0
loop: true
max_goal_retries: 3
goal_retry_delay_sec: 5.0
```

Nav2 목표가 실패하거나 거부되면 같은 waypoint를 5초 간격으로
최대 3회 재시도하며, 모두 실패하면 안전을 위해 해당 지점에서
순찰을 정지합니다.

실행 전에는 팀원이 SLAM으로 만든 `map.yaml`, `map.pgm`을 Nav2에 로드하고, 로봇의 위치 추정과 `navigate_to_pose` 액션 서버가 준비되어 있어야 합니다.

```bash
ros2 run core nav2_waypoint_patrol
```

다른 waypoint 파일을 사용하려면 다음처럼 파라미터를 넘깁니다.

```bash
ros2 run core nav2_waypoint_patrol --ros-args \
  -p waypoint_file:=/path/to/room_waypoints.yaml
```

### TurtleBot3 Nav2 통합 시뮬레이션 실행

`nav2_patrol_sim.launch.py`는 Gazebo Classic의 TurtleBot3 Waffle,
저장 지도, AMCL, Nav2, RViz와 waypoint 순찰 노드를 한 번에
실행합니다. 기본 지도와 월드는 `nav2_bringup`이 제공하는
TurtleBot3 샘플이며 BOMI 전용 지도나 시뮬레이션은 아닙니다.

처음 실행할 때 의존성을 설치하고 `core`를 빌드합니다.

```bash
cd /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install --packages-select core
source install/setup.bash
```

#### WSL에서 안전하게 실행

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

그다음 두 번째 WSL 터미널을 열고 RViz만 별도로 실행합니다.
RViz에도 Gazebo와 같은 시뮬레이션 시간을 적용해야 지도와 TF가
표시됩니다. `LP_NUM_THREADS`와 `nice`는 소프트웨어 렌더링이
컴퓨터 전체를 느리게 만들지 않도록 부하를 제한합니다.

```bash
source /opt/ros/humble/setup.bash
source /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws/install/setup.bash

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
source /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws/install/setup.bash
```

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

### 시뮬레이션 없이 테스트

시뮬레이션 없이 waypoint 파일 검증, 순찰 순서, 목표 재시도와
yaw 변환을 확인할 수 있습니다.

```bash
cd /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install --packages-select core
colcon test --packages-select core
colcon test-result --verbose
```

## 처음 개발 환경 설정하기

이 절은 ROS 2가 설치되지 않은 새 개발 환경에서 최초 한 번만 진행합니다. 프로젝트는 다음 환경을 기준으로 합니다.

- Ubuntu 22.04 LTS
- ROS 2 Humble
- Python 3.10
- Windows 사용 시 WSL2 + Ubuntu 22.04

### 1. Ubuntu 22.04 확인

Ubuntu 터미널에서 다음 명령을 실행합니다.

```bash
lsb_release -rs
```

결과가 `22.04`여야 합니다. Windows에 Ubuntu 22.04 WSL이 없다면 관리자 권한 PowerShell에서 다음 명령으로 설치합니다.

```powershell
wsl --install -d Ubuntu-22.04
```

설치 후 재부팅하고 Ubuntu 22.04 터미널을 실행합니다. 아래 명령은 PowerShell이 아닌 Ubuntu 터미널에서 실행해야 합니다.

### 2. ROS 2 패키지 저장소 등록

기본 패키지와 UTF-8 환경을 준비합니다.

```bash
sudo apt update
sudo apt install -y locales software-properties-common curl
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export LANG=en_US.UTF-8
sudo add-apt-repository universe
```

ROS 2 저장소 인증 키와 패키지 저장소를 등록합니다.

```bash
sudo curl -sSL \
  https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
```

```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
```

### 3. ROS 2 Humble과 개발 도구 설치

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y ros-humble-desktop ros-dev-tools python3-colcon-common-extensions python3-rosdep
```

설치된 ROS 2 환경을 현재 터미널과 이후에 여는 터미널에 적용합니다.

```bash
source /opt/ros/humble/setup.bash
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
source ~/.bashrc
```

설치 결과를 확인합니다.

```bash
printenv ROS_DISTRO
ros2 --help
```

`printenv ROS_DISTRO`의 결과가 `humble`이면 설치가 완료된 것입니다.

### 4. 프로젝트 의존성 설치

`rosdep`을 처음 한 번만 초기화하고 데이터를 갱신합니다.

```bash
sudo rosdep init
rosdep update
```

`rosdep sources list file already exists` 메시지가 나오면 이미 초기화된 것이므로 `rosdep update`부터 진행합니다.

저장소 위치가 다르면 아래 경로를 실제 경로로 변경한 뒤 프로젝트 의존성을 설치합니다.

```bash
cd /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws
rosdep install --from-paths src --ignore-src -r -y
```

## Gazebo에서 SLAM 지도 생성하기

Gazebo 시뮬레이션에서 BOMI 차동구동 모델을 움직이며 LiDAR 스캔으로
지도를 생성할 수 있습니다. 통합 launch를 실행하면 다음 구성 요소가 함께
시작됩니다.

- Gazebo 테스트 월드와 BOMI 로봇 모델
- `/cmd_vel`, `/scan`, `/odom`, `/tf`, `/clock` 토픽 브리지
- SLAM Toolbox
- 지도와 LiDAR 스캔을 확인할 수 있는 RViz

현재 시뮬레이션 모델은 목표 구성인 차동구동 로봇을 기준으로 하며, 실제
자동차형 하드웨어의 동작을 재현하지는 않습니다.

### 1. 시뮬레이션 의존성 설치

앞의 개발 환경 설정과 `rosdep` 초기화를 완료한 뒤 실행합니다.

```bash
cd /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
sudo apt install -y ros-humble-nav2-map-server
```

Gazebo와 RViz는 GUI 프로그램입니다. WSL2에서는 WSLg가 활성화된 Windows
11 환경을 사용하거나 별도의 X 서버를 준비해야 합니다.

### 2. 워크스페이스 빌드

```bash
cd /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

새 터미널을 열 때마다 ROS 2와 워크스페이스 환경을 다시 불러와야 합니다.

```bash
source /opt/ros/humble/setup.bash
source /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws/install/setup.bash
```

### 3. Gazebo, SLAM Toolbox, RViz 통합 실행

첫 번째 터미널에서 다음 명령을 실행합니다.

```bash
ros2 launch mapping mapping_sim.launch.py
```

Gazebo에 테스트 월드와 로봇이 나타나고 RViz의 `Map`, `LaserScan`, `TF`
화면에서 지도 생성을 확인할 수 있습니다. 시뮬레이션 시작 후 SLAM Toolbox는
센서와 TF가 준비될 시간을 확보하기 위해 약 5초 뒤 실행됩니다.

### 4. 키보드로 로봇 이동

두 번째 터미널에서 환경을 불러온 뒤 실행합니다.

```bash
ros2 run core keyboard_teleop
```

`w`, `s`, `a`, `d`로 이동하고 `Space`로 정지합니다. 대각선 조작은
`q`, `e`, `z`, `c`를 사용하며 `x`를 누르면 키보드 제어가 종료됩니다.
벽과 장애물 주변을 천천히 주행하면서 RViz에서 지도가 확장되는지 확인합니다.

### 5. 지도 저장

지도가 충분히 생성되면 세 번째 터미널에서 워크스페이스 환경을 불러오고
다음 명령을 실행합니다.

```bash
cd /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws
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

### 주요 토픽과 TF

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

### 문제 해결

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

## 실제 LiDAR를 손으로 이동하며 2D 지도 생성하기

바퀴 엔코더가 없는 현재 단계에서는 RF2O Laser Odometry가 연속된
`/scan`의 변화를 이용해 `odom → base_link` 이동량을 추정합니다.
SLAM Toolbox는 이 TF와 LaserScan을 받아 `map → odom`을 발행합니다.

```text
map → odom → base_link → laser_frame
       RF2O       bomi_lidar의 기존 정적 TF
```

이 구성은 실물 센서용이며 Gazebo의 `/odom`과 TF를 함께 실행하면 안 됩니다.
RF2O는 Adlink-ROS 공식 저장소의 ROS 2 Humble용 `humble-devel` 브랜치에서
검증한 revision을 `rf2o.repos`로 가져옵니다. 외부 코드를 저장소에 복사하지
않고 `vcs import`로 같은 소스를 반복해서 준비하기 위한 방식입니다.

### 1. RF2O와 ROS 의존성 준비

```bash
cd /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash

sudo apt update
sudo apt install -y python3-vcstool python3-rosdep
vcs import src < rf2o.repos
rosdep install --from-paths src --ignore-src -r -y
```

`src/rf2o_laser_odometry`가 이미 있으면 먼저 현재 remote와 branch를 확인하고
중복으로 import하지 않습니다. 기존 `bomi_lidar` launch는
`ydlidar_ros2_driver` 패키지에 의존하므로 `rosdep`으로 설치되지 않는
환경에서는 해당 드라이버를 먼저 워크스페이스 또는 ROS underlay에
준비해야 합니다.

### 2. 빌드와 환경 적용

```bash
cd /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install \
  --packages-up-to mapping rf2o_laser_odometry
source install/setup.bash
```

새 터미널에서는 항상 다음 두 줄을 다시 실행합니다.

```bash
source /opt/ros/humble/setup.bash
source /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws/install/setup.bash
```

### 3. LiDAR 연결과 통합 실행

YDLIDAR를 연결하고 장치 경로와 권한을 확인합니다.

```bash
ls -l /dev/ttyUSB*
groups
```

기본 장치가 `/dev/ttyUSB0`이면 LiDAR, 기존 정적 TF, RF2O,
SLAM Toolbox와 RViz를 한 번에 실행합니다.

```bash
ros2 launch mapping mapping_real.launch.py \
  lidar_port:=/dev/ttyUSB0
```

WSL에서 RViz의 OpenGL 문제가 있으면 다음처럼 실행합니다.

```bash
LIBGL_ALWAYS_SOFTWARE=1 ros2 launch mapping mapping_real.launch.py \
  lidar_port:=/dev/ttyUSB0
```

LiDAR 드라이버를 별도 터미널에서 실행해야 한다면 두 터미널을 사용합니다.
첫 번째 터미널:

```bash
ros2 launch bomi_lidar x4_pro.launch.py \
  port:=/dev/ttyUSB0 \
  scan_topic:=/scan \
  base_frame:=base_link \
  laser_frame:=laser_frame
```

두 번째 터미널:

```bash
ros2 launch mapping mapping_real.launch.py include_lidar:=false
```

두 방식을 동시에 사용하면 LiDAR 드라이버와 정적 TF가 중복되므로 하나만
선택합니다. 기본 RF2O 처리 주기는 공식 Humble launch와 같은 20 Hz입니다.
실측이 필요할 때만 `rf2o_frequency:=<Hz>`로 변경합니다.

### 4. 토픽과 TF 검증

```bash
ros2 topic list
ros2 topic hz /scan
ros2 topic echo /odom_rf2o --once
ros2 run tf2_ros tf2_echo odom base_link
ros2 run tf2_ros tf2_echo base_link laser_frame
ros2 topic echo /map --once
ros2 run tf2_tools view_frames
```

`view_frames`는 실행한 디렉터리에 TF 그래프 파일을 생성합니다. RF2O가
`Waiting for laser_scans`를 반복하면 `/scan`의 발행 주기와 이름을 확인합니다.
TF 조회 오류가 나면 다음 명령으로 실제 LaserScan frame을 확인하고,
그 frame이 `base_link`에 연결되는지 확인합니다.

```bash
ros2 topic echo /scan --once
ros2 topic info /scan -v
ros2 topic info /odom_rf2o -v
```

RViz에서는 다음 항목을 확인합니다.

- Fixed Frame이 `map`인지
- LaserScan이 실제 벽 위치와 대체로 일치하는지
- LiDAR 이동 중 `odom → base_link`가 끊기지 않고 변하는지
- 이동 방향과 RViz에서 보이는 이동 방향이 일치하는지
- 벽이 지나치게 겹치거나 휘지 않는지
- 출발점으로 돌아왔을 때 loop closure로 지도가 보정되는지
- `/map`이 지속적으로 갱신되는지

### 5. 손으로 측정할 때 주의사항

- LiDAR를 가능한 한 수평으로 고정하고 실제 로봇 장착 높이와 비슷하게 유지합니다.
- 위아래 흔들림과 기울어짐을 최소화합니다.
- 천천히 직진하고 천천히 회전하며 급격한 방향 전환을 피합니다.
- 움직이는 사람이나 물체가 적은 환경에서 측정합니다.
- 출발 지점으로 다시 돌아와 loop closure를 확인합니다.
- 손이나 몸으로 LiDAR의 수평 측정 면을 가리지 않습니다.
- 최종 지도는 실제 로봇에 센서를 장착한 상태에서도 다시 검증합니다.

### 6. 지도 저장과 파일 확인

기존 `bomi_test_map`을 덮어쓰지 않도록 새 이름을 사용합니다.

```bash
cd /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws
ros2 run nav2_map_server map_saver_cli \
  -f src/mapping/maps/bomi_handheld_01

ls -l src/mapping/maps/bomi_handheld_01.pgm \
  src/mapping/maps/bomi_handheld_01.yaml
grep '^image:' src/mapping/maps/bomi_handheld_01.yaml
```

YAML의 `image:` 값이 `bomi_handheld_01.pgm`처럼 함께 생성된 PGM을
가리키는지 확인합니다. 지도 저장 후 각 launch 터미널에서 `Ctrl+C`를 눌러
종료합니다. LiDAR 드라이버를 별도로 실행했다면 RF2O/SLAM을 먼저 종료하고
드라이버를 종료합니다.

## turtlesim으로 키보드 제어 확인하기

아래 경로는 저장소가 `C:\ssafy\kh\S15P11E102`에 있는 경우를 기준으로 합니다. 저장소 위치가 다르면 `/mnt/c/ssafy/kh/S15P11E102` 부분을 실제 경로에 맞게 바꾸세요.

`turtlesim` 실행은 키 입력과 `/cmd_vel` 발행을 화면에서 확인하기 위한 개발용 테스트입니다. 실제 자동차형 차량의 조향 동작을 재현하거나 하드웨어를 제어하지는 않습니다.

### 1. WSL 실행

Windows 터미널이나 PowerShell에서 Ubuntu 22.04를 실행합니다.

```bash
wsl -d Ubuntu-22.04
```

`robot/` 아래 텍스트 파일의 줄바꿈은 `robot/.gitattributes`에서 LF로 통일하므로 별도의 Git 설정이 필요하지 않습니다.

### 2. 필요한 ROS 2 패키지 설치

처음 한 번만 실행합니다.

```bash
sudo apt update
sudo apt install ros-humble-desktop ros-humble-ros2run ros-humble-turtlesim python3-colcon-common-extensions python3-rosdep -y
```

### 3. `core` 패키지 빌드

최초 실행 또는 패키지 구성 변경 후 빌드합니다.

```bash
cd /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select core
```

### 4. 두 터미널의 환경 준비

Ubuntu 터미널을 두 개 열고, 각 터미널에서 다음 명령을 실행합니다.

```bash
source /opt/ros/humble/setup.bash
source /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws/install/setup.bash
```

### 5. 첫 번째 터미널에서 turtlesim 실행

```bash
ros2 run turtlesim turtlesim_node
```

### 6. 두 번째 터미널에서 키보드 제어 실행

```bash
ros2 run core keyboard_teleop --ros-args -r /cmd_vel:=/turtle1/cmd_vel
```

`keyboard_teleop`은 기본적으로 `/cmd_vel`에 명령을 발행하지만, turtlesim은 `/turtle1/cmd_vel`을 구독합니다. 따라서 위 명령의 토픽 remap이 필요합니다.

### 조작키

| 키 | 동작 |
| --- | --- |
| `w` | 전진 |
| `s` | 후진 |
| `a` | 왼쪽 회전 |
| `d` | 오른쪽 회전 |
| `q` / `e` | 전진하면서 왼쪽 / 오른쪽 회전 |
| `z` / `c` | 후진하면서 왼쪽 / 오른쪽 회전 |
| `Space` | 정지 |
| `x` | 키보드 제어 종료 |

종료할 때는 두 번째 터미널에서 `x`를 눌러 키보드 제어를 종료하고, 첫 번째 터미널에서 `Ctrl+C`를 눌러 turtlesim을 종료합니다.

## 다른 Mock 노드 실행

새 터미널에서 ROS 2와 워크스페이스 환경을 준비한 뒤 실행하세요.

```bash
source /opt/ros/humble/setup.bash
source /mnt/c/ssafy/kh/S15P11E102/robot/ros2_ws/install/setup.bash
```

상태 메시지를 발행하려면 다음 명령을 사용합니다.

```bash
ros2 run core status_publisher
```

키보드 명령을 로그로 확인하려면 터미널 두 개에서 `mock_motor_driver`와 `keyboard_teleop`을 각각 실행합니다.

```bash
ros2 run core mock_motor_driver
```

```bash
ros2 run core keyboard_teleop
```
