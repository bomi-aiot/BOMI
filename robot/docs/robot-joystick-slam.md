# 실물 로봇 조이스틱 구동과 지도 생성

이 문서는 Pico H, Xbox 계열 조이스틱, YDLIDAR X4-PRO를 연결한 실물 BOMI의
구동을 먼저 안전하게 확인하고, 같은 구성으로 SLAM 지도를 만드는 절차다.

## 1. 최초 환경 준비

Ubuntu 22.04와 ROS 2 Humble 설치 후 워크스페이스에서 의존성을 설치하고
빌드한다. ROS 설치 자체는 [`ros2-humble-setup.md`](ros2-humble-setup.md)를
따른다.

```bash
cd ~/bomi_aiot_workspace/robot/ros2_ws
source /opt/ros/humble/setup.bash
sudo rosdep init  # 이미 초기화했다면 생략
rosdep update
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install --packages-up-to mapping
source install/setup.bash
```

새 터미널마다 마지막 두 `source` 명령을 다시 실행한다. 아래 명령에서
`mapping`, `core`, `bomi_lidar`가 보여야 한다.

```bash
ros2 pkg prefix mapping
ros2 pkg prefix core
ros2 pkg prefix bomi_lidar
```

## 2. 장치 이름과 권한 확인

모터 전원을 끈 상태에서 Pico, LiDAR, 조이스틱을 연결한다.

```bash
ls -l /dev/ttyACM* /dev/ttyUSB* /dev/input/js*
groups
```

기본값은 Pico `/dev/ttyACM0`, LiDAR `/dev/ttyUSB0`, 조이스틱
`/dev/input/js0`이다. 번호가 다르면 실제 경로를 launch 인자로 전달한다.
권한 오류가 나면 사용자를 `dialout`과 `input` 그룹에 추가한 뒤 로그아웃하고
다시 로그인한다.

```bash
sudo usermod -aG dialout,input "$USER"
```

여러 USB 장치를 반복 연결할 때 번호가 바뀌면 `/dev/serial/by-id/`의 고정
경로를 우선 사용한다.

## 3. 조이스틱 입력만 확인

아직 모터 전원을 켜지 않는다.

```bash
ros2 launch core joystick_teleop.launch.py cmd_vel_topic:=/cmd_vel_test
```

다른 터미널에서 다음을 확인한다.

```bash
ros2 topic hz /joy
ros2 topic echo /joy
ros2 topic echo /cmd_vel_test
```

현재 기본 매핑은 왼쪽 스틱 세로축이 `linear.x`, 가로축이 `angular.z`다.
스틱을 놓았을 때 두 값이 0이어야 한다. 축이 다르면
`core/config/xbox360_sim.yaml`의 축 번호를 `ros2 topic echo /joy` 결과에 맞춰
수정한다. 현재 설정의 최대 명령은 실차 최대치보다 크지만 Pico 드라이버에서
0.8 rev/s로 제한된다. 지도 생성 때는 스틱을 조금만 움직여 저속으로 주행한다.

## 4. Pico와 바퀴 구동 확인

로봇을 받침대에 올려 네 바퀴가 바닥에서 떨어지고 주변에 사람과 케이블이 없는지
확인한다. 모터 전원을 켠 뒤 Pico만 실행한다.

```bash
ros2 launch core pico_driver.launch.py serial_port:=/dev/ttyACM0
```

다른 터미널에서 작은 명령을 한 번씩 보내 바퀴 방향을 확인한다. 각 명령은
`Ctrl+C`로 종료하면 timeout에 의해 정지해야 한다.

```bash
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.03}, angular: {z: 0.0}}'
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: -0.03}, angular: {z: 0.0}}'
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.0}, angular: {z: 0.2}}'
```

전진에서 네 바퀴가 모두 차체 전진 방향이고, 회전에서는 좌우가 반대 방향이어야
한다. 명령 발행을 끊은 뒤 0.5초 안에 정지하지 않으면 실험을 중단한다.

이상이 없을 때 통합 조이스틱 구동을 실행한다. 처음에는 계속 받침대 위에서
확인하고, 그 다음 넓고 평평한 바닥에서 최소 스틱 입력으로 확인한다.

```bash
ros2 launch core joystick_slam_robot.launch.py \
  use_rviz:=false \
  pico_port:=/dev/ttyACM0 \
  lidar_port:=/dev/ttyUSB0
```

## 5. 지도 전 센서와 odometry 확인

지도를 그리기 전에 아래 네 연결이 모두 연속적이어야 한다.

```text
map → odom → base_link → laser_frame
```

```bash
ros2 topic hz /scan
ros2 topic hz /odom
ros2 topic echo /imu --once
ros2 run tf2_ros tf2_echo odom base_link
ros2 run tf2_ros tf2_echo base_link laser_frame
```

직선 1 m를 천천히 왕복해 RViz와 `/odom`의 거리·방향을 비교한다. 이어서 바닥에
각도를 표시하고 90°와 360° 제자리 회전을 반복해 odometry yaw 오차와 명령 종료
뒤 추가 회전을 기록한다. 직선 거리나 회전각이 반복적으로 틀리면 SLAM 설정을
바꾸기 전에 `pico_driver.yaml`의 실측값과 유효 트레드를 보정한다.

LiDAR 중심의 `base_link` 기준 전방(x), 좌측(y), 높이(z)를 m로 재고, 센서의
roll, pitch, yaw를 rad로 측정한다. 현재 기본값 0은 임시값이다. 예를 들어 실제
측정값이 x=0.08 m, z=0.31 m라면 다음처럼 전달한다.

```bash
ros2 launch core joystick_slam_robot.launch.py \
  pico_port:=/dev/ttyACM0 lidar_port:=/dev/ttyUSB0 \
  laser_x:=0.08 laser_y:=0.0 laser_z:=0.31 \
  laser_roll:=0.0 laser_pitch:=0.0 laser_yaw:=0.0
```

예시 숫자는 BOMI의 확정값이 아니므로 측정 없이 그대로 사용하지 않는다.

## 6. 지도 생성 주행

RViz Fixed Frame을 `map`으로 두고 LaserScan과 Map을 함께 표시한다.

- 사람이 적고 문이 움직이지 않는 시간에 진행한다.
- LiDAR 높이의 유리, 거울, 커튼과 반사 물체를 먼저 확인한다.
- 긴 직선만 계속 달리지 말고 모서리와 형태가 뚜렷한 구간을 포함한다.
- 급가속·급정지·제자리 급회전을 피하고 일정한 저속으로 움직인다.
- 한 구역을 작은 고리 형태로 돌고 출발점으로 돌아와 loop closure를 만든다.
- 벽이 두 겹이 되는 순간 계속 확장하지 말고 그 직전 원인을 먼저 확인한다.

좋지 않은 지도의 증상별 우선 점검 순서는 다음과 같다.

| 증상 | 먼저 확인할 항목 |
| --- | --- |
| 회전할수록 벽이 부채꼴·이중으로 보임 | 유효 트레드, 추가 회전, `laser_yaw` |
| 직선 벽이 평행한 두 줄로 누적됨 | 바퀴 미끄러짐, odometry 거리, TF 시간 끊김 |
| 로봇을 돌리면 스캔이 벽에서 벗어남 | LiDAR x/y/yaw와 장착 강성 |
| 지도가 순간 이동하거나 찢어짐 | `/scan`·`/odom` 주기, TF 누락, USB 통신 |
| 특정 재질만 비거나 번짐 | 유리·거울·검은 물체와 LiDAR 반사 특성 |

## 7. 저장과 결과 보존

기존 지도를 덮어쓰지 않도록 매번 새 이름으로 저장한다.

```bash
cd ~/bomi_aiot_workspace/robot/ros2_ws
ros2 run nav2_map_server map_saver_cli \
  -f src/mapping/maps/bomi_real_01
```

PGM과 YAML이 함께 생기고 YAML의 `image:`가 생성한 PGM을 가리키는지 확인한다.

```bash
ls -lh src/mapping/maps/bomi_real_01.{pgm,yaml}
grep '^image:' src/mapping/maps/bomi_real_01.yaml
```

첫 결과에는 LiDAR 실측 TF, 1 m 직선 오차, 360° 회전 오차, `/scan`과 `/odom`
주기를 함께 기록한다. 이 측정값을 확보한 뒤에만 SLAM Toolbox의 해상도와 scan
matching/loop closure 파라미터를 한 항목씩 바꾸고 같은 경로로 비교한다.
