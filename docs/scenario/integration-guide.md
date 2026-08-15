# 로봇·IoT 실기 통합 가이드

> 최종 메시지 기준은 [`scenario-contract-v1.md`](../mqtt/scenario-contract-v1.md)와
> [`bomi-mqtt.asyncapi.yaml`](../../backend/src/main/resources/static/openapi/bomi-mqtt.asyncapi.yaml)이다.
> 과거 draft, legacy envelope, 오래된 simulator 출력은 구현 기준으로 사용하지 않는다.

## 실물 연동 전 안전 수칙

- **실물 Robot Bridge와 `robot-sim`을 같은 `robotId`로 동시에 실행하지 않는다.** 둘 다 같은 명령을 구독하면 실물 로봇이 의도하지 않게 움직일 수 있다.
- 실물 Broker에서 `scripts/dev/publish_event.py`, 수동 MQTT publish 또는 Swagger `Try it out`으로 이동 시나리오를 시작하지 않는다.
- 실제 E-stop과 모터 정지는 Robot의 물리 안전 계층이 담당한다. Backend의 mode 또는 복구 API는 이를 대신하지 않는다.
- 실물 시험 전 사람과 장애물을 이동 범위에서 치우고, Robot 담당자가 물리 E-stop을 즉시 조작할 수 있는 상태인지 확인한다.

## Robot Bridge 계약

### Backend 명령 구독

토픽:

```text
bomi/v1/robot/{robotId}/commands
```

Backend 명령의 `commandId`, `scenarioId`, `robotId`는 최상위 필드다. Bridge는 다음 명령을 최종 v1 형식으로 처리한다.

| 명령 | payload | 의미 |
| --- | --- | --- |
| `NAVIGATE` | `{"target":"ENTRANCE|LIVING_ROOM|DEFAULT"}` | 지정 waypoint로 이동 |
| `FOLLOW_START` | `{}` | 사람 따라가기 시작 |
| `FOLLOW_STOP` | `{}` | 사람 따라가기 중지 |

QoS 1에서는 같은 명령이 다시 도착할 수 있으므로 Bridge는 `commandId` 기준으로 중복 실행을 막아야 한다. 만료된 `expiresAt`의 명령도 실행하지 않는다.

### Robot 결과 발행

토픽:

```text
bomi/v1/robot/{robotId}/results
```

`scenarioId`와 `commandId`는 원 명령의 값을 그대로 **최상위 필드에** 반환한다. `payload`에 넣거나 legacy `status` 필드로 대체하지 않는다.

정상 도착 예시:

```json
{
  "eventId": "evt-nav-result-001",
  "robotId": "bomi-AA001",
  "type": "NAVIGATION_RESULT",
  "occurredAt": "2026-08-05T10:30:10+09:00",
  "scenarioId": "fc768674-3266-47bb-8348-1a7d222c84bd",
  "commandId": "cmd-nav-001",
  "payload": {
    "outcome": "SUCCEEDED",
    "resultCode": "ARRIVED",
    "reasonCode": null
  }
}
```

산책 추종 시작·중지 결과도 같은 상관관계 규칙을 사용한다.

```json
{
  "eventId": "evt-follow-result-001",
  "robotId": "bomi-AA001",
  "type": "FOLLOW_RESULT",
  "occurredAt": "2026-08-05T10:31:00+09:00",
  "scenarioId": "9724acfb-2f59-475b-bb03-f4f533486065",
  "commandId": "cmd-follow-start-001",
  "payload": {
    "outcome": "SUCCEEDED",
    "resultCode": "STARTED",
    "reasonCode": null
  }
}
```

- `outcome`: `SUCCEEDED`, `FAILED`, `CANCELLED`, `TIMED_OUT`
- `NAVIGATION_RESULT.resultCode`: `ARRIVED`, `NOT_ARRIVED`
- `FOLLOW_RESULT.resultCode`: `STARTED`, `STOPPED`, `UNCHANGED`
- 성공이면 `reasonCode=null`, 성공이 아니면 v1의 안정 reason code를 사용한다.
- 토픽의 `{robotId}`와 본문의 `robotId`가 다르거나 상관관계 ID가 원 명령과 다르면 Backend가 결과를 적용하지 않는다.
- QoS 1, retain=false를 사용한다.

## IoT 이벤트 계약

IoT 생산자는 `bomi/v1/iot/{sourceId}/events`로 최종 v1 envelope를 발행한다. `eventId`는 새 사건마다 새로 만들고 같은 사건의 재전송에서만 재사용한다. `sourceId`는 토픽과 본문이 같아야 하며 `occurredAt`은 타임존 오프셋을 포함한 ISO 8601 값이어야 한다.

문 열림 예시:

```json
{
  "eventId": "evt-door-001",
  "sourceId": "door_sensor",
  "type": "DOOR_OPENED",
  "occurredAt": "2026-08-05T10:30:00+09:00",
  "payload": {"location":"ENTRANCE"}
}
```

온습도 예시:

```json
{
  "eventId": "evt-ambient-001",
  "sourceId": "ambient-sensor-01",
  "type": "AMBIENT_ENVIRONMENT_OBSERVED",
  "occurredAt": "2026-08-05T10:30:00+09:00",
  "payload": {
    "temperatureC": 32.0,
    "humidityPercent": 50.0,
    "comfortAssessment": "UNCOMFORTABLE",
    "observedAt": "2026-08-05T10:30:00+09:00"
  }
}
```

## 운영자 Robot mode 복구

Robot 담당자가 물리적으로 안전함을 확인했고 활성 시나리오가 없는데 mode만 `SAFE_STOP` 또는 `SCENARIO_ACTIVE`에 남았을 때에만 다음 API를 사용한다.

```http
POST /api/v1/operator/robots/{deviceId}/mode-recoveries
X-Operator-Shared-Secret: <운영 환경의 별도 secret>
Content-Type: application/json

{
  "physicalSafetyConfirmed": true,
  "reason": "현장 점검 후 이동 경로와 모터 상태 확인"
}
```

복구 조건:

- 등록되고 활성화됐으며 어르신이 배정된 Robot
- 활성 Scenario 0건
- 현재 mode가 `SAFE_STOP`, 또는 활성 Scenario가 없는데 남아 있는 비정상 `SCENARIO_ACTIVE`
- `physicalSafetyConfirmed=true`와 비어 있지 않은 `reason`
- 복구 목표는 `IDLE`만 허용하며 이미 `IDLE`이면 멱등 no-op

이 API는 MQTT 이동·취소 명령을 발행하지 않고 mode만 복구하며 감사 이력을 남긴다. 서버의 `OPERATOR_SHARED_SECRET` 또는 `OPERATOR_ID`가 비어 있으면 요청은 fail-closed로 거절된다. 활성 Scenario가 있거나 현장 안전 확인을 할 수 없다면 SQL이나 API로 강제 복구하지 말고 Robot 담당자와 먼저 원인을 해결한다.
