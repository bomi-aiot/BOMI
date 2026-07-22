# API 계약 문서

## 1. 목적

BOMI의 서비스 간 REST 계약은 OpenAPI 3.0 YAML로 관리합니다. 이번 버전은 귀가 환영 시나리오에서 사용하는 AI Vision과 대화·음성 AI 연동을 정의합니다.

OpenAPI YAML은 Spring Boot 정적 리소스 디렉터리를 단일 원본으로 사용합니다. 이렇게 하면 Git 문서와 Swagger UI가 서로 다른 내용을 보여주는 문제를 방지하고 Docker 이미지에도 같은 계약이 포함됩니다.

## 2. OpenAPI 명세 목록

| 명세 | 호출 방향 | 주요 API | 원본 |
| --- | --- | --- | --- |
| AI Vision 인식 요청 | Spring Boot → AI Vision | `POST /api/v1/recognitions` | [`vision-ai.openapi.yaml`](../../backend/src/main/resources/static/openapi/vision-ai.openapi.yaml) |
| AI Vision 결과 Callback | AI Vision → Spring Boot | `POST /api/v1/integrations/vision/results` | [`vision-callback.openapi.yaml`](../../backend/src/main/resources/static/openapi/vision-callback.openapi.yaml) |
| 대화·음성 생성 및 다운로드 | Spring Boot·Robot → 대화·음성 AI | `POST /api/v1/conversations/generate`, `GET /api/v1/audio/{audioId}` | [`voice-ai.openapi.yaml`](../../backend/src/main/resources/static/openapi/voice-ai.openapi.yaml) |

관련 메시지와 상태 계약:

- MQTT: [`../mqtt/topic-convention.md`](../mqtt/topic-convention.md)
- 시나리오: [`../scenario/homecoming-welcome.md`](../scenario/homecoming-welcome.md)

## 3. 팀 공용 배포 Swagger UI

팀원은 다음 배포 주소를 API 계약의 공용 열람 링크로 사용합니다.

```text
https://i15e102.p.ssafy.io/swagger-ui.html
```

Backend는 Springdoc Swagger UI에서 세 OpenAPI 명세를 선택해 볼 수 있도록 설정되어 있습니다.

```text
AI Vision Recognition API
AI Vision Result Callback API
Conversation and Voice AI API
```

개별 YAML도 같은 배포 서버에서 확인할 수 있습니다.

```text
https://i15e102.p.ssafy.io/openapi/vision-ai.openapi.yaml
https://i15e102.p.ssafy.io/openapi/vision-callback.openapi.yaml
https://i15e102.p.ssafy.io/openapi/voice-ai.openapi.yaml
```

계약 단계에서 실수로 서비스 연동 API를 호출하지 않도록 Swagger UI의 `Try it out` 기능은 비활성화되어 있습니다. 배포 Swagger에 표시되는 문서는 배포된 Backend 이미지에 포함된 YAML이므로, 최신 Git 변경은 Backend가 다시 배포된 뒤 반영됩니다.

### 로컬 문서 확인

배포 전 변경 내용을 검토할 때는 PostgreSQL 없이 실행할 수 있는 `docs` Profile을 사용합니다.

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

실행 후 다음 로컬 주소를 엽니다.

```text
http://localhost:8080/swagger-ui.html
```

로컬 개별 YAML 주소:

```text
http://localhost:8080/openapi/vision-ai.openapi.yaml
http://localhost:8080/openapi/vision-callback.openapi.yaml
http://localhost:8080/openapi/voice-ai.openapi.yaml
```

PowerShell에서 응답을 확인할 수도 있습니다.

```powershell
Invoke-WebRequest http://localhost:8080/openapi/vision-ai.openapi.yaml
Invoke-WebRequest http://localhost:8080/openapi/vision-callback.openapi.yaml
Invoke-WebRequest http://localhost:8080/openapi/voice-ai.openapi.yaml

$config = Invoke-RestMethod http://localhost:8080/v3/api-docs/swagger-config
$config.urls | Format-Table name, url
```

## 4. 실제 개발 환경 실행

Backend 기능과 함께 확인하려면 PostgreSQL을 먼저 실행하고 기본 Profile로 Backend를 시작합니다.

```powershell
docker compose up -d postgres
cd backend
.\gradlew.bat bootRun
```

`docs` Profile은 문서 확인만을 위한 Profile입니다. 실제 API·DB 연동 테스트에는 사용하지 않습니다.

## 5. 계약 읽는 방법

각 OpenAPI 명세에는 다음 내용이 포함되어 있습니다.

- 호출 주체와 대상 서버
- 요청·응답 필수 필드
- 정상 및 실패 응답 예시
- 내부 서비스 인증 방식
- 멱등성 식별자
- enum과 필드 길이 제한
- 오류 응답 형식

Swagger UI를 제공하는 주소와 각 API를 실제로 호출하는 주소는 구분합니다.

- Vision Callback은 배포 Backend인 `https://i15e102.p.ssafy.io`를 사용합니다.
- AI Vision과 대화·음성 AI는 별도 AI 서버에서 실행되므로 해당 명세의 `localhost` 주소는 개발 예시입니다.
- AI 서버의 실제 주소와 인증정보는 환경변수 또는 비밀 저장소로 주입하며 Git에 저장하지 않습니다.

## 6. 변경 규칙

API 계약을 변경할 때는 다음 순서를 따릅니다.

1. 시나리오 상태와 호출 방향에 미치는 영향을 확인합니다.
2. `backend/src/main/resources/static/openapi/`의 YAML 원본을 수정합니다.
3. 요청·응답 예시와 오류 응답을 함께 수정합니다.
4. MQTT와 REST에서 사용하는 `eventId`, `scenarioId`, `requestId`, `commandId`, `robotId`의 생성 주체와 의미가 일치하는지 확인합니다.
5. Swagger UI에서 변경된 명세가 정상 렌더링되는지 확인합니다.
6. Robot·AI·Backend 담당자에게 계약 변경 리뷰를 요청합니다.

YAML 원본을 `docs/api/`에 복사해서 이중 관리하지 않습니다.

## 7. 구현 전 합의 항목

- [ ] AI Vision이 인식 요청의 `requestId`, `scenarioId`, `robotId`를 그대로 Callback에 반환함
- [ ] AI Vision과 Backend가 `PERSON_DETECTED`, `PERSON_NOT_FOUND`, `INFERENCE_FAILED`의 의미에 합의함
- [ ] 대화·음성 AI가 같은 `requestId` 재요청에 동일한 결과를 반환함
- [ ] Robot이 AI 서버의 `audioUri`에 접근할 네트워크와 내부 인증 방식을 확인함
- [ ] 모든 서비스가 타임존을 포함한 ISO 8601 시각을 사용함
- [ ] 내부 서비스 토큰을 저장소가 아닌 환경변수 또는 비밀 저장소로 주입함

## 8. 배포 노출 정책

운영 Nginx는 팀 공용 계약 열람을 위해 다음 경로만 Backend로 전달합니다.

```text
/swagger-ui.html
/swagger-ui/**
/v3/api-docs/swagger-config
/openapi/vision-ai.openapi.yaml
/openapi/vision-callback.openapi.yaml
/openapi/voice-ai.openapi.yaml
```

- Swagger UI와 YAML은 조회 전용이며 GET·HEAD 이외의 요청은 거부합니다.
- 자동 생성 API 문서인 `/v3/api-docs`는 비활성화하고 외부에 공개하지 않습니다.
- 현재 문서 경로에는 별도 로그인이 없으므로 공개 가능한 계약과 예시만 작성합니다.
- OpenAPI YAML과 예시에는 실제 서비스 토큰이나 비밀번호를 기록하지 않습니다.
- 문서에 새로운 YAML을 추가하면 Springdoc 목록과 Nginx 허용 목록을 함께 변경합니다.
