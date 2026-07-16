# MQTT 토픽 규칙

토픽은 `bomi/v1/{domain}/{deviceId}/{channel}` 형식을 사용합니다.

| 용도 | 토픽 예시 | 방향 |
| --- | --- | --- |
| 현관 이벤트 | `bomi/v1/iot/door-sensor-01/events` | IoT → Backend |
| 로봇 명령 | `bomi/v1/robot/robot-01/commands` | Backend → Robot |
| 로봇 상태 | `bomi/v1/robot/robot-01/status` | Robot → Backend |
| 로봇 결과 | `bomi/v1/robot/robot-01/results` | Robot → Backend |

메시지는 UTF-8 JSON이며 공통으로 `eventId`, `type`, `occurredAt`, `sourceId`, `payload`를 포함합니다. `occurredAt`은 타임존을 포함한 ISO 8601 문자열로 기록합니다. 토픽에는 개인정보나 비밀값을 넣지 않습니다.

```json
{
  "eventId": "01J...",
  "type": "OBSTACLE_AVOIDED",
  "occurredAt": "2026-07-16T15:30:00+09:00",
  "sourceId": "robot-01",
  "payload": { "status": "COMPLETED" }
}
```
