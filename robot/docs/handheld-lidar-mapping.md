# 실제 LiDAR를 손으로 이동하며 2D 지도 생성하기

실물 YDLIDAR를 손에 들고 이동하며 2D 지도를 만드는 절차입니다.
Gazebo 시뮬레이션으로 지도를 만들 때는
[`gazebo-slam-mapping.md`](gazebo-slam-mapping.md)를 참고하세요.

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

## 1. RF2O와 ROS 의존성 준비

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
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

## 2. 빌드와 환경 적용

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install \
  --packages-up-to mapping rf2o_laser_odometry
source install/setup.bash
```

새 터미널에서는 항상 다음 두 줄을 다시 실행합니다.

```bash
source /opt/ros/humble/setup.bash
source /mnt/c/S15P11E102/robot/ros2_ws/install/setup.bash
```

## 3. LiDAR 연결과 통합 실행

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

## 4. 토픽과 TF 검증

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

## 5. 손으로 측정할 때 주의사항

- LiDAR를 가능한 한 수평으로 고정하고 실제 로봇 장착 높이와 비슷하게 유지합니다.
- 위아래 흔들림과 기울어짐을 최소화합니다.
- 천천히 직진하고 천천히 회전하며 급격한 방향 전환을 피합니다.
- 움직이는 사람이나 물체가 적은 환경에서 측정합니다.
- 출발 지점으로 다시 돌아와 loop closure를 확인합니다.
- 손이나 몸으로 LiDAR의 수평 측정 면을 가리지 않습니다.
- 최종 지도는 실제 로봇에 센서를 장착한 상태에서도 다시 검증합니다.

## 6. 지도 저장과 파일 확인

기존 `bomi_test_map`을 덮어쓰지 않도록 새 이름을 사용합니다.

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
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
