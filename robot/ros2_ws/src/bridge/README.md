# bridge

백엔드 MQTT와 로봇 내부 동작을 잇는 통역 브릿지 패키지입니다. 백엔드가 발행하는
로봇 명령(NAVIGATE/SPEAK/CANCEL)을 받아 실행하고, 그 결과와 상태를 다시 MQTT로
백엔드에 발행합니다.

계약 근거: `docs/mqtt/topic-convention.md`, S15P11E102-146 (백엔드 `RobotCommand`/
`HomecomingContract`/`ObservationContract`).

## 구조

```text
bridge/
├── bridge/
│   ├── contract.py          # 토픽 규칙·명령 파싱/검증·결과/상태 envelope (순수 Python)
│   ├── robot_driver.py      # 주행 실행 경계 RobotDriver + MockRobotDriver + 드라이버 선택
│   ├── nav2_robot_driver.py # 실제 Nav2 주행 드라이버 (NavigateToPose 직접 호출)
│   ├── waypoint_lookup.py   # 목적지 이름 → room_waypoints.yaml 좌표 변환 (순수 Python)
│   ├── mqtt_bridge.py       # 브릿지 코어: 명령→driver→결과/상태 발행 (전송 무관)
│   ├── mqtt_client.py       # paho-mqtt 러너: 코어를 실제 브로커에 연결
│   └── mqtt_bridge_node.py  # ROS 2 노드 얇은 래퍼 (러너 구동)
├── test/                    # 단위 테스트 + 실제 브로커 E2E
└── docs/decisions/          # 설계 결정 기록
```

계층: `mqtt_bridge_node`(ROS 2) → `mqtt_client`(paho) → `mqtt_bridge`(코어) →
`robot_driver`(주행). 코어와 계약은 ROS 2·MQTT에 의존하지 않아 브로커/ROS 없이도
단위 테스트됩니다.

## 흐름

```text
commands 구독 → 계약 파싱 → RobotDriver 실행 → results 발행 (scenarioId echo-back)
```

로봇 → 백엔드 토픽: 결과는 `bomi/v1/robot/{id}/results`, 상태는
`bomi/v1/robot/{id}/status`. 인바운드/아웃바운드 모두 QoS 1, retain=false.

## 개발 환경 (WSL)

이 패키지는 **WSL Ubuntu 22.04 + ROS 2 Humble**에서 실행합니다. Windows에서 WSL
우분투 터미널을 열고 진행하세요. Windows의 `C:\...` 저장소는 WSL에서 `/mnt/c/...`
아래에 보입니다. 아래 예시는 저장소가 `C:\S15P11E102\robot`인 경우이며, 위치가
다르면 경로만 바꾸세요.

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
```

`ros2 run`/`ros2 launch`로 브릿지를 실행하려면 **최초 1회(그리고 코드가 바뀔
때마다)** 워크스페이스를 빌드해야 합니다.

```bash
colcon build --packages-select core bridge --symlink-install
```

그리고 ROS 2를 쓰는 터미널마다 아래 두 줄을 먼저 실행합니다(새 터미널마다 반복).
`install/setup.bash`는 위 빌드 이후에 생깁니다.

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
```

`bridge` 패키지가 보이는지 확인합니다.

```bash
ros2 pkg list | grep bridge
```

> `Package 'bridge' not found`가 나오면 → 빌드를 안 했거나 `source
> install/setup.bash`를 안 한 것입니다. 위 빌드 + source 두 줄을 실행하세요.
> (순수 paho 러너 `python3 -m bridge.mqtt_client`는 빌드 없이 실행됩니다. 빌드·
> 소싱은 `ros2 run`/`ros2 launch`로 주행 드라이버를 실행할 때만 필요합니다.)

MQTT 테스트 도구는 한 번만 설치합니다(비밀번호 입력이 필요하면 입력).

```bash
sudo apt install -y mosquitto mosquitto-clients   # 브로커 + mosquitto_pub/sub
pip3 install paho-mqtt
```

## 1. 단위 테스트 (병합 전 확인)

pull 받은 뒤, WSL 터미널에서 **아래 한 덩어리**로 빌드 + 전체 단위 테스트를
실행합니다. 모두 통과하면 병합해도 됩니다. Nav2·로봇·브로커 없어도 됩니다.

```bash
cd /mnt/c/S15P11E102/robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select core bridge --symlink-install
source install/setup.bash
colcon test --packages-select core bridge
colcon test-result --verbose
```

- Nav2 드라이버 테스트(`test_nav2_robot_driver.py`)는 액션 클라이언트를 Fake로
  대체하므로 실제 Nav2 서버 없이 위 명령으로 함께 검증됩니다.
- 실제 브로커가 필요한 E2E 테스트(`test_e2e_broker.py`)는 브로커가 없으면
  자동으로 건너뜁니다(skip).

## 2. 주행 드라이버 (Mock / Nav2)

주행 실행 드라이버는 ROS 2 노드의 `driver_type` 파라미터로 고릅니다.

| driver_type | 동작 |
| --- | --- |
| `mock` (기본값) | 실제 주행 없이 즉시 `ARRIVED` 반환. 통신·상태 검증용 |
| `nav2` | 목적지 이름을 좌표로 바꿔 Nav2 `NavigateToPose`로 실제 주행 |

- 기본값은 `mock`입니다. 잘못된 값이면 조용히 넘어가지 않고 노드 시작이 실패합니다.
- `nav2`는 ROS 2 노드 실행 경로에서만 쓰이며, Nav2가 먼저 활성화돼 있어야 합니다.
- 좌표는 `core/config/room_waypoints.yaml`을 단일 출처로 씁니다. `ENTRANCE`는
  `entrance`로 매핑하고, `DEFAULT`는 위치 미확정이라 미지원(`FAILED`)입니다.
- 도착 타임아웃은 `goal_timeout_seconds`(초, 기본 120)로 설정합니다.

설계 근거는 `docs/decisions/0001-nav2-driver-owns-action-client.md`를 참고하세요.

### 시뮬레이션에서 실제 이동 확인 (선택, WSL)

로봇이 실제로 현관으로 가는지 보고 싶을 때만 진행합니다. 이 테스트는 **WSL 안의
로컬 평문 브로커(1883)** 로 하며, 명령은 `mosquitto_pub`으로 직접 발행합니다. 순찰
노드 `nav2_waypoint_patrol`과 동시에 실행하지 않습니다.

WSL 터미널 4개를 씁니다. ROS 터미널(2·3번)은 **위 "개발 환경"의 빌드(최초 1회)와
`source` 두 줄**을 먼저 실행해야 `ros2 launch`가 동작합니다.

```bash
# 터미널 1) 로컬 브로커
mosquitto

# 터미널 2) Nav2 스택 (지도·AMCL·Nav2·RViz, WSLg 필요)
ros2 launch core bomi_navigation_sim.launch.py

# 터미널 3) 브릿지(nav2) — 로컬 브로커로
ros2 launch bridge mqtt_bridge.launch.py driver_type:=nav2 broker_host:=localhost

# 터미널 4) 결과 구독 + 명령 발행
mosquitto_sub -h localhost -t 'bomi/v1/robot/robot-01/results' -v

# 다른 탭에서
mosquitto_pub -h localhost -t 'bomi/v1/robot/robot-01/commands' -m '{
  "commandId":"cmd-1","scenarioId":"s-1","robotId":"robot-01","type":"NAVIGATE",
  "occurredAt":"2026-08-03T10:00:00+09:00","expiresAt":"2026-08-03T10:02:00+09:00",
  "payload":{"target":"ENTRANCE"}}'
```

RViz에서 로봇이 `entrance`로 이동하고, `.../results`에 `status`가 `ARRIVED`(성공)
또는 `FAILED`로 발행되면 정상입니다.

## 범위

- 담당: 백엔드 MQTT ↔ 로봇 동작 통역, 계약 검증, 결과/상태 발행.
- 범위 밖: SLAM, 모터 드라이버, AI 비전. Nav2 자율주행 스택 자체는 `core`가
  소유하며, 이 패키지는 그 액션 서버에 목표만 보냅니다.
