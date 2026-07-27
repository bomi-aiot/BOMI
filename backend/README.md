# BOMI Backend

Java 17 / Spring Boot / Gradle 기반 중앙 백엔드입니다.

1. 루트 `.env.example`을 `.env`로 복사하고 값을 설정합니다.
2. 루트에서 `docker compose up -d`로 PostgreSQL + pgvector와 Mosquitto를 시작합니다.
3. 이 디렉터리에서 `./gradlew bootRun`(Windows: `gradlew.bat bootRun`)을 실행합니다.
4. `GET http://localhost:8080/api/health`로 상태를 확인합니다.

## MQTT 구독·발행 스켈레톤

Backend는 Spring Integration MQTT를 사용해 다음 토픽을 QoS 1로 구독할 수 있습니다.

```text
bomi/v1/iot/+/events
bomi/v1/robot/+/events
bomi/v1/robot/+/status
bomi/v1/robot/+/results
```

Robot 명령은 `RobotCommandPublisher`를 통해
`bomi/v1/robot/{robotId}/commands`로 발행하며 QoS 1, `retain=false`를 강제합니다.

스켈레톤은 연결·JSON 계약 검증·수동 ACK·발행 경계까지만 제공합니다. 시나리오 상태
전이, DB 멱등 처리와 온보딩 답변 저장은 후속 업무 처리기에서 구현해야 합니다. 실제
업무 처리기 없이 메시지를 소비하지 않도록 MQTT는 기본적으로 비활성화되어 있습니다.

로컬 Broker를 시작한 뒤 다음 환경변수를 설정해 명시적으로 활성화합니다.

```dotenv
MQTT_ENABLED=true
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_CLIENT_ID_PREFIX=bomi-backend-local
MQTT_USERNAME=
MQTT_PASSWORD=
```

운영에서는 서비스별로 고유하고 재시작 후에도 유지되는 client ID prefix를 사용해야
합니다. 실제 인증정보는 저장소에 커밋하지 않습니다. 운영 활성화 전에는 Backend의
`bomi-mqtt-net` 연결, MQTT 환경변수 주입과 `robot/+/events` ACL 권한을 별도로
완료해야 합니다.

## API 계약과 Swagger UI

AI Vision과 대화·음성 AI의 OpenAPI 계약은 `src/main/resources/static/openapi/`에서 관리합니다. 팀 공용 문서는 배포 Swagger UI를 기준으로 확인합니다.

```text
https://i15e102.p.ssafy.io/swagger-ui.html
```

Swagger UI 상단에서 사람 인식 요청, Vision 결과 Callback, 대화·음성 생성 명세를 선택할 수 있습니다. 계약 열람 전용이므로 `Try it out`은 비활성화되어 있습니다.

배포 전 변경 내용을 로컬에서 확인하거나 PostgreSQL 없이 문서만 확인하려면 `docs` Profile로 실행합니다.

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=docs"
```

macOS 또는 Linux:

```bash
./gradlew bootRun --args='--spring.profiles.active=docs'
```

로컬 Swagger UI:

```text
http://localhost:8080/swagger-ui.html
```

상세한 명세 목록, 개별 YAML 주소와 계약 변경 규칙은 [`../docs/api/README.md`](../docs/api/README.md)를 참고합니다.

## Docker 이미지

운영 이미지는 `backend/Dockerfile`의 멀티스테이지 빌드를 사용합니다.

- 빌드: Eclipse Temurin Java 17 JDK + Gradle Wrapper
- 실행: Eclipse Temurin Java 17 JRE
- 실행 사용자: UID/GID 10001의 비-root 사용자 `bomi`
- Health check: `GET /actuator/health`
- 컨테이너 포트: 8080

저장소 루트에서 이미지를 빌드할 수 있습니다.

```bash
docker build -t bomi-backend:local backend
```

운영 환경에서는 8080을 호스트에 직접 공개하지 않고 Nginx와 Docker 내부 네트워크로 연결합니다.
