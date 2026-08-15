# Gazebo에서 SLAM 지도 생성하기

Gazebo 시뮬레이션에서 BOMI 차동구동 모델을 움직이며 LiDAR 스캔으로
지도를 생성하는 절차입니다. 실물 LiDAR로 지도를 만들 때는
[`handheld-lidar-mapping.md`](handheld-lidar-mapping.md)를 참고하세요.

통합 launch를 실행하면 다음 구성 요소가 함께 시작됩니다.

- Gazebo 테스트 월드와 BOMI 로봇 모델
- `/cmd_vel`, `/scan`, `/odom`, `/tf`, `/clock` 토픽 브리지
- SLAM Toolbox
- 지도와 LiDAR 스캔을 확인할 수 있는 RViz

시뮬레이션 모델은 차동구동 로봇을 기준으로 합니다. 실물 치수는 그 뒤 측정됐지만
(바퀴 1회전 거리 0.1929 m, 기하 트레드 0.257 m, 회전 변환용 유효 트레드 0.278 m —
[`hardware-control.md`](hardware-control.md) `## 7`), 이 모델의 치수를 거기에
맞춘 것은 아닙니다. 시뮬에서 잰 주행 특성을 실물 값으로 그대로 옮기지 마세요.

## 1. 시뮬레이션 의존성 설치

[`../README.md`](../README.md)의 개발 환경 설정과 `rosdep` 초기화를 완료한 뒤
실행합니다.

```bash
cd <저장소>/robot/ros2_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
sudo apt install -y ros-humble-nav2-map-server
```

Gazebo와 RViz는 GUI 프로그램입니다. WSL2에서는 WSLg가 활성화된 Windows
11 환경을 사용하거나 별도의 X 서버를 준비해야 합니다.

## 2. 워크스페이스 빌드

```bash
cd <저장소>/robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-up-to mapping core
source install/setup.bash
```

이 문서가 쓰는 것은 `mapping`(launch·설정)과 `core`(`keyboard_teleop`)뿐입니다.
`mapping` 은 `core` 를 의존하지 않으므로 **둘 다 명시해야** 합니다.

새 터미널을 열 때마다 ROS 2와 워크스페이스 환경을 다시 불러와야 합니다.

```bash
source /opt/ros/humble/setup.bash
source <저장소>/robot/ros2_ws/install/setup.bash
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
cd <저장소>/robot/ros2_ws
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

저장한 지도는 `bomi_navigation_sim.launch.py` 의 `map:=` 인자로 넘겨 주행에
씁니다. 같은 Gazebo 월드에서 만든 지도여야 합니다.

## 주요 토픽과 TF

| 이름 | 역할 |
| --- | --- |
| `/cmd_vel` | ROS 2에서 Gazebo 차동구동 플러그인으로 전달되는 속도 명령 |
| `/scan` | Gazebo LiDAR의 `sensor_msgs/LaserScan` 데이터. 시뮬에서는 드라이버가 직접 내므로 `scan_sanitizer` 를 거치지 않습니다 — 실기 문서의 `/scan_raw` → 위생 → `/scan` 과 이름은 같아도 뜻이 다릅니다 |
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
