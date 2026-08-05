# 로봇·IoT 파트 통합 가이드 — 내 코드를 검증된 파이프라인에 꽂기

> 배경: 시나리오 ①⑤의 백엔드 전 구간이 로컬에서 E2E 검증됨 ([`local-e2e-report.md`](./local-e2e-report.md)).
> 실센서 자리는 발사기, 실로봇 자리는 robot-sim이라는 대역이 맡고 있다.
> **이 문서는 그 대역 자리에 당신 코드를 꽂아 자기 파트를 검증하는 방법이다.**
> 갈아끼우기 = 코드 수정이 아니라 "그 대역 프로그램 대신 내 프로그램을 켜는 것".
> 브로커가 가운데 있으므로 브랜치·언어·OS가 달라도 된다.

공통 준비 (아무 PC 1대, be-develop 기준):

```bash
docker compose up -d                # 브로커(1883) + DB
docker compose exec -T postgres psql -U bomi -d bomi < scripts/dev/seed-kim-sunja.sql
# 백엔드 실행: MQTT_ENABLED=true 환경변수 필수
pip install paho-mqtt               # 발사기/robot-sim 용
```

---

## A. 로봇 담당용 — robot-sim 자리에 내 브릿지 꽂기

### 구성

```
[발사기(제공)] → [백엔드(제공)] → [★ 당신의 브릿지 + Nav2]
```

robot-sim을 켜지 말고, 당신의 우분투/ROS 환경에서 브릿지를 켠다.
브로커 주소만 위 공통 준비를 한 PC의 IP:1883 로 지정 (같은 공유기/네트워크면 됨).

### 당신이 받게 될 메시지 (구독: `bomi/v1/robot/bomi-AA001/commands`)

```json
{ "commandId": "...", "scenarioId": "<UUID>", "robotId": "bomi-AA001",
  "type": "NAVIGATE", "occurredAt": "...", "expiresAt": "...(+2분)",
  "payload": { "target": "ENTRANCE" } }
```

- `type`: `NAVIGATE`(target: `ENTRANCE`/`DEFAULT`/`LIVING_ROOM`) 또는 `SPEAK`(payload.text)
- target → 좌표 변환은 로봇 소유 (`named_waypoints.yaml`, 계약 v1.0 안건 3)

### 당신이 보내야 할 메시지 (발행: `bomi/v1/robot/bomi-AA001/results`)

도착(또는 실패) 시:

```json
{ "eventId": "<새 UUID>", "type": "NAVIGATION_RESULT", "occurredAt": "<지금, 오프셋 포함>",
  "robotId": "bomi-AA001",
  "payload": { "scenarioId": "<받은 값 그대로!>", "status": "ARRIVED" } }
```

- ★ **scenarioId를 받은 그대로 되돌려주는 것(echo)이 계약의 핵심.** 없으면 백엔드가 결과를 연결 못 한다.
- `status`: `ARRIVED` | `FAILED`. QoS 1, retain=false.
- 정확한 형식이 궁금하면 robot-sim 소스(`scripts/dev/publish_event.py`의 `run_robot_sim`)가 곧 정답지다.

### 테스트 절차와 성공 판정

1. 당신의 브릿지 켬 (robot-sim은 끔)
2. 백엔드 PC에서: `python scripts/dev/publish_event.py door`
3. ✅ 성공 = 로봇(또는 시뮬)이 ENTRANCE로 이동 → ARRIVED 발행 → 백엔드 로그에 대화 전이
4. 이어서 `conv-end --scenario <로그의 id>` → NAVIGATE(DEFAULT) 수신 → 복귀 → 백엔드 로그 completed
5. `ambient --temp 32` 로 LIVING_ROOM 이동도 확인 (시나리오 ①)

### 자주 걸리는 것

- 명령이 안 옴 → robotId가 `bomi-AA001`인지 (시드 기준), 브로커 IP/방화벽
- 결과 보냈는데 백엔드 무반응 → payload 안 `scenarioId` echo 누락 또는 `robotId`가 토픽과 불일치 (불일치 시 백엔드가 **조용히 폐기**함)
- 같은 명령이 두 번 옴 → QoS 1 정상 동작. commandId로 중복 무시 권장

---

## B. IoT 담당용 — 발사기 자리에 내 센서 코드 꽂기

### 구성

```
[★ 당신의 발행 코드] → [백엔드(제공)] → [robot-sim(제공)]
```

robot-sim은 켜둔다 (그래야 시나리오가 끝까지 돈다).

### 당신이 보내야 할 메시지

문 열림 (발행: `bomi/v1/iot/door_sensor/events`):

```json
{ "eventId": "<매 사건마다 새 UUID>", "type": "DOOR_OPENED",
  "occurredAt": "2026-08-05T10:30:00+09:00", "sourceId": "door_sensor",
  "payload": { "location": "ENTRANCE" } }
```

온습도 (발행: `bomi/v1/iot/ambient-sensor-01/events`):

```json
{ "eventId": "...", "type": "AMBIENT_ENVIRONMENT_OBSERVED",
  "occurredAt": "...", "sourceId": "ambient-sensor-01",
  "payload": { "temperatureC": 32.0, "humidityPercent": 50.0,
               "comfortAssessment": "UNCOMFORTABLE", "observedAt": "..." } }
```

지켜야 할 것 (하나라도 어기면 백엔드가 **에러 없이 조용히 폐기**하므로 주의):

- `sourceId` == 토픽의 센서ID. 센서ID를 바꾸면 **백엔드 설정 등록 필요 → 백엔드 담당에게 알려줄 것**
- `occurredAt`은 타임존 오프셋 포함 ISO-8601 (`+09:00`)
- `eventId`는 사건마다 새로, 재전송 시에만 동일 유지 / QoS 1 / retain=false
- 정답지: `python scripts/dev/publish_event.py door --dry-run` 출력과 내 코드 출력을 비교

### 테스트 절차와 성공 판정

1. robot-sim 켬
2. 당신의 코드로 문 열림 발행 (실제 센서를 손으로 열어도 됨)
3. ✅ 성공 = 백엔드 로그 `Homecoming started` + robot-sim 창에 `NAVIGATE {target: ENTRANCE}` 수신
4. 온습도는 32°C 이상으로 발행 → `Wellness check started` (30°C 미만이면 기록만 되고 로봇 안 움직임 — 정상)
5. 연속 발행 시 `suppressed (ACTIVE_SCENARIO_EXISTS/COOLDOWN_ACTIVE)` 로그 = 중복 방지가 일하는 것. 버그 아님

---

문의: 백엔드(시나리오 라우팅) 담당에게. 계약 원문: [`../mqtt/scenario-contract-draft.md`](../mqtt/scenario-contract-draft.md)
