# MQTT 토픽 및 메시지 계약

## 1. 목적과 범위

이 문서는 BOMI 외부 장치와 Spring Boot 사이의 MQTT 통신 계약을 정의합니다.
이번 버전은 귀가 환영 시나리오의 센서 이벤트·Robot 이동·음성 재생, 초기 온보딩 답변 이벤트와 백그라운드 휴식 전이·온습도 관측 이벤트를 다룹니다.

Robot 내부의 MQTT Bridge가 MQTT 메시지와 ROS 2 명령·결과를 변환합니다. MQTT Broker가 ROS 2 노드나 토픽과 직접 연결되는 구조가 아닙니다.

시나리오 상태와 전체 흐름은 [`../scenario/homecoming-welcome.md`](../scenario/homecoming-welcome.md)를 참고합니다.

## 2. 기본 규칙

- 토픽 버전은 `v1`입니다.
- payload는 UTF-8 JSON 객체입니다.
- 필드 이름은 `lowerCamelCase`, enum 값은 `UPPER_SNAKE_CASE`를 사용합니다.
- 시각은 타임존을 포함한 ISO 8601 문자열을 사용합니다.
- 토픽에는 사용자 이름, 토큰, 비밀번호 같은 개인정보나 비밀값을 넣지 않습니다.
- MQTT에는 명령과 작은 상태·결과만 전송하고 영상·음성 바이너리는 전송하지 않습니다.
- 모든 토픽은 `retain=false`를 사용합니다. 과거 명령이 재연결한 Robot에서 실행되면 안 됩니다.
- 이번 시나리오 토픽은 전달 보장을 위해 QoS 1을 사용하고 수신자는 중복을 허용해야 합니다.
- `eventId`는 생산자와 관계없이 BOMI 시스템 전체에서 충돌하지 않는 불투명 문자열을 사용합니다.

## 3. 토픽 구조

기본 형식은 다음과 같습니다.

```text
bomi/v1/{domain}/{deviceId}/{channel}
```

| 용도 | 토픽 | 발행자 | 구독자 | QoS |
| --- | --- | --- | --- | ---: |
| IoT 이벤트 | `bomi/v1/iot/{deviceId}/events` | IoT 센서 | Backend | 1 |
| Robot 명령 | `bomi/v1/robot/{robotId}/commands` | Backend | Robot MQTT Bridge | 1 |
| Robot 업무 이벤트 | `bomi/v1/robot/{robotId}/events` | Robot MQTT Bridge | Backend | 1 |
| Robot 진행 상태 | `bomi/v1/robot/{robotId}/status` | Robot MQTT Bridge | Backend | 1 |
| Robot 최종 결과 | `bomi/v1/robot/{robotId}/results` | Robot MQTT Bridge | Backend | 1 |

Backend 구독 패턴은 다음과 같습니다.

```text
bomi/v1/iot/+/events
bomi/v1/robot/+/events
bomi/v1/robot/+/status
bomi/v1/robot/+/results
```

## 4. 식별자와 상관관계

| 필드 | 적용 메시지 | 설명 |
| --- | --- | --- |
| `eventId` | 이벤트·상태·결과 | BOMI 시스템 전체에서 유일한 논리 이벤트 식별자. 동일 온보딩 답변을 포함한 재전송은 같은 값 유지 |
| `scenarioId` | Robot 명령·상태·결과 | Backend가 생성한 E2E 시나리오 식별자 |
| `commandId` | Robot 명령·상태·결과 | 명령과 상태·결과를 연결하는 식별자 |
| `robotId` | Robot 메시지 | 토픽의 `{robotId}`와 반드시 동일해야 함 |
| `sequence` | Robot 진행 상태 | 동일한 `commandId` 안에서 단조 증가하는 상태 순서 |
| `occurredAt` | 모든 메시지 | 이벤트 발생 시각. 전송 시각이 아님 |

최초 IoT 이벤트에는 아직 `scenarioId`, `commandId`, `robotId`가 없을 수 있습니다. Backend가 시나리오와 명령을 생성한 이후의 메시지부터 해당 식별자를 사용합니다. 명령 없이 계속되는 백그라운드 `REST_STATE_CHANGED`와 `ONBOARDING_ANSWER_CAPTURED`는 `robotId`와 `eventId`는 필수지만 `scenarioId`, `commandId`, `sequence`는 사용하지 않습니다.

`scenarioId`는 PostgreSQL `scenario.id` UUID의 표준 문자열 표현입니다. `eventId`와 `commandId`는 오프라인 생산자와 외부 시스템이 만든 최대 64자의 불투명 식별자로, 팀이 확정한 UUIDv4/v7 또는 ULID 형식을 사용하고 재전송 시 원문을 유지합니다. `robotId`는 MQTT 토픽에 안전한 등록 코드이며 DB의 `robot.serial_number`와 매핑합니다. 서로 다른 종류의 ID를 같은 값으로 재사용하지 않습니다.

## 5. IoT 센서 이벤트

문 열림 자체와 사람의 이동 방향 판정은 서로 다른 사건으로 취급합니다. 단순 문 열림 이벤트는 `DOOR_OPENED`로 발행할 수 있지만 귀가 환영 시나리오를 직접 시작하지 않습니다. 귀가 환영 시나리오는 방향 판정이 완료된 `PRESENCE_DETECTED` 중 `direction=INBOUND`인 이벤트만 사용합니다.

### `DOOR_OPENED`

단일 도어 센서가 문 열림을 감지했을 때 발행합니다. 이 이벤트만으로 사람의 존재나 이동 방향을 추론하지 않습니다.

```json
{
  "eventId": "01K0M4Y6YQ6B9D2F7H3J5N8RSC",
  "type": "DOOR_OPENED",
  "occurredAt": "2026-07-21T10:29:59+09:00",
  "sourceId": "door-sensor-01",
  "payload": {
    "location": "ENTRANCE"
  }
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `eventId` | 예 | BOMI 시스템 전체에서 유일한 이벤트 멱등 키 |
| `type` | 예 | `DOOR_OPENED` 고정 |
| `occurredAt` | 예 | 실제 문 열림 감지 시각 |
| `sourceId` | 예 | 토픽의 `{deviceId}`와 동일한 도어 센서 ID |
| `payload.location` | 예 | 등록된 논리 위치. 이번 시나리오는 `ENTRANCE` |

Backend는 `DOOR_OPENED`를 감사 로그 또는 센서 상태 확인에 사용할 수 있지만 이 이벤트만으로 귀가 환영 시나리오를 시작하지 않습니다.

### `PRESENCE_DETECTED`

IoT Gateway가 등록된 센서 조합으로 현관의 사람과 이동 방향을 판정했을 때 발행합니다. 단일 도어 센서의 문 열림만으로 이 이벤트를 생성해서는 안 됩니다.

```json
{
  "eventId": "01K0M4Y7G1D8W3A9H2T6Q5R4NP",
  "type": "PRESENCE_DETECTED",
  "occurredAt": "2026-07-21T10:30:00+09:00",
  "sourceId": "entrance-sensor-hub-01",
  "payload": {
    "location": "ENTRANCE",
    "direction": "INBOUND",
    "detectionMethod": "SENSOR_SEQUENCE"
  }
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `eventId` | 예 | BOMI 시스템 전체에서 유일한 이벤트 멱등 키 |
| `type` | 예 | `PRESENCE_DETECTED` 고정 |
| `occurredAt` | 예 | 사람과 이동 방향 판정이 확정된 시각 |
| `sourceId` | 예 | 토픽의 `{deviceId}`와 동일한 IoT Gateway ID |
| `payload.location` | 예 | 등록된 논리 위치. 이번 시나리오는 `ENTRANCE` |
| `payload.direction` | 예 | `INBOUND`, `OUTBOUND`, `UNKNOWN` 중 하나 |
| `payload.detectionMethod` | 예 | `SENSOR_SEQUENCE`, `VISION`, `MANUAL_OVERRIDE` 중 하나 |

Backend는 `type=PRESENCE_DETECTED`이면서 `direction=INBOUND`인 이벤트만 귀가 환영 시나리오의 트리거로 사용합니다. `DOOR_OPENED`와 `direction=UNKNOWN` 이벤트는 귀가 시나리오를 시작하지 않습니다. 같은 `eventId`가 다시 전달되면 기존 처리 결과를 유지합니다.

### `AMBIENT_ENVIRONMENT_OBSERVED`

온습도 센서 또는 IoT Gateway가 최신 온습도 스냅샷을 발행합니다. 장치는 설정된 저주기, 의미 있는 변화 또는 임계값 초과 시에만 발행하고 초당 원시 스트림을 중앙으로 보내지 않습니다.

```json
{
  "eventId": "01K0AMBIENT7G1D8W3A9H2T6Q",
  "type": "AMBIENT_ENVIRONMENT_OBSERVED",
  "occurredAt": "2026-07-23T14:20:00+09:00",
  "sourceId": "living-room-ambient-01",
  "payload": {
    "temperatureC": 29.2,
    "humidityPercent": 72.0,
    "reason": "THRESHOLD_CROSSED",
    "policyVersion": "ambient-policy-v1"
  }
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `eventId` | 예 | 동일 관측 재전송의 멱등 키 |
| `type` | 예 | `AMBIENT_ENVIRONMENT_OBSERVED` 고정 |
| `occurredAt` | 예 | 센서가 값을 관측한 시각 |
| `sourceId` | 예 | 토픽의 `{deviceId}`와 동일한 센서 또는 Gateway ID |
| `payload.temperatureC` | 예 | 섭씨 온도. 장치 지원 범위와 DB CHECK 범위 안의 숫자 |
| `payload.humidityPercent` | 예 | 상대습도 `%RH`, 0~100 |
| `payload.reason` | 예 | `PERIODIC`, `SIGNIFICANT_CHANGE`, `THRESHOLD_CROSSED`, `MANUAL_SAMPLE` |
| `payload.policyVersion` | 예 | 발행 주기·변화량·임계값을 판정한 운영 정책 버전 |

Backend는 `occurredAt`이 현재 `robot.ambient_observed_at`보다 새로울 때만 최신 스냅샷을 갱신합니다. `THRESHOLD_CROSSED`이거나 사용자가 덥고 춥고 습하고 건조하다고 확인한 경우에만 `ENVIRONMENT_OBSERVATION`을 생성합니다. 같은 `eventId`는 새 돌봄 기록을 만들지 않습니다.

## 6. Backend → Robot 명령

명령의 공통 형태는 다음과 같습니다.

```json
{
  "commandId": "01K0M4Y8B7F5M2N1Q9R6S3T8VX",
  "scenarioId": "6fd94c8c-3903-4a01-a82d-819e0c8edb12",
  "robotId": "robot-01",
  "type": "NAVIGATE",
  "occurredAt": "2026-07-21T10:30:01+09:00",
  "expiresAt": "2026-07-21T10:31:01+09:00",
  "payload": {}
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `commandId` | 예 | 명령 멱등 키 |
| `scenarioId` | 예 | 귀가 환영 시나리오 ID |
| `robotId` | 예 | 대상 Robot ID. 토픽과 일치해야 함 |
| `type` | 예 | 명령 타입 |
| `occurredAt` | 예 | Backend가 명령을 생성한 시각 |
| `expiresAt` | 예 | Robot이 명령 실행을 시작할 수 있는 마지막 시각 |
| `payload` | 예 | 명령 타입별 데이터 |

Robot은 `expiresAt`이 지난 명령을 실행하지 않고 `COMMAND_EXPIRED` 실패 결과를 발행합니다. 이미 처리한 `commandId`를 다시 받으면 명령을 재실행하지 않고 기존 최종 결과를 다시 발행할 수 있습니다.

### `NAVIGATE`

```json
{
  "commandId": "01K0M4Y8B7F5M2N1Q9R6S3T8VX",
  "scenarioId": "6fd94c8c-3903-4a01-a82d-819e0c8edb12",
  "robotId": "robot-01",
  "type": "NAVIGATE",
  "occurredAt": "2026-07-21T10:30:01+09:00",
  "expiresAt": "2026-07-21T10:31:01+09:00",
  "payload": {
    "waypointId": "ENTRANCE"
  }
}
```

`waypointId`는 Backend와 Robot이 사전에 합의한 논리 위치 이름입니다. 귀가 시나리오는 현관 이동에 `ENTRANCE`, 안전 확인 후 기본 위치 복귀에 `DEFAULT_POSITION`을 사용하며 충전소를 복귀 대상으로 사용하지 않습니다. 좌표나 Nav2 세부 파라미터는 MQTT 계약에 노출하지 않고 Robot 설정에서 해석합니다.

### `SPEAK`

```json
{
  "commandId": "01K0M51BR2X6A8D4F9G7H3J5KC",
  "scenarioId": "6fd94c8c-3903-4a01-a82d-819e0c8edb12",
  "robotId": "robot-01",
  "type": "SPEAK",
  "occurredAt": "2026-07-21T10:30:20+09:00",
  "expiresAt": "2026-07-21T10:30:50+09:00",
  "payload": {
    "utteranceId": "utt-01K0M519WQ",
    "text": "길동님, 어서 오세요.",
    "audioUri": "http://voice-ai:8002/api/v1/audio/audio-01K0M51A9P",
    "contentType": "audio/wav"
  }
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `payload.utteranceId` | 예 | AI가 생성한 발화 식별자 |
| `payload.text` | 예 | 접근성·로그·Fallback에 사용할 문장 |
| `payload.audioUri` | 예 | Robot이 내부망에서 가져올 수 있는 HTTP(S) URI |
| `payload.contentType` | 예 | `audio/wav` 또는 `audio/mpeg` |

Backend는 대화·음성 AI 응답의 서버 기준 주소와 `downloadPath`를 조합해 `audioUri`를 만듭니다. `audioUri`는 내부 주소이며 장기 저장하지 않습니다. 음성 자체를 MQTT payload에 포함하지 않습니다. Robot은 별도 설정으로 주입된 내부 서비스 인증정보를 사용하며 인증정보를 MQTT payload에 넣지 않습니다. 다운로드 실패와 재생 실패는 결과의 `reasonCode`로 구분합니다.

### `CANCEL`

진행 중인 이동 또는 음성 재생을 중단하도록 요청합니다. 취소 명령은 별도의 `commandId`를 사용하고 취소 대상은 `targetCommandId`로 지정합니다.

```json
{
  "commandId": "01K0M53F6C8D2G9H4J1N5Q7RST",
  "scenarioId": "6fd94c8c-3903-4a01-a82d-819e0c8edb12",
  "robotId": "robot-01",
  "type": "CANCEL",
  "occurredAt": "2026-07-21T10:31:01+09:00",
  "expiresAt": "2026-07-21T10:31:06+09:00",
  "payload": {
    "targetCommandId": "01K0M4Y8B7F5M2N1Q9R6S3T8VX",
    "reason": "SCENARIO_TIMED_OUT"
  }
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `payload.targetCommandId` | 예 | 중단할 `NAVIGATE` 또는 `SPEAK` 명령 ID |
| `payload.reason` | 예 | `SCENARIO_TIMED_OUT`, `USER_CANCELLED`, `POLICY_CANCELLED`, `SAFETY_CONDITION_UNCERTAIN` 중 하나 |

Robot MQTT Bridge는 `targetCommandId`의 작업을 찾고 ROS 2/Nav2 또는 음성 재생 노드에 취소를 요청합니다. 취소 요청을 받았다는 이유만으로 대상 작업을 성공 처리하지 않습니다.

## 7. Robot 진행 상태

### `REST_STATE_CHANGED`

Robot의 로컬 Vision이 설정된 지속시간 이상 누움 또는 기상 상태를 확정했을 때만 발행합니다. 프레임별 자세 후보는 발행하지 않습니다.

휴식 진입 예시:

```json
{
  "eventId": "01K0REST8B7F5M2N1Q9R6S3T8V",
  "robotId": "robot-01",
  "type": "REST_STATE_CHANGED",
  "occurredAt": "2026-07-23T13:10:00+09:00",
  "payload": {
    "restState": "RESTING",
    "posture": "LYING",
    "detectionMethod": "VISION_POSTURE_DURATION",
    "detectionDurationSeconds": 600,
    "confidence": 0.94,
    "policyVersion": "rest-policy-v1",
    "robotMode": "REST_GUARD"
  }
}
```

기상 예시:

```json
{
  "eventId": "01K0RESTAWAKE5M2N1Q9R6S3T8V",
  "robotId": "robot-01",
  "type": "REST_STATE_CHANGED",
  "occurredAt": "2026-07-23T14:02:00+09:00",
  "payload": {
    "restState": "AWAKE",
    "detectionMethod": "VISION_POSTURE_DURATION",
    "confidence": 0.91,
    "policyVersion": "rest-policy-v1",
    "robotMode": "IDLE"
  }
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `eventId` | 예 | 휴식 시작 또는 종료 전이의 시스템 전체 멱등 키 |
| `robotId` | 예 | 토픽의 `{robotId}`와 동일 |
| `type` | 예 | `REST_STATE_CHANGED` 고정 |
| `occurredAt` | 예 | 후보가 아니라 최종 전이가 확정된 시각 |
| `payload.restState` | 예 | `RESTING`, `AWAKE` |
| `payload.posture` | RESTING일 때 | MVP는 `LYING` |
| `payload.detectionMethod` | 예 | `VISION_POSTURE_DURATION`, `USER_COMMAND`, `GUARDIAN_OVERRIDE` |
| `payload.detectionDurationSeconds` | Vision RESTING일 때 | 임계값을 충족한 실제 지속시간 |
| `payload.confidence` | Vision일 때 | 0~1 최종 판정 신뢰도 |
| `payload.policyVersion` | 예 | 지속시간·해제 조건을 적용한 정책 버전 |
| `payload.robotMode` | 예 | `RESTING`이면 `REST_GUARD`, `AWAKE`이면 `IDLE` 또는 진행할 허용 모드 |

Backend는 `RESTING`에서 `robot.current_mode=REST_GUARD`와 `REST_OBSERVATION/ACTIVE`를 멱등 반영하고, `AWAKE`에서 관찰을 `COMPLETED` 처리합니다. Robot은 `REST_GUARD` 중 일반 능동 대화·비긴급 알림·자율 시나리오를 중지하지만 호출 감지, 안전 감지, 긴급 대응과 호출 시 안전 확인 후 접근은 계속 허용합니다.

금지 payload: 이미지·영상·관절 좌표·bounding box·track ID·얼굴 특징·프레임별 자세 배열.

### `NAVIGATION_STATUS`

진행 상태는 화면 표시와 관찰 가능성을 위한 정보이며 최종 성공·실패 판정은 `results` 토픽으로 전달합니다.

```json
{
  "eventId": "01K0M4Z1CT7N9B5V3X2K8P6QRS",
  "commandId": "01K0M4Y8B7F5M2N1Q9R6S3T8VX",
  "scenarioId": "6fd94c8c-3903-4a01-a82d-819e0c8edb12",
  "robotId": "robot-01",
  "type": "NAVIGATION_STATUS",
  "sequence": 2,
  "occurredAt": "2026-07-21T10:30:10+09:00",
  "payload": {
    "status": "MOVING",
    "currentLocation": "HALLWAY"
  }
}
```

`payload.status`는 `ACCEPTED`, `MOVING` 중 하나입니다. Backend는 진행 상태만으로 시나리오를 `ARRIVED` 또는 실패 상태로 전환하지 않습니다.

`sequence`는 동일한 `commandId`에서 발생한 진행 상태의 순서를 나타내는 1 이상의 정수입니다. Robot은 첫 상태부터 1씩 증가시킵니다.

| `sequence` | `payload.status` |
| ---: | --- |
| 1 | `ACCEPTED` |
| 2 | `MOVING` |

Backend는 `(commandId, sequence)`를 기준으로 진행 상태를 적용합니다.

- 마지막으로 적용한 값보다 작은 `sequence`는 늦게 도착한 이전 상태이므로 무시합니다.
- 같은 `sequence`와 같은 `eventId`는 재전송으로 처리합니다.
- 같은 `sequence`에 서로 다른 `eventId` 또는 다른 상태가 들어오면 계약 위반으로 기록합니다.
- 최종 `NAVIGATION_RESULT`가 확정된 후 도착한 진행 상태는 저장만 하고 현재 상태를 변경하지 않습니다.
- `occurredAt`은 표시와 장애 분석에 사용하며 처리 순서 판정에는 사용하지 않습니다.

## 8. Robot 업무 이벤트

### `ONBOARDING_ANSWER_CAPTURED`

현재 배정된 로봇이 진행 중인 초기 온보딩에서 한 문항의 답변 또는 수정본을 캡처했을 때 `events` 토픽으로 발행합니다. 답변이 Backend에 도달했는지 불확실해 재전송할 때는 반드시 같은 `eventId`를 사용합니다.

```json
{
  "eventId": "01K0ONBOARD7F5M2N1Q9R6S3T8V",
  "robotId": "robot-01",
  "type": "ONBOARDING_ANSWER_CAPTURED",
  "occurredAt": "2026-07-23T10:15:20+09:00",
  "payload": {
    "sessionId": "6c047625-c1d2-4e61-9e70-1c865ec6ac7f",
    "questionCode": "Q04_DAILY_ROUTINE",
    "revision": 1,
    "sourceConversationId": "1a4fe41a-6464-4e7e-b292-9a507333a3fa",
    "sourceMessageId": "a6f8cb84-c91c-4a38-a7b6-386ce6aa027f",
    "transcriptExcerpt": "아침 일곱 시쯤 일어나요.",
    "sttConfidence": 0.93,
    "sttModelName": "bomi-stt",
    "sttModelVersion": "2026-07",
    "processingPolicyVersion": "onboarding-extract-v1"
  }
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `eventId` | 예 | `onboarding_answer.client_event_id`에 원문 저장하는 전역 멱등 키 |
| `robotId` | 예 | 토픽의 `{robotId}`와 동일하며 세션의 배정 로봇과 일치 |
| `type` | 예 | `ONBOARDING_ANSWER_CAPTURED` 고정 |
| `occurredAt` | 예 | 답변이 캡처된 시각; `answered_at`으로 변환 |
| `payload.sessionId` | 예 | `onboarding_session.id` UUID |
| `payload.questionCode` | 예 | 해당 `question_set_version`의 허용 문항 코드 |
| `payload.revision` | 예 | 1 이상의 문항별 수정 순번 |
| `payload.sourceConversationId` | 아니오 | 단기 원문 출처 conversation UUID |
| `payload.sourceMessageId` | 아니오 | conversation JSON의 논리 messageId |
| `payload.transcriptExcerpt` | 아니오 | 확인에 필요한 최소 발췌; 전체 대화 금지, 기본 7일 파기 |
| `payload.sttConfidence` | 아니오 | 0~1; 있으면 STT 모델명·버전 필수 |
| `payload.sttModelName` | confidence가 있으면 | STT 모델명 |
| `payload.sttModelVersion` | confidence가 있으면 | STT 모델 버전 |
| `payload.processingPolicyVersion` | 예 | 추출·확인 처리 정책 버전 |

Backend는 토픽/메시지 `robotId`가 현재 세션의 `robot_id`와 일치하고 세션이 `IN_PROGRESS`인지 먼저 검사합니다. `(sessionId, questionCode, revision)`이 기존 행과 다르면서 `eventId`만 같으면 계약 위반입니다. 같은 `eventId`의 정상 재전송은 기존 `onboarding_answer.id`와 처리 상태를 반환하며 추출이나 최종 도메인 반영을 다시 실행하지 않습니다.

`transcriptExcerpt`는 MQTT 최대 payload와 개인정보 최소화 정책을 모두 통과한 짧은 텍스트만 허용합니다. 전체 STT, 원본/인코딩 음성, 토큰, 전체 프롬프트·모델 응답, 건강정보의 불필요한 반복은 포함하지 않습니다. AI 구조화 결과가 큰 경우 Backend/AI REST 계약에서 처리하고 MQTT에는 캡처 상관관계만 둡니다.

## 9. Robot 최종 결과

### `NAVIGATION_RESULT`

성공 예시:

```json
{
  "eventId": "01K0M50D4S8V2X6Z1B3N7Q9RTP",
  "commandId": "01K0M4Y8B7F5M2N1Q9R6S3T8VX",
  "scenarioId": "6fd94c8c-3903-4a01-a82d-819e0c8edb12",
  "robotId": "robot-01",
  "type": "NAVIGATION_RESULT",
  "occurredAt": "2026-07-21T10:30:15+09:00",
  "payload": {
    "outcome": "ARRIVED",
    "location": "ENTRANCE"
  }
}
```

실패 예시:

```json
{
  "eventId": "01K0M50D4S8V2X6Z1B3N7Q9RTQ",
  "commandId": "01K0M4Y8B7F5M2N1Q9R6S3T8VX",
  "scenarioId": "6fd94c8c-3903-4a01-a82d-819e0c8edb12",
  "robotId": "robot-01",
  "type": "NAVIGATION_RESULT",
  "occurredAt": "2026-07-21T10:30:15+09:00",
  "payload": {
    "outcome": "FAILED",
    "reasonCode": "PATH_BLOCKED",
    "message": "목적지까지 안전한 경로를 찾지 못했습니다."
  }
}
```

### `SPEAK_RESULT`

```json
{
  "eventId": "01K0M528W4Q7B2N6P9R1S3T5VX",
  "commandId": "01K0M51BR2X6A8D4F9G7H3J5KC",
  "scenarioId": "6fd94c8c-3903-4a01-a82d-819e0c8edb12",
  "robotId": "robot-01",
  "type": "SPEAK_RESULT",
  "occurredAt": "2026-07-21T10:30:25+09:00",
  "payload": {
    "outcome": "COMPLETED"
  }
}
```

실패 시 `payload.outcome=FAILED`와 `reasonCode`, `message`를 포함합니다.

### `CANCEL_RESULT`

```json
{
  "eventId": "01K0M53J8P2R4S6T9V1X3Z5BCD",
  "commandId": "01K0M53F6C8D2G9H4J1N5Q7RST",
  "scenarioId": "6fd94c8c-3903-4a01-a82d-819e0c8edb12",
  "robotId": "robot-01",
  "type": "CANCEL_RESULT",
  "occurredAt": "2026-07-21T10:31:02+09:00",
  "payload": {
    "outcome": "CANCELLED",
    "targetCommandId": "01K0M4Y8B7F5M2N1Q9R6S3T8VX"
  }
}
```

`payload.outcome`은 다음 중 하나입니다.

| 값 | 의미 |
| --- | --- |
| `CANCELLED` | 실행 중인 대상 작업을 중단함 |
| `ALREADY_COMPLETED` | 대상 작업이 이미 종료되어 취소할 작업이 없음 |
| `FAILED` | 대상 작업 취소에 실패함. `reasonCode` 필수 |

Backend는 `CANCEL_RESULT`를 별도 명령 결과로 기록하고 시나리오의 원래 종료 원인인 `TIMED_OUT` 또는 `CANCELLED`를 덮어쓰지 않습니다.

초기 표준 오류 코드는 다음과 같습니다.

| 명령 | 오류 코드 | 의미 |
| --- | --- | --- |
| 공통 | `COMMAND_EXPIRED` | 명령 만료 시각이 지남 |
| 공통 | `INVALID_COMMAND` | 필수 필드나 지원 타입이 잘못됨 |
| `NAVIGATE` | `PATH_BLOCKED` | 안전한 경로를 찾지 못함 |
| `NAVIGATE` | `NAVIGATION_ABORTED` | ROS 2/Nav2가 주행을 중단함 |
| `SPEAK` | `AUDIO_DOWNLOAD_FAILED` | 음성 파일을 가져오지 못함 |
| `SPEAK` | `AUDIO_PLAYBACK_FAILED` | 스피커 재생에 실패함 |
| `CANCEL` | `TARGET_COMMAND_NOT_FOUND` | 취소 대상 명령을 찾지 못함 |
| `CANCEL` | `CANCEL_UNSUPPORTED` | 대상 ROS 2 작업이 취소를 지원하지 않음 |

## 10. 유효성 및 보안

- 토픽의 `{deviceId}` 또는 `{robotId}`와 payload의 식별자가 다르면 메시지를 거부합니다.
- 알 수 없는 `type`, `status`, `outcome`은 임의로 성공 처리하지 않습니다.
- `occurredAt`이 파싱되지 않거나 필수 필드가 없으면 오류 로그를 남기고 폐기합니다.
- Backend는 `eventId`에 시스템 전체 unique constraint를 적용하고 동일 이벤트의 부수 효과를 다시 실행하지 않습니다.
- `ONBOARDING_ANSWER_CAPTURED.eventId`는 `onboarding_answer.client_event_id`에 그대로 저장하고, 같은 답변 재전송에서 새 ID를 만들지 않습니다.
- Backend는 온보딩 세션의 `robot_id`, `senior_id`, `status`, question set의 허용 코드를 검증한 뒤 답변을 저장합니다.
- 로그에 전체 `audioUri`, 인증 토큰이나 개인정보를 기록하지 않습니다.
- 운영 MQTT는 인증과 TLS를 적용합니다. 실제 인증정보는 저장소에 커밋하지 않습니다.
- Backend와 Robot은 `eventId`, `commandId`를 기준으로 QoS 1 중복을 안전하게 처리합니다.
- 더 오래된 `AMBIENT_ENVIRONMENT_OBSERVED.occurredAt`은 최신 `robot.ambient_*`를 덮어쓰지 않습니다.
- `REST_STATE_CHANGED`에는 프레임·관절 좌표·track ID·얼굴 특징을 포함하지 않으며 휴식 후보가 아닌 최종 전이만 발행합니다.

## 11. 담당자 구현 체크리스트

### IoT

- [ ] 단순 문 열림은 `DOOR_OPENED`, 방향 판정이 완료된 사람 감지는 `PRESENCE_DETECTED`로 구분함
- [ ] `PRESENCE_DETECTED` 방향 판정에 사용하는 센서 조합과 `detectionMethod`를 합의함
- [ ] 온습도 단위·보정·발행 주기·의미 있는 변화량·임계 정책 버전을 합의함
- [ ] 초당 원시 온습도 스트림을 중앙 MQTT/DB로 보내지 않음
- [ ] 재전송 시 같은 `eventId`를 유지함
- [ ] `sourceId`와 토픽의 장치 ID가 일치함

### Backend

- [ ] 네 구독 패턴과 Robot 명령 토픽을 설정함
- [ ] `eventId`, `commandId` 멱등 처리를 구현함
- [ ] 10테이블 MVP에서는 명령 ID·업무 상태·발행 대기 상태를 먼저 저장하고 커밋 후 같은 `commandId`로 발행함(별도 Outbox는 측정된 필요가 생길 때 분리)
- [ ] 온보딩 eventId를 `client_event_id`에 원문 저장하고 같은 ID 재전송 시 기존 answer를 반환함
- [ ] 세션 로봇·상태·question code·revision을 검증하고 최종 반영은 `materialization_key`로 한 번만 수행함
- [ ] 만료·실패·순서 역전 결과를 처리함
- [ ] 최신 온습도 스냅샷과 임계 사건 저장을 분리하고 오래된 관측의 역덮어쓰기를 차단함
- [ ] 휴식 시작/종료 external event를 멱등 처리하고 `REST_OBSERVATION`을 연결함

### Robot

- [ ] MQTT Bridge가 `NAVIGATE`, `SPEAK`, `CANCEL`을 ROS 2 작업으로 변환함
- [ ] 상태와 최종 결과를 구분해 발행함
- [ ] 진행 상태의 `sequence`를 `commandId`별로 단조 증가시킴
- [ ] 만료되거나 중복된 명령을 재실행하지 않음
- [ ] 이동·재생 취소 결과를 `CANCEL_RESULT`로 반환함
- [ ] 음성 바이너리를 MQTT로 요청하거나 발행하지 않음
- [ ] 동일 온보딩 답변을 재전송할 때 같은 `eventId`, `sessionId`, `questionCode`, `revision`을 유지함
- [ ] 온보딩 답변 이벤트에 전체 STT·음성·프롬프트·모델 응답을 포함하지 않음
- [ ] 누움 지속시간 미달 후보는 `REST_STATE_CHANGED`로 발행하지 않음
- [ ] `REST_GUARD`에서 일반 능동 기능을 억제하고 호출·안전·긴급 기능 allowlist는 유지함
- [ ] 프레임·관절 좌표·track ID·얼굴 특징을 휴식 이벤트에 포함하지 않음
