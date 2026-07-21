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

## 3. Swagger UI 실행

Backend는 Springdoc Swagger UI에서 세 OpenAPI 명세를 선택해 볼 수 있도록 설정되어 있습니다.

### 문서 전용 Profile

문서만 확인할 때는 PostgreSQL 없이 실행할 수 있는 `docs` Profile을 사용합니다.

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
http://localhost:8080/swagger-ui.html
```

Swagger UI 상단의 명세 선택 메뉴에서 다음 항목을 전환할 수 있습니다.

```text
AI Vision Recognition API
AI Vision Result Callback API
Conversation and Voice AI API
```

계약 단계에서 실수로 서비스 연동 API를 호출하지 않도록 Swagger UI의 `Try it out` 기능은 비활성화되어 있습니다.

### 개별 YAML 확인

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

OpenAPI의 `localhost` 서버 주소와 토큰 형식은 계약 예시입니다. 실제 주소와 인증정보를 YAML, 코드 또는 Git에 저장하지 않습니다.

## 6. 변경 규칙

API 계약을 변경할 때는 다음 순서를 따릅니다.

1. 시나리오 상태와 호출 방향에 미치는 영향을 확인합니다.
2. `backend/src/main/resources/static/openapi/`의 YAML 원본을 수정합니다.
3. 요청·응답 예시와 오류 응답을 함께 수정합니다.
4. MQTT에서 사용하는 `scenarioId`, `commandId`, `robotId`와 의미가 일치하는지 확인합니다.
5. Swagger UI에서 변경된 명세가 정상 렌더링되는지 확인합니다.
6. Robot·AI·Backend 담당자에게 계약 변경 리뷰를 요청합니다.

YAML 원본을 `docs/api/`에 복사해서 이중 관리하지 않습니다.

## 7. 구현 전 합의 항목

- [ ] AI Vision이 인식 요청의 `requestId`, `scenarioId`, `robotId`를 그대로 Callback에 반환함
- [ ] AI Vision과 Backend가 `PERSON_DETECTED`, `PERSON_NOT_FOUND`, `INFERENCE_FAILED`의 의미에 합의함
- [ ] 대화·음성 AI가 같은 `commandId` 재요청에 동일한 결과를 반환함
- [ ] Robot이 AI 서버의 `audioUri`에 접근할 네트워크와 내부 인증 방식을 확인함
- [ ] 모든 서비스가 타임존을 포함한 ISO 8601 시각을 사용함
- [ ] 내부 서비스 토큰을 저장소가 아닌 환경변수 또는 비밀 저장소로 주입함

## 8. 운영 노출 주의사항

현재 Swagger UI는 개발자가 Backend의 8080 포트에 직접 접근하는 로컬 확인용입니다. 운영 Nginx는 Swagger 및 OpenAPI 경로를 외부로 프록시하지 않습니다.

운영 환경에 Swagger UI를 공개하려면 별도 보안 검토 후 다음 경로의 접근 정책을 결정해야 합니다.

```text
/swagger-ui.html
/swagger-ui/**
/v3/api-docs/**
/openapi/**
```
