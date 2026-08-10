# BOMI LCD 표정 프로토타입

PySide6 전체 화면 UI가 ROS 2 상태를 구독해 대기, 주행, 듣기, 발화, 오류 표정을 표시합니다.

## 빠른 화면 테스트

Jetson의 Ubuntu 데스크톱 세션에서 실행합니다.

```bash
python3 -m pip install PySide6
cd ~/bomi/robot/ros2_ws/src/bomi_display
python3 -m bomi_display.face_display --demo
```

창 모드로 확인하려면 `--windowed`를 추가합니다. 종료는 `Esc` 대신 `Alt+F4`를 사용합니다.

## ROS 2 실행

```bash
cd ~/bomi/robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select bomi_display
source install/setup.bash
ros2 launch bomi_display display.launch.py
```

| 토픽 | 타입 | 입력 예시 |
| --- | --- | --- |
| `/bomi/nav_status` | `std_msgs/String` | `IDLE`, `NAVIGATING`, `SUCCEEDED`, `FAILED` |
| `/bomi/tts_status` | `std_msgs/String` | `IDLE`, `LISTENING`, `SPEAKING`, `FAILED` |
| `/bomi/mqtt_connected` | `std_msgs/Bool` | `true`, `false` |
| `/bomi/sensor_heartbeat` | `std_msgs/Empty` | 센서 데이터 수신 때마다 발행 |
| `/cmd_vel` | `geometry_msgs/Twist` | 실제 속도 명령이 있으면 `이동 중` |

`demo-start.sh`로 실행하면 AI Chat이 `/tmp/bomi_ai_status`에 기록하는
`LISTENING`, `THINKING`, `SPEAKING`, `IDLE` 상태도 자동으로 반영합니다.

테스트 발행 예시:

```bash
ros2 topic pub --once /bomi/nav_status std_msgs/msg/String "{data: NAVIGATING}"
ros2 topic pub --once /bomi/tts_status std_msgs/msg/String "{data: SPEAKING}"
ros2 topic pub --once /bomi/mqtt_connected std_msgs/msg/Bool "{data: false}"
ros2 topic pub --once /bomi/sensor_heartbeat std_msgs/msg/Empty "{}"
```

표시 우선순위는 `오류 > 발화 > 생각 > 듣기 > 주행 > 대기`입니다. 센서 만료 감시는 첫 생존 신호를 받은 뒤 시작하며 기본 만료 시간은 3초입니다. 다른 값은 실행 시 `--sensor-timeout 5.0`처럼 지정할 수 있습니다.
