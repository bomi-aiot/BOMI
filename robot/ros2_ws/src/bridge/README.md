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
│   ├── contract.py         # 토픽 규칙·명령 파싱/검증·결과/상태 envelope (순수 Python)
│   ├── robot_driver.py     # 주행 실행 경계 RobotDriver + MockRobotDriver
│   ├── mqtt_bridge.py      # 브릿지 코어: 명령→driver→결과/상태 발행 (전송 무관)
│   ├── mqtt_client.py      # paho-mqtt 러너: 코어를 실제 브로커에 연결
│   └── mqtt_bridge_node.py # ROS 2 노드 얇은 래퍼 (러너 구동)
├── test/                   # 단위 테스트 + 실제 브로커 E2E
└── docs/decisions/         # 설계 결정 기록
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

## 실행 방법

### A. 순수 Python 러너 (ROS 2 불필요)

브릿지만 브로커에 붙여 돌립니다. 개발·테스트에 가장 빠릅니다.

```bash
pip install paho-mqtt
ROBOT_ID=robot-01 MQTT_BROKER_HOST=localhost MQTT_BROKER_PORT=1883 \
  python3 -m bridge.mqtt_client
```

### B. ROS 2 노드 (WSL Ubuntu 22.04 + ROS 2 Humble)

```bash
cd robot/ros2_ws
colcon build --packages-select bridge
source install/setup.bash
ros2 run bridge mqtt_bridge --ros-args \
  -p robot_id:=robot-01 -p broker_host:=localhost -p broker_port:=1883
```

## 브로커 띄우기 (로컬 테스트)

프로젝트 인프라의 mosquitto를 사용합니다.

```bash
docker run --rm -p 1883:1883 \
  -v "$PWD/infra/docker/mosquitto/config:/mosquitto/config" eclipse-mosquitto
```

## 테스트

```bash
cd robot/ros2_ws/src/bridge
pip install pytest paho-mqtt

# 단위 테스트만 (브로커 불필요)
python3 -m pytest test/test_contract.py test/test_mqtt_bridge.py test/test_status.py -v

# 실제 브로커 E2E 포함 (브로커가 localhost:1883에 떠 있어야 함)
python3 -m pytest test/ -v
# 브로커 호스트/포트 변경 시
TEST_BROKER_HOST=127.0.0.1 TEST_BROKER_PORT=1883 python3 -m pytest test/ -v
```

브로커가 없으면 E2E 테스트는 자동으로 건너뜁니다(skip).

## 주행 실물 전환

현재 주행은 `MockRobotDriver`(도착을 흉내만 냄)를 사용합니다. 로봇 하드웨어와
Nav2가 준비되면 실물 드라이버를 구현해 러너에 주입하는 한 곳만 바꾸면 됩니다.
방식(옵션 B: NavigateToPose 직접 호출)과 남은 조율 사항은
`docs/decisions/0001-nav2-driver-owns-action-client.md`를 참고하세요.

## 범위

- 담당: 백엔드 MQTT ↔ 로봇 동작 통역, 계약 검증, 결과/상태 발행.
- 범위 밖: Nav2 자율주행(S15P11E102-79), SLAM, 모터 드라이버, AI 비전. 이들은
  실물 드라이버 구현 시점에 연결합니다.
