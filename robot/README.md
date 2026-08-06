# BOMI Robot

Ubuntu 22.04, ROS 2 Humble, Python 3.10을 기준으로 하는 로봇 워크스페이스입니다.

`core`의 `pico_driver`가 Pico H와 실제로 시리얼 통신하는 드라이버입니다.
실기로 전진·후진·좌우회전·제자리회전까지 확인했습니다. MQTT 통신 테스트는
유효한 NAVIGATE를 2초 저속 전진으로 바꾸며, 실제 Nav2 목적지 주행과 분리됩니다.

## 패키지

| 패키지 | 역할 |
| --- | --- |
| `core` | 이동 명령, 상태 발행, Pico 시리얼 드라이버, Mock 모터 드라이버, waypoint 순찰, 사용자 추종, Nav2 설정과 launch |
| `description` | Gazebo용 BOMI 차동구동 로봇과 LiDAR 모델 |
| `simulation` | 테스트 월드, 로봇 배치, Gazebo·ROS 2 토픽 브리지 |
| `mapping` | SLAM Toolbox 설정, 통합 launch, RViz 설정과 지도 파일 |
| `bomi_lidar` | YDLIDAR X4-PRO 드라이버 launch와 정적 TF |
| `bomi_obstacle_detection` | LiDAR 전방 장애물 거리 측정 |
| `bridge` | 백엔드와 로봇 사이의 MQTT 브리지 |

`src/rf2o_laser_odometry`는 외부 저장소를 `rf2o.repos`로 가져오는 패키지이며
Git으로 추적하지 않습니다. 준비 방법은
[`docs/handheld-lidar-mapping.md`](docs/handheld-lidar-mapping.md)에 있습니다.

## 실행 진입점

| 명령 | 동작 |
| --- | --- |
| `ros2 run core status_publisher` | `/bomi/status`에 `bomi is ready`를 1초마다 발행 |
| `ros2 run core keyboard_teleop` | 키보드 입력을 `/cmd_vel`의 `geometry_msgs/Twist`로 발행 |
| `ros2 launch core pico_driver.launch.py` | `/cmd_vel`을 Pico H로 보내고 `/odom`·`/imu` 발행 |
| `ros2 run core mock_motor_driver` | `/cmd_vel`을 구독해 값을 로그로 출력 |
| `ros2 run core joy_cmd_filter` | 조이스틱 입력을 `/cmd_vel` 명령으로 변환 |
| `ros2 run core nav2_waypoint_patrol` | YAML 순찰 지점을 Nav2 목표로 순서대로 전송 |
| `ros2 run core vision_udp_bridge` | AI 비전의 UDP 추적 결과를 `/vision/follow_result`로 발행 |
| `ros2 run core person_follower` | 추적 결과와 `/scan_real`로 `/cmd_vel` 생성, 근접 시 정지 |
| `ros2 launch bridge backend_drive_test.launch.py` | 유효한 MQTT NAVIGATE마다 저속으로 2초 전진하는 통신 테스트 |

## 하드웨어

차량은 JGB37-520 엔코더 모터 4개, MDD10A와 Pico H를 사용하는 차동구동
구조입니다. 조립, 모터 구동 확인, Jetson↔Pico 프로토콜과 ROS 2
드라이버(`pico_driver`)까지 실기로 검증했습니다. Odometry의 유효 트레드
정밀 보정은 진행 중입니다.

구성, 진행 상태와 안전 기준은
[`docs/hardware-control.md`](docs/hardware-control.md)에 있습니다.

Pico H 펌웨어 원본은 [`pico/`](pico/)에 있습니다.

## 시작하기

아래 경로는 저장소가 `C:\S15P11E102`에 있는 경우를 기준으로 합니다.
저장소 위치가 다르면 `/mnt/c/S15P11E102` 부분을 실제 경로에 맞게 바꾸세요.

### 1. 개발 환경 준비

ROS 2 설치는 최초 한 번만 필요합니다. 절차는
[`docs/ros2-humble-setup.md`](docs/ros2-humble-setup.md)에 있습니다.

이미 설치되어 있으면 확인만 하고 넘어갑니다. 결과가 `humble`이면 됩니다.

```bash
printenv ROS_DISTRO
```

### 2. 빌드

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
```

`core`와 그 의존 패키지만 빌드하려면 `--packages-up-to core`를 붙입니다.

빌드가 실패하면 [`docs/nav2-troubleshooting.md`](docs/nav2-troubleshooting.md)를
확인하세요. 브랜치를 바꾼 뒤에는 `rm -rf build install log` 후 다시 빌드해야
할 수 있습니다.

### 3. 새 터미널마다 환경 적용

```bash
source /opt/ros/humble/setup.bash
source /mnt/c/S15P11E102/robot/ros2_ws/install/setup.bash
```

## 저장 지도 기반 Nav2 시뮬레이션

`bomi_navigation_sim.launch.py`는 BOMI Gazebo 모델, 저장된 BOMI 지도, AMCL,
Nav2와 RViz를 함께 실행합니다. SLAM으로 지도를 새로 만들지 않으며, 기본 지도는
`mapping/maps/bomi_test_map.yaml`입니다. 시작 위치는 Gazebo의 BOMI 생성 위치와
같은 `x=0.0`, `y=0.0`, `yaw=0.0`으로 AMCL에 전달합니다.

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 launch core bomi_navigation_sim.launch.py
```

30초쯤 뒤 RViz 창이 열립니다. 기본 실행은 WSL의 그래픽 부하를 줄이기 위해
Gazebo 서버를 화면 없이 실행하고 RViz만 표시합니다.

### 목표 지정

RViz 툴바에서 `2D Goal Pose`를 선택하고 지도의 빈 공간을 마우스로 누른 채
드래그한 다음 놓으면 주행이 시작됩니다. 드래그 방향이 도착 후 로봇이 바라볼
방향입니다.

> `2D Pose Estimate`는 목표 지정이 아니라 로봇의 현재 위치를 AMCL에 알려주는
> 도구입니다. 잘못 지정하면 위치 추정이 깨져 로봇이 엉뚱한 방향으로 주행합니다.

명령으로 목표를 보낼 수도 있습니다. `SUCCEEDED`가 나오면 도달한 것입니다.

```bash
ros2 action send_goal /navigate_to_pose nav2_msgs/action/NavigateToPose \
  '{pose: {header: {frame_id: map}, pose: {position: {x: 0.0, y: 1.0, z: 0.0}, orientation: {z: 0.7071068, w: 0.7071068}}}}'
```

기본 지도는 6 m × 6 m이므로 `x`, `y`는 −2.5 ~ 2.5 범위로 지정합니다.
이 launch는 단일 목표 이동 확인용이므로 `nav2_waypoint_patrol`을 자동으로
실행하지 않습니다.

### 실행 옵션

| 목적 | 인자 |
| --- | --- |
| Gazebo 월드 화면도 표시 | `headless:=False` |
| Gazebo 화면 없이 실행 (기본값) | `headless:=True` |
| RViz 없이 실행 | `use_rviz:=False` |
| 다른 지도 사용 | `map:=/absolute/path/to/map.yaml` |

이 launch는 BOMI 차동구동 시뮬레이션 검증용이며 실제 모터 드라이버나 실물
Odometry를 실행하지 않습니다.

주행이 중단되거나 화면이 정상적으로 표시되지 않으면
[`docs/nav2-troubleshooting.md`](docs/nav2-troubleshooting.md)를 확인하세요.

## 비전 기반 사용자 추종

`person_following.launch.py`는 카메라의 사람 추적 결과와 LiDAR 거리로 속도
명령을 만듭니다. 사람이 너무 가까우면 정지합니다.

```text
카메라 → AI 비전 → UDP → vision_udp_bridge → /vision/follow_result
→ person_follower (+ LiDAR /scan) → /cmd_vel_follow
```

출력 토픽 기본값이 `/cmd_vel_follow`이므로 이대로는 로봇이 움직이지 않습니다.
실제로 움직이려면 출력을 `/cmd_vel`로 지정합니다.

```bash
ros2 launch core person_following.launch.py output_topic:=/cmd_vel
```

이때 Nav2 자율주행을 함께 실행하면 두 기능이 모두 `/cmd_vel`에 발행해 명령이
충돌합니다. 하나만 실행합니다.

카메라와 LiDAR 준비, 토픽 설정과 실행 순서는
[`ros2_ws/src/core/README.md`](ros2_ws/src/core/README.md)에 있습니다.

## 지도 만들기

| 방법 | 문서 | 필요한 것 |
| --- | --- | --- |
| 실물 로봇을 조이스틱으로 주행하며 생성 | [`docs/robot-joystick-slam.md`](docs/robot-joystick-slam.md) | BOMI, Pico H, 조이스틱, YDLIDAR X4-PRO |
| Gazebo 시뮬레이션에서 생성 | [`docs/gazebo-slam-mapping.md`](docs/gazebo-slam-mapping.md) | 없음 |
| 실물 LiDAR를 손으로 이동하며 생성 | [`docs/handheld-lidar-mapping.md`](docs/handheld-lidar-mapping.md) | YDLIDAR X4-PRO |

두 방법 모두 SLAM Toolbox로 `/map`을 만들고 `map_saver_cli`로 저장합니다.

## 테스트

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon test --packages-select simulation core
colcon test-result --verbose
```

## 문서

| 문서 | 내용 |
| --- | --- |
| [`AGENTS.md`](AGENTS.md) | 작업 규칙과 검증 기준 |
| [`docs/hardware-control.md`](docs/hardware-control.md) | 하드웨어 구성, 안전 기준, 검증 순서 |
| [`docs/ros2-humble-setup.md`](docs/ros2-humble-setup.md) | ROS 2 Humble 설치와 개발 환경 설정 |
| [`docs/nav2-troubleshooting.md`](docs/nav2-troubleshooting.md) | 주행 실패, 렌더링, 빌드 문제 해결 |
| [`docs/gazebo-slam-mapping.md`](docs/gazebo-slam-mapping.md) | Gazebo에서 SLAM 지도 생성 |
| [`docs/handheld-lidar-mapping.md`](docs/handheld-lidar-mapping.md) | 실물 LiDAR로 2D 지도 생성 |
| [`docs/robot-joystick-slam.md`](docs/robot-joystick-slam.md) | 실물 조이스틱 구동 확인과 로봇 탑재 LiDAR 지도 생성 |
| [`docs/waypoint-patrol.md`](docs/waypoint-patrol.md) | SLAM 지도 기반 waypoint 순찰 |
| [`docs/turtlebot3-nav2-sim.md`](docs/turtlebot3-nav2-sim.md) | TurtleBot3 Nav2 통합 시뮬레이션 |
| [`docs/turtlesim-teleop.md`](docs/turtlesim-teleop.md) | turtlesim으로 키보드 제어 확인 |
| [`ros2_ws/src/core/README.md`](ros2_ws/src/core/README.md) | 비전 기반 사용자 추종 실행 방법 |
| [`ros2_ws/src/bridge/README.md`](ros2_ws/src/bridge/README.md) | 백엔드 MQTT 브리지 |
| [`ai_vision/README.md`](ai_vision/README.md) | AI 비전 모듈 |
