# API·메시지 계약 문서

## 1. 목적

BOMI의 서비스 간 계약을 한 진입점에서 열람하기 위한 안내입니다. REST의 기계 판독 계약은 OpenAPI로, MQTT의 기계 판독 스펙은 AsyncAPI로 관리하며 두 문서는 서로 링크로 오갈 수 있습니다. 다만 5개 시나리오 메시지의 최종 기준은 [`../mqtt/scenario-contract-v1.md`](../mqtt/scenario-contract-v1.md)이며, AsyncAPI나 설명 문서와 충돌하면 시나리오 계약 v1을 우선합니다.

OpenAPI와 AsyncAPI의 브라우저 렌더링용 스펙 파일은 Spring Boot 정적 리소스 디렉터리에서 각각 한 벌만 관리합니다. 이는 동일 스펙의 YAML·JSON 사본을 이중 관리하지 않는다는 뜻이며, 시나리오 메시지 의미의 계약 우선순위는 위 기준을 따릅니다.

## 2. 도메인별 문서 위치

| 도메인 | 무엇을 보는가 | 어디서 보는가 |
| --- | --- | --- |
| Backend — 로봇·AI 채널 | 로봇(`ai_chat`)이 호출하는 REST API | Swagger UI → `[BE-Robot] 로봇·AI 채널 API` |
| Backend — 가디언웹 채널 | 가디언웹이 호출하는 REST API | Swagger UI → `[BE-Guardian] 가디언웹 채널 API` |
| Backend — 전체 | 위 두 채널과 운영용 엔드포인트 전부 | Swagger UI → `[BE-All] 백엔드 전체 API` |
| AI Vision | 인식 요청·결과 Callback 계약 | Swagger UI → `[AI-Vision] ...` (**미구현 계약**) |
| AI Chat (대화·음성) | 문장·TTS 생성 계약 | Swagger UI → `[AI-Chat] ...` (**미구현 계약**) |
| IoT·Robot·AI 주행 | MQTT 토픽과 메시지 계약 | AsyncAPI 뷰어 `/asyncapi/mqtt/` |
| 스트리밍 (예정) | WebSocket 메시지 계약 | `/asyncapi/websocket/` (**구현체 없음**) |
| 프론트엔드 | 자체 제공 API가 없습니다 | 해당 없음 |

### AI 서비스는 왜 REST 스펙이 "미구현 계약"인가

`robot/ai_chat`은 HTTP 서버가 아니라 **MQTT 소비자이자 Backend 호출자**입니다. `robot/ai_vision`은 아직 빈 패키지입니다. 따라서 두 도메인의 OpenAPI 문서는 합의된 계약일 뿐 지금 호출할 수 있는 API가 아니며, 제목에 `(계약·미구현)`을 붙여 구분합니다.

`ai_chat`이 **호출하는** API는 실제로 동작하며 `[BE-Robot]` 그룹에 있습니다. `ai_chat`이 **구독·발행하는** 메시지는 AsyncAPI 뷰어에 있습니다.

| `ai_chat` 모듈 | 호출 대상 |
| --- | --- |
| `context_client` | `POST /api/v1/seniors/{seniorId}/conversation-context` |
| `contract_client` | `/api/v1/robot/onboarding` |
| `conversation_client` | `/api/v1/robot/conversation-events` |
| `door_client` | `/api/v1/seniors/{seniorId}/door-events` |

## 3. 팀 공용 배포 주소

진입점은 `/docs/` 하나입니다. 여기서 세 문서로 전부 갈 수 있습니다.

```text
https://i15e102.p.ssafy.io/docs/
├── HTTP API
│   └── /swagger-ui/index.html
└── Event/Streaming API
    ├── /asyncapi/mqtt/
    └── /asyncapi/websocket/
```

문서 주소와 실제 통신 주소는 다릅니다.

| 프로토콜 | 실제 통신 주소 | 상태 |
| --- | --- | --- |
| HTTP | `https://i15e102.p.ssafy.io/api/v1/...` | 동작 |
| WebSocket | `wss://i15e102.p.ssafy.io/api/v1/ws` | 미구현 |
| MQTT | `mqtts://i15e102.p.ssafy.io:8883` | 동작 |

개별 스펙 파일도 같은 배포 서버에서 받을 수 있습니다.

```text
/openapi/vision-ai.openapi.yaml
/openapi/vision-callback.openapi.yaml
/openapi/voice-ai.openapi.yaml
/openapi/bomi-mqtt.asyncapi.yaml
/openapi/bomi-mqtt.asyncapi.json
```

Swagger UI의 `Try it out` 은 **켜져 있습니다.** 로봇·가디언웹 채널 API는 브라우저에서 바로 호출할 수 있으며 **실제 데이터가 바뀝니다.** 쓰기 메서드는 무엇을 건드리는지 확인하고 누르십시오. 이 서비스에는 인증이 없으므로 문서 주소를 아는 사람은 누구나 같은 일을 할 수 있습니다 — 발표 기간 한정으로 감수한 결정입니다.

MQTT와 WebSocket은 HTTP가 아니라 브라우저에서 발행·구독 시험을 할 수 없습니다. 두 페이지는 계약 열람 전용입니다.

배포 문서는 배포된 Backend 이미지에 포함된 파일이므로, 최신 Git 변경은 Backend가 다시 배포된 뒤 반영됩니다.

## 4. 스펙 목록

| 스펙 | 형식 | 호출·전달 방향 | 표현·구현 원본 |
| --- | --- | --- | --- |
| 로봇·AI 채널 API | OpenAPI (자동생성) | Robot·AI → Spring Boot | 컨트롤러 코드 |
| 가디언웹 채널 API | OpenAPI (자동생성) | 가디언웹 → Spring Boot | 컨트롤러 코드 |
| AI Vision 인식 요청 | OpenAPI (수기) | Spring Boot → AI Vision | [`vision-ai.openapi.yaml`](../../backend/src/main/resources/static/openapi/vision-ai.openapi.yaml) |
| AI Vision 결과 Callback | OpenAPI (수기) | AI Vision → Spring Boot | [`vision-callback.openapi.yaml`](../../backend/src/main/resources/static/openapi/vision-callback.openapi.yaml) |
| 대화·음성 생성 | OpenAPI (수기) | Spring Boot·Robot → 대화·음성 AI | [`voice-ai.openapi.yaml`](../../backend/src/main/resources/static/openapi/voice-ai.openapi.yaml) |
| MQTT 메시지 계약 | AsyncAPI (수기) | IoT·Robot·AI ↔ Spring Boot | 기계 판독: [`bomi-mqtt.asyncapi.yaml`](../../backend/src/main/resources/static/openapi/bomi-mqtt.asyncapi.yaml), 의미 기준: [`scenario-contract-v1.md`](../mqtt/scenario-contract-v1.md) |

관련 문서:

- 5개 시나리오 메시지 최종 계약: [`../mqtt/scenario-contract-v1.md`](../mqtt/scenario-contract-v1.md)
- MQTT 공통 토픽·봉투 규칙: [`../mqtt/topic-convention.md`](../mqtt/topic-convention.md)
- 시나리오: [`../scenario/homecoming-welcome.md`](../scenario/homecoming-welcome.md)

## 5. 네이밍 규칙

### 스펙 파일명

```text
<domain>-<service>.openapi.yaml    REST 계약
<domain>.asyncapi.yaml             메시지 계약
```

### 드롭다운 표시명

도메인 접두어를 대괄호로 붙입니다. 접두어가 없으면 어느 도메인의 계약인지 목록에서 구분되지 않습니다.

```text
[BE-Robot]     백엔드 · 로봇·AI 채널
[BE-Guardian]  백엔드 · 가디언웹 채널
[BE-All]       백엔드 · 전체
[AI-Vision]    AI Vision
[AI-Chat]      대화·음성 AI
[MQTT]         메시지 계약
```

구현체가 아직 없는 계약은 표시명 끝에 `(계약·미구현)`을 붙이고 스펙 `info.description` 첫 문단에도 같은 사실을 적습니다.

### 컨트롤러 태그

모든 `@RestController`에 `@Tag`를 붙이고 **description에 호출 주체를 적습니다.**

```java
@Tag(name = "Robot Door Event", description = "현관 이벤트 전달 — 로봇(ai_chat door_client)이 호출합니다.")
```

`OpenApiDocumentationTest.everyControllerDeclaresATagNamingItsCaller` 가 이를 강제합니다. 태그를 빠뜨리면 springdoc이 클래스명으로 기본 태그를 만들어 주기 때문에 Swagger는 멀쩡해 보이고, "이 API를 누가 호출하는가"라는 정보만 조용히 사라집니다.

## 6. 새 스펙을 추가할 때 수정할 곳

정적 스펙 파일을 하나 추가하면 **세 곳**을 함께 고칩니다. 하나라도 빠지면 배포에서 404가 나거나 드롭다운에 나타나지 않습니다.

1. `backend/src/main/resources/application.yml` — `springdoc.swagger-ui.urls`에 표시명과 경로를 추가합니다.
2. `infra/nginx/conf.d/bomi.conf` — 문서 `location` 정규식의 허용 목록에 파일명을 추가합니다.
3. `docs/api/README.md` — 위 2절 표와 4절 표에 한 줄씩 추가합니다.

`springdoc.group-configs`로 만든 **그룹**은 `swagger-ui.urls`에 적지 않습니다. springdoc이 `display-name`으로 이미 드롭다운에 넣으므로, 또 적으면 같은 항목이 두 번 뜹니다. `OpenApiDocumentationTest.dropdownHasNoDuplicateEntries` 가 이를 잡습니다.

새 API 채널이 생겨 그룹을 추가할 때는 `group-configs`에 `paths-to-match`와 함께 등록하고, `OpenApiDocumentationTest.channelGroupsContainOnlyTheirOwnPaths` 에 확인을 추가합니다.

## 7. 로컬 문서 확인

PostgreSQL 없이 실행할 수 있는 `docs` Profile을 사용합니다.

Windows PowerShell:

```powershell
cd backend
.\gradlew.bat bootRun --args="--spring.profiles.active=docs"
```

macOS 또는 Linux:

```bash
cd backend
./gradlew bootRun --args='--spring.profiles.active=docs'
```

실행 후 다음 주소를 엽니다.

```text
http://localhost:8080/docs/
http://localhost:8080/swagger-ui.html
http://localhost:8080/asyncapi/mqtt/
http://localhost:8080/asyncapi/websocket/
```

PowerShell에서 드롭다운 구성을 확인할 수도 있습니다.

```powershell
$config = Invoke-RestMethod http://localhost:8080/v3/api-docs/swagger-config
$config.urls | Format-Table name, url
```

`docs` Profile은 문서 확인만을 위한 Profile입니다. 실제 API·DB 연동 테스트에는 사용하지 않습니다.

### 실제 개발 환경 실행

Backend 기능과 함께 확인하려면 PostgreSQL을 먼저 실행하고 기본 Profile로 Backend를 시작합니다.

```powershell
docker compose up -d postgres
cd backend
.\gradlew.bat bootRun
```

## 8. 계약 읽는 방법

각 OpenAPI 명세에는 다음 내용이 포함되어 있습니다.

- 호출 주체와 대상 서버
- 요청·응답 필수 필드
- 정상 및 실패 응답 예시
- 내부 서비스 인증 방식
- 멱등성 식별자
- enum과 필드 길이 제한
- 오류 응답 형식

AsyncAPI 명세에는 토픽 주소, 발행자·구독자, 메시지별 필드표와 예시가 포함되어 있습니다.

문서를 제공하는 주소와 각 API를 실제로 호출하는 주소는 구분합니다.

- Vision Callback은 배포 Backend인 `https://i15e102.p.ssafy.io`를 사용합니다.
- AI Vision과 대화·음성 AI는 아직 구현체가 없으며, 명세의 `localhost` 주소는 구현 시점의 예시입니다.
- AI 서버의 실제 주소와 인증정보는 환경변수 또는 비밀 저장소로 주입하며 Git에 저장하지 않습니다.

## 9. 변경 규칙

계약을 변경할 때는 다음 순서를 따릅니다.

1. 5개 시나리오 메시지를 바꾼다면 [`../mqtt/scenario-contract-v1.md`](../mqtt/scenario-contract-v1.md)를 먼저 수정합니다.
2. 시나리오 상태와 호출·전달 방향에 미치는 영향을 확인합니다.
3. `backend/src/main/resources/static/openapi/`의 기계 판독 스펙을 수정합니다.
4. 요청·응답 예시와 오류 응답을 함께 수정합니다.
5. MQTT와 REST에서 사용하는 `eventId`, `scenarioId`, `requestId`, `commandId`, `robotId`의 생성 주체와 의미가 일치하는지 확인합니다.
6. MQTT 계약을 바꿨다면 `scenario-contract-v1.md`, `bomi-mqtt.asyncapi.yaml`, `docs/mqtt/topic-convention.md`를 **함께** 고칩니다. `AsyncApiDocumentationTest.everyDocumentedTopicExistsInTheMarkdownContract` 는 AsyncAPI 토픽이 최종 시나리오 계약에 빠지지 않았는지 검사합니다.
7. `./gradlew test --tests "com.ssafy.bomi.docs.*"` 로 문서 검사를 통과하는지 확인합니다.
8. Robot·AI·Backend 담당자에게 계약 변경 리뷰를 요청합니다.

스펙 원본을 `docs/api/`에 복사해서 이중 관리하지 않습니다.

## 10. AsyncAPI 뷰어에 대한 설계 메모

MQTT 계약은 Swagger UI에서 볼 수 없습니다. OpenAPI 3.x는 HTTP 전용이라 토픽·QoS·발행자/구독자를 표현할 문법이 없습니다. 억지로 `paths`에 넣으면 호출 가능한 REST처럼 보여 오해를 만듭니다.

그래서 별도의 정적 뷰어(`/asyncapi/mqtt/`)를 두되 **새 서버나 새 도메인은 만들지 않았습니다.** Swagger UI와 같은 Backend에서, 같은 주소 아래에서, 서로 링크로 오갑니다.

뷰어는 외부 라이브러리를 쓰지 않는 순수 HTML·CSS·JS입니다. 운영 Nginx의 CSP가 `script-src 'self'`이므로 CDN 렌더러는 차단되고, 번들을 저장소에 넣을 Node 빌드 단계도 없기 때문입니다.

AsyncAPI 뷰어가 렌더링하는 기계 판독 스펙의 원본은 YAML 하나이며, 브라우저가 읽을 JSON은 `AsyncApiSpecController`가 같은 파일을 변환해 내려줍니다. JSON 사본을 따로 커밋하면 두 파일을 맞춰야 하므로 그렇게 하지 않았습니다. 이 단일 원본 원칙은 YAML·JSON 표현에 관한 것이며, 5개 시나리오 메시지 의미의 최종 기준은 [`../mqtt/scenario-contract-v1.md`](../mqtt/scenario-contract-v1.md)입니다.

## 11. 배포 노출 정책

운영 Nginx는 팀 공용 계약 열람을 위해 다음 경로만 Backend로 전달합니다.

```text
/swagger-ui.html
/swagger-ui/**
/docs/
/asyncapi/mqtt/
/asyncapi/mqtt/renderer.js
/asyncapi/websocket/
/asyncapi/style.css
/v3/api-docs/swagger-config
/v3/api-docs/bomi-robot
/v3/api-docs/bomi-guardian
/v3/api-docs/bomi-backend
/openapi/vision-ai.openapi.yaml
/openapi/vision-callback.openapi.yaml
/openapi/voice-ai.openapi.yaml
/openapi/bomi-mqtt.asyncapi.yaml
/openapi/bomi-mqtt.asyncapi.json
```

- 문서와 스펙은 조회 전용이며 GET·HEAD 이외의 요청은 거부합니다.
- 자동 생성 API 문서의 그룹 없는 `/v3/api-docs`는 외부에 공개하지 않습니다.
- 현재 문서 경로에는 별도 로그인이 없으므로 공개 가능한 계약과 예시만 작성합니다.
- 스펙과 예시에는 실제 서비스 토큰이나 비밀번호를 기록하지 않습니다.
- 문서에 새 스펙을 추가하면 6절의 세 곳을 함께 변경합니다.

## 12. 구현 전 합의 항목

- [ ] AI Vision이 인식 요청의 `requestId`, `scenarioId`, `robotId`를 그대로 Callback에 반환함
- [ ] AI Vision과 Backend가 `PERSON_DETECTED`, `PERSON_NOT_FOUND`, `INFERENCE_FAILED`의 의미에 합의함
- [ ] 대화·음성 AI가 같은 `requestId` 재요청에 동일한 결과를 반환함
- [ ] Robot이 AI 서버의 `audioUri`에 접근할 네트워크와 내부 인증 방식을 확인함
- [ ] 모든 서비스가 타임존을 포함한 ISO 8601 시각을 사용함
- [ ] 내부 서비스 토큰을 저장소가 아닌 환경변수 또는 비밀 저장소로 주입함
