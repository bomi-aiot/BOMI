# MQTT 토픽 및 메시지 계약

## 1. 목적과 범위

이 문서는 BOMI 외부 장치와 Spring Boot 사이의 MQTT 통신 계약을 정의합니다.
이번 버전은 귀가 환영 시나리오에서 사용하는 센서 이벤트, Robot 이동, 음성 재생만 다룹니다.

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

## 3. 토픽 구조

기본 형식은 다음과 같습니다.

```text
bomi/v1/{domain}/{deviceId}/{channel}
```

| 용도 | 토픽 | 발행자 | 구독자 | QoS |
| --- | --- | --- | --- | ---: |
| IoT 이벤트 | `bomi/v1/iot/{deviceId}/events` | IoT 센서 | Backend | 1 |
| Robot 명령 | `bomi/v1/robot/{robotId}/commands` | Backend | Robot MQTT Bridge | 1 |
| Robot 진행 상태 | `bomi/v1/robot/{robotId}/status` | Robot MQTT Bridge | Backend | 1 |
| Robot 최종 결과 | `bomi/v1/robot/{robotId}/results` | Robot MQTT Bridge | Backend | 1 |

Backend 구독 패턴은 다음과 같습니다.

```text
bomi/v1/iot/+/events
bomi/v1/robot/+/status
bomi/v1/robot/+/results
```

## 4. 식별자와 상관관계

| 필드 | 적용 메시지 | 설명 |
| --- | --- | --- |
| `eventId` | 이벤트·상태·결과 | 생산자가 생성한 메시지 식별자. 재전송 시 같은 값 유지 |
| `scenarioId` | Robot 명령·상태·결과 | Backend가 생성한 E2E 시나리오 식별자 |
| `commandId` | Robot 명령·상태·결과 | 명령과 상태·결과를 연결하는 식별자 |
| `robotId` | Robot 메시지 | 토픽의 `{robotId}`와 반드시 동일해야 함 |
| `occurredAt` | 모든 메시지 | 이벤트 발생 시각. 전송 시각이 아님 |

최초 IoT 이벤트에는 아직 `scenarioId`, `commandId`, `robotId`가 없을 수 있습니다. Backend가 시나리오와 명령을 생성한 이후의 메시지부터 해당 식별자를 사용합니다.

## 5. IoT 센서 이벤트

### `PRESENCE_DETECTED`

현관 센서가 귀가 방향의 사람 또는 문 열림을 감지했을 때 발행합니다.

```json
{
  "eventId": "01K0M4Y7G1D8W3A9H2T6Q5R4NP",
  "type": "PRESENCE_DETECTED",
  "occurredAt": "2026-07-21T10:30:00+09:00",
  "sourceId": "door-sensor-01",
  "payload": {
    "location": "ENTRANCE",
    "direction": "INBOUND"
  }
}
```

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `eventId` | 예 | 이벤트 멱등 키 |
| `type` | 예 | `PRESENCE_DETECTED` 고정 |
| `occurredAt` | 예 | 실제 감지 시각 |
| `sourceId` | 예 | 토픽의 `{deviceId}`와 동일한 센서 ID |
| `payload.location` | 예 | 등록된 논리 위치. 이번 시나리오는 `ENTRANCE` |
| `payload.direction` | 예 | `INBOUND`, `OUTBOUND`, `UNKNOWN` 중 하나 |

Backend는 `direction=INBOUND` 이벤트만 귀가 환영 시나리오의 트리거로 사용합니다. 같은 `eventId`가 다시 전달되면 기존 처리 결과를 유지합니다.

## 6. Backend → Robot 명령

명령의 공통 형태는 다음과 같습니다.

```json
{
  "commandId": "01K0M4Y8B7F5M2N1Q9R6S3T8VX",
  "scenarioId": "01K0M4Y80XD4J7C2H6P9N5Q3RS",
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
  "scenarioId": "01K0M4Y80XD4J7C2H6P9N5Q3RS",
  "robotId": "robot-01",
  "type": "NAVIGATE",
  "occurredAt": "2026-07-21T10:30:01+09:00",
  "expiresAt": "2026-07-21T10:31:01+09:00",
  "payload": {
    "waypointId": "ENTRANCE"
  }
}
```

`waypointId`는 Backend와 Robot이 사전에 합의한 논리 위치 이름입니다. 좌표나 Nav2 세부 파라미터는 MQTT 계약에 노출하지 않고 Robot 설정에서 해석합니다.

### `SPEAK`

```json
{
  "commandId": "01K0M51BR2X6A8D4F9G7H3J5KC",
  "scenarioId": "01K0M4Y80XD4J7C2H6P9N5Q3RS",
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
  "scenarioId": "01K0M4Y80XD4J7C2H6P9N5Q3RS",
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
| `payload.reason` | 예 | `SCENARIO_TIMED_OUT`, `USER_CANCELLED`, `POLICY_CANCELLED` 중 하나 |

Robot MQTT Bridge는 `targetCommandId`의 작업을 찾고 ROS 2/Nav2 또는 음성 재생 노드에 취소를 요청합니다. 취소 요청을 받았다는 이유만으로 대상 작업을 성공 처리하지 않습니다.

## 7. Robot 진행 상태

### `NAVIGATION_STATUS`

진행 상태는 화면 표시와 관찰 가능성을 위한 정보이며 최종 성공·실패 판정은 `results` 토픽으로 전달합니다.

```json
{
  "eventId": "01K0M4Z1CT7N9B5V3X2K8P6QRS",
  "commandId": "01K0M4Y8B7F5M2N1Q9R6S3T8VX",
  "scenarioId": "01K0M4Y80XD4J7C2H6P9N5Q3RS",
  "robotId": "robot-01",
  "type": "NAVIGATION_STATUS",
  "occurredAt": "2026-07-21T10:30:10+09:00",
  "payload": {
    "status": "MOVING",
    "currentLocation": "HALLWAY"
  }
}
```

`payload.status`는 `ACCEPTED`, `MOVING` 중 하나입니다. Backend는 진행 상태만으로 시나리오를 `ARRIVED` 또는 실패 상태로 전환하지 않습니다.

## 8. Robot 최종 결과

### `NAVIGATION_RESULT`

성공 예시:

```json
{
  "eventId": "01K0M50D4S8V2X6Z1B3N7Q9RTP",
  "commandId": "01K0M4Y8B7F5M2N1Q9R6S3T8VX",
  "scenarioId": "01K0M4Y80XD4J7C2H6P9N5Q3RS",
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
  "scenarioId": "01K0M4Y80XD4J7C2H6P9N5Q3RS",
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
  "scenarioId": "01K0M4Y80XD4J7C2H6P9N5Q3RS",
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
  "scenarioId": "01K0M4Y80XD4J7C2H6P9N5Q3RS",
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

## 9. 유효성 및 보안

- 토픽의 `{deviceId}` 또는 `{robotId}`와 payload의 식별자가 다르면 메시지를 거부합니다.
- 알 수 없는 `type`, `status`, `outcome`은 임의로 성공 처리하지 않습니다.
- `occurredAt`이 파싱되지 않거나 필수 필드가 없으면 오류 로그를 남기고 폐기합니다.
- 로그에 전체 `audioUri`, 인증 토큰이나 개인정보를 기록하지 않습니다.
- 운영 MQTT는 인증과 TLS를 적용합니다. 실제 인증정보는 저장소에 커밋하지 않습니다.
- Backend와 Robot은 `eventId`, `commandId`를 기준으로 QoS 1 중복을 안전하게 처리합니다.

## 10. 담당자 구현 체크리스트

### IoT

- [ ] `PRESENCE_DETECTED` 예시를 그대로 발행할 수 있음
- [ ] 재전송 시 같은 `eventId`를 유지함
- [ ] `sourceId`와 토픽의 장치 ID가 일치함

### Backend

- [ ] 세 구독 패턴과 Robot 명령 토픽을 설정함
- [ ] `eventId`, `commandId` 멱등 처리를 구현함
- [ ] 명령 발행과 시나리오 상태 변경을 연결함
- [ ] 만료·실패·순서 역전 결과를 처리함

### Robot

- [ ] MQTT Bridge가 `NAVIGATE`, `SPEAK`, `CANCEL`을 ROS 2 작업으로 변환함
- [ ] 상태와 최종 결과를 구분해 발행함
- [ ] 만료되거나 중복된 명령을 재실행하지 않음
- [ ] 이동·재생 취소 결과를 `CANCEL_RESULT`로 반환함
- [ ] 음성 바이너리를 MQTT로 요청하거나 발행하지 않음
