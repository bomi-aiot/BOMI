# MQTT 로봇 ↔ 백엔드 메시지 계약서

> **대체됨(SUPERSEDED):** 이 문서는 이전 백엔드 가정값을 보존한 문서입니다. 5개 시나리오 메시지의 최종 기준은 [`scenario-contract-v1.md`](./scenario-contract-v1.md)이며, 충돌 시 해당 문서를 따릅니다.
> 상태: **DRAFT (백엔드 가정값)** — 로봇/IoT 팀 검토·확정 대기
> 당시 코드 출처: `MqttTopics`, `MqttInboundMessageParser`, `HomecomingContract`, `ObservationContract`, `RobotCommand`
> 관련 문서: [`topic-convention.md`](./topic-convention.md)

이 문서는 백엔드가 **현재 구현 기준으로 가정한** MQTT 계약입니다. payload 필드 이름·타입 문자열은 아직 로봇/IoT 팀과 공식 합의되지 않았습니다. 각 항목을 검토해 O/X·수정안을 남겨 주세요. 차이가 확정되면 백엔드는 계약소 파일(`HomecomingContract`, `ObservationContract`) 한 곳만 고치면 됩니다.

---

## 1. 토픽 규칙

형식: `bomi/v1/{domain}/{deviceId}/{channel}`

| 용도 | 토픽 | 방향 |
| --- | --- | --- |
| 현관/환경 이벤트 | `bomi/v1/iot/{sensorId}/events` | IoT → Backend |
| 로봇 상태 | `bomi/v1/robot/{robotId}/status` | Robot → Backend |
| 로봇 결과 | `bomi/v1/robot/{robotId}/results` | Robot → Backend |
| 로봇 이벤트 | `bomi/v1/robot/{robotId}/events` | Robot → Backend |
| 로봇 명령 | `bomi/v1/robot/{robotId}/commands` | Backend → Robot |

- 백엔드 구독: `bomi/v1/iot/+/events`, `bomi/v1/robot/+/events`, `bomi/v1/robot/+/status`, `bomi/v1/robot/+/results`
- `{deviceId}`(= 토픽의 `sourceId`)는 `[A-Za-z0-9._-]` 1~64자만 허용.

## 2. 공통 봉투 (envelope)

모든 메시지는 UTF-8 JSON이며 아래 최상위 필드를 포함합니다.

| 필드 | 필수 | 규칙 |
| --- | --- | --- |
| `eventId` | ✅ | 문자열 ≤64자. **멱등 키**(중복 전송 시 동일 값 유지). |
| `type` | ✅ | 문자열 ≤64자. 아래 3·4절의 허용 값. |
| `occurredAt` | ✅ | ISO-8601 **오프셋 포함** (예: `2026-07-27T15:30:00+09:00`). |
| `sourceId` (IoT) / `robotId` (Robot) | ✅ | **토픽의 deviceId와 일치**해야 함. IoT 메시지는 `sourceId`, 로봇 메시지는 `robotId` 키 사용. |
| `payload` | ✅ | JSON **객체**(빈 객체 가능). |

전송 규약:
- **QoS 1** (at-least-once) — 백엔드 인바운드는 QoS 1만 허용.
- **retain = false** — retained 메시지는 계약 위반으로 폐기.
- 위반 메시지(형식 오류·타입 불일치·sourceId 불일치 등)는 **조용히 폐기 후 ack**(재전송 폭주 방지).

예시 봉투:

```json
{
  "eventId": "01J8Z...",
  "type": "NAVIGATION_RESULT",
  "occurredAt": "2026-07-27T15:30:00+09:00",
  "robotId": "robot-01",
  "payload": { }
}
```

## 3. Backend → Robot : 명령 (`.../commands`)

명령 메시지 구조(`RobotCommand`): `commandId`, `scenarioId`, `robotId`, `type`, `occurredAt`, `expiresAt`, `payload`.

| type | payload (가정) | 의미 |
| --- | --- | --- |
| `NAVIGATE` | `{ "target": "ENTRANCE" \| "DEFAULT" }` | 목표 위치로 이동 |
| `SPEAK` | `{ "text": "..." }` | 발화(인사 등) |
| `CANCEL` | `{ }` | 진행 동작 취소 |

- `scenarioId`는 이 명령이 속한 시나리오(UUID). **로봇은 결과 메시지에서 이 값을 그대로 되돌려줘야 함**(4절).
- `commandId`는 명령별 고유 id(≤64자).
- `expiresAt`은 명령 유효 만료 시각(ISO-8601). 기본 2분. 지난 명령은 무시 권장.

예시:

```json
{
  "commandId": "cmd-8f3a...",
  "scenarioId": "3b1e6d2c-....",
  "robotId": "robot-01",
  "type": "NAVIGATE",
  "occurredAt": "2026-07-27T15:30:00+09:00",
  "expiresAt": "2026-07-27T15:32:00+09:00",
  "payload": { "target": "ENTRANCE" }
}
```

## 4. Robot → Backend : 상태·결과·이벤트

허용 `type` (파서 기준, 그대로 사용해야 함):

| 채널 | type | payload (가정) | 비고 |
| --- | --- | --- | --- |
| `results` | `NAVIGATION_RESULT` | `{ "scenarioId": "<받은 값 그대로>" }` | **scenarioId echo 필수** |
| `results` | `SPEAK_RESULT` | `{ "scenarioId": "..." }` | echo 권장 |
| `results` | `CANCEL_RESULT` | `{ "scenarioId": "..." }` | echo 권장 |
| `status` | `NAVIGATION_STATUS` | (진행 텔레메트리, 자유) | 현재 로깅만 |
| `status` | `REST_STATE_CHANGED` | `{ "restState": "RESTING" \| "AWAKE" }` | 휴식 관찰·모드 |
| `events` | `ONBOARDING_ANSWER_CAPTURED` | (온보딩, 별도 계약) | 이번 범위 밖 |

`NAVIGATION_RESULT` 예시 — **scenarioId echo가 핵심**:

```json
{
  "eventId": "01J8Z...",
  "type": "NAVIGATION_RESULT",
  "occurredAt": "2026-07-27T15:30:20+09:00",
  "robotId": "robot-01",
  "payload": { "scenarioId": "3b1e6d2c-...." }
}
```

## 5. IoT → Backend : 센서 이벤트 (`.../events`)

| type | payload (가정) | 의미 |
| --- | --- | --- |
| `DOOR_OPENED` | `{ }` (sourceId = 문 센서 id) | 현관 열림 → 귀가 시나리오 시작 |
| `AMBIENT_ENVIRONMENT_OBSERVED` | `{ "temperatureC": 24.5, "humidityPercent": 50.0, "comfortAssessment": "COMFORTABLE", "observedAt": "..." }` | 온·습도 관찰 |
| `PRESENCE_DETECTED` | (예약) | 이번 범위 밖 |

`AMBIENT_ENVIRONMENT_OBSERVED` 예시:

```json
{
  "eventId": "01J8Z...",
  "type": "AMBIENT_ENVIRONMENT_OBSERVED",
  "occurredAt": "2026-07-27T15:31:00+09:00",
  "sourceId": "ambient-sensor-01",
  "payload": {
    "temperatureC": 24.5,
    "humidityPercent": 50.0,
    "comfortAssessment": "COMFORTABLE",
    "observedAt": "2026-07-27T15:31:00+09:00"
  }
}
```

## 6. 기기 ID 규약

- **로봇**: 안정적인 `deviceId`(예: `robot-01`)로 자기 식별. 토픽·`robotId` 필드에 동일 값 사용. 백엔드는 이 값으로 로봇 레코드를 조회하므로 **재부팅·재배포에도 불변**이어야 함.
- **센서**(문/환경): `sensorId`(예: `door-sensor-01`, `ambient-sensor-01`)를 **일관되게** 사용. "어느 집(시니어)인지"는 **백엔드 설정에서 매핑**하므로 로봇/IoT 팀은 id만 고정해 주면 됨.

## 7. 귀가 시나리오 메시지 흐름 (참고)

```
IoT  DOOR_OPENED ─────────────▶ BE  (시나리오 생성)
BE   NAVIGATE(ENTRANCE) ──────▶ Robot
Robot NAVIGATION_RESULT ──────▶ BE  (scenarioId echo)   → 도착
BE   SPEAK(인사) ─────────────▶ Robot
        ...대화(음성 도메인)...
BE   NAVIGATE(DEFAULT) ───────▶ Robot   (대화 종료 후)
Robot NAVIGATION_RESULT ──────▶ BE  (scenarioId echo)   → 완료
```

## 8. ✅ 로봇/IoT 팀 확인 요청 체크리스트

각 항목에 O/X와 (다르면) 실제 값을 적어 주세요.

- [ ] 토픽 형식 `bomi/v1/{domain}/{deviceId}/{channel}` 그대로 사용 가능?
- [ ] 공통 봉투 5개 필드(eventId/type/occurredAt/sourceId|robotId/payload) 제공 가능?
- [ ] `occurredAt`을 **오프셋 포함 ISO-8601**로 보낼 수 있는가?
- [ ] **QoS 1 / retain=false** 준수 가능?
- [ ] `type` 문자열이 3·4·5절 목록과 동일한가? (다르면 실제 문자열 기입)
- [ ] **결과 메시지에 `scenarioId`를 받은 값 그대로 echo** 가능한가? (위치도: `payload.scenarioId`)
- [ ] NAVIGATE payload 키 `target`(`ENTRANCE`/`DEFAULT`), SPEAK 키 `text` 동의?
- [ ] REST payload 키 `restState`(`RESTING`/`AWAKE`) 동의?
- [ ] AMBIENT payload 키(`temperatureC`/`humidityPercent`/`comfortAssessment`/`observedAt`) 동의?
- [ ] 로봇 `deviceId`·센서 `sensorId`를 불변·일관 값으로 고정 가능?
- [ ] `expiresAt` 지난 명령 무시 정책 동의?

## 9. 변경 관리

- 이 문서는 이전 가정값의 참고 기록입니다. 시나리오 메시지 변경은 [`scenario-contract-v1.md`](./scenario-contract-v1.md)를 먼저 갱신하고 버전/일자를 남깁니다.
- 백엔드 반영 지점: payload 키는 `HomecomingContract`/`ObservationContract`, 타입 문자열은 각 핸들러·`MqttInboundMessageParser`, 토픽은 `MqttTopics`.
