# 시나리오 1~5 MQTT 계약 v1.0 (확정)

> 이의는 24시간 내. 이후 이 문서가 정본. 기존 문서와 충돌 시 이 문서 우선.

## 1. 시나리오별 이벤트/명령

| # | 시나리오 | 트리거 → Backend | 채널 | Backend → Robot |
|---|---|---|---|---|
| ① | 온습도 안부 | `AMBIENT_ENVIRONMENT_OBSERVED` (기존) | `bomi/v1/iot/{sensorId}/events` | `NAVIGATE {target: LIVING_ROOM}` + `SPEAK` |
| ② | 약 알림 | 없음 (백엔드 스케줄러) | — | `NAVIGATE {target: LIVING_ROOM}` + `SPEAK` |
| ③ | "보미야" 호출 | 신규 `WAKE_WORD_DETECTED` | `bomi/v1/robot/{robotId}/events` | `NAVIGATE {target: LIVING_ROOM}` |
| ④ | 산책 | 신규 `WALK_REQUESTED` | `bomi/v1/robot/{robotId}/events` | 신규 `FOLLOW_START` / `FOLLOW_STOP` |
| ⑤ | 현관 인사 | `DOOR_OPENED` (기존) | `bomi/v1/iot/{sensorId}/events` | `NAVIGATE {target: ENTRANCE}` + `SPEAK` |

- 시나리오 시작 판정은 항상 백엔드. 시작 후 실시간 제어(사람 추적 등)는 전부 로봇 내부.
- 온습도 임계값 판단은 백엔드 (30°C 또는 습도 80%, 설정값).
- 봉투 규칙(eventId, occurredAt, QoS 1, retain=false, scenarioId echo)은 기존 `backend-robot-contract.md` 그대로.

## 2. NAVIGATE payload 확정

키는 `target`, 값은 `ENTRANCE` | `DEFAULT` | `LIVING_ROOM`. (기존 문서의 `waypointId`, `DEFAULT_POSITION` 폐기)

- 이름→좌표 파일: `robot/ros2_ws/src/bridge/config/named_waypoints.yaml` 신설, **로봇 파트 소유**. 3개 좌표 실측 필요 (`DEFAULT`는 현재 어디에도 없음).
- 모르는 target 수신 시 로봇은 `NAVIGATION_RESULT {status: FAILED}` 회신 (무시 금지).

## 3. 신규 메시지

**`WAKE_WORD_DETECTED`** (Robot → BE, `events`) — 웨이크워드 엔진 도입 보류. **STT 결과에 "보미" 포함 시 발행**하는 임시 구현으로 확정.

```json
{ "eventId": "01K1...", "type": "WAKE_WORD_DETECTED",
  "occurredAt": "2026-08-05T14:00:00+09:00", "robotId": "bomi-AA001",
  "payload": { "confidence": 0.92 } }
```

**`WALK_REQUESTED`** (Robot → BE, `events`) — `source`: `VOICE` | `APP`

```json
{ "eventId": "01K1...", "type": "WALK_REQUESTED",
  "occurredAt": "...", "robotId": "bomi-AA001",
  "payload": { "source": "VOICE" } }
```

**`FOLLOW_START` / `FOLLOW_STOP`** (BE → Robot, `commands`) — payload 없음. 봉투는 기존 명령과 동일(commandId, scenarioId, expiresAt 포함). 로봇 자체 종료(사용자 "그만", 사람 놓침)도 허용.

**`FOLLOW_RESULT`** (Robot → BE, `results`) — `status`: `STARTED` | `STOPPED` | `FAILED`, `scenarioId` echo 필수. `reason`(선택): `USER_REQUEST` | `PERSON_LOST` | `COMMAND` | `TIMEOUT`

```json
{ "eventId": "01K1...", "type": "FOLLOW_RESULT",
  "occurredAt": "...", "robotId": "bomi-AA001",
  "payload": { "scenarioId": "3b1e...", "status": "STOPPED", "reason": "USER_REQUEST" } }
```

## 4. 브랜치 병합 (기한 D+2)

ai-develop의 `robot/ai_chat`, `robot/ai_vision` 구현본을 robot-develop으로 폴더 단위 1회 병합 (ai-develop의 빈 `ros2_ws`는 반입 금지). 이후 robot 폴더 정본은 robot-develop. 담당: 로봇+AI, 리뷰: 백엔드.

## 5. 우선순위와 파트별 착수 목록

우선순위: **P0 = ⑤ → ① → ② / P1 = ③ / P2 = ④** (④는 P0·P1 완료 전 착수 금지. 미완 시 시연 제외)

| 파트 | 즉시 착수 |
|---|---|
| 로봇 | `Nav2RobotDriver`(Mock 대체) + `named_waypoints.yaml` 좌표 실측 + 브릿지 비동기화 — **전 시나리오 공통 병목, 최우선** |
| AI | 4절 병합 → STT 포함 매칭으로 `WAKE_WORD_DETECTED` / `WALK_REQUESTED` 발행부 |
| IoT | `DOOR_OPENED`, `AMBIENT_ENVIRONMENT_OBSERVED` 발행 코드 (형식은 이 문서 + 기존 계약 준수) |
| 백엔드 | 신규 타입 수신 허용 + 시나리오 오케스트레이터 (P0 순) |
| FE | 산책 시작/종료 REST 필드 협의 (P2 시점) |
