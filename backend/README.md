# BOMI Backend

Java 17 / Spring Boot / Gradle 기반 중앙 백엔드입니다.

1. 루트 `.env.example`을 루트 `.env`로 복사하고 값을 설정합니다. `docker compose`와
   `./gradlew bootRun`이 같은 파일을 읽습니다. (`backend/.env.example`은 백엔드 단독
   실행용 부분집합이며, 둘을 동시에 쓰지 않습니다.)
2. 루트에서 `docker compose up -d`로 PostgreSQL + pgvector와 Mosquitto를 시작합니다.
3. 이 디렉터리에서 `./gradlew bootRun`(Windows: `gradlew.bat bootRun`)을 실행합니다.
4. `GET http://localhost:8080/api/health`로 상태를 확인합니다.

MQTT는 구독·발행 양방향 모두 구현되어 있습니다. IoT·로봇 이벤트를 받는 인바운드
(`mqtt/inbound/`)와 로봇 이동 명령·AI 대화 명령을 내보내는 아웃바운드(`mqtt/outbound/`)가
Spring Integration 위에 올라가 있고, 메시지 형식의 최종 기준은
[`docs/mqtt/scenario-contract-v1.md`](../docs/mqtt/scenario-contract-v1.md)입니다.
로컬에서 MQTT를 끄고 싶으면 `MQTT_ENABLED=false`로 둡니다(루트 `.env.example` 기본값).

Flyway 마이그레이션은 애플리케이션이 뜰 때 자동으로 적용됩니다. 빈 PostgreSQL에
`bootRun` 하면 스키마가 만들어집니다.

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

`/actuator/prometheus`로 지표를 노출하지만, 운영 Nginx는 `/actuator` 전체를 404로 막습니다
(`infra/nginx/conf.d/bomi.conf`). 외부에서는 볼 수 없고 Docker 내부 네트워크에서만 읽습니다.

운영자 채널은 fail-closed입니다. `OPERATOR_SHARED_SECRET`이 비어 있으면 운영자 API가
503(`operator authentication is not configured`)을 돌려줍니다.

## 더 볼 곳

| 주제 | 문서 |
| --- | --- |
| API 문서화 규칙(`@Tag`, 그룹, AsyncAPI 3파일 동시 수정) | [`backend/CLAUDE.md`](CLAUDE.md) |
| 브라우저로 API 문서 보기 | `./gradlew bootRun --args='--spring.profiles.active=docs'` → `http://localhost:8080/docs/` |
| 테스트 3종 (`test` 무료 / `integrationTest` Qdrant 필요 / `billedTest` 과금) | [`build.gradle`](build.gradle) 상단 주석 |
| RAG·임베딩·Qdrant 운영 | [`infra/RAG_OPERATIONS.md`](../infra/RAG_OPERATIONS.md) |
| 운영 배포 | [`scripts/deploy/DEPLOYMENT.md`](../scripts/deploy/DEPLOYMENT.md), [`ci/README.md`](../ci/README.md) |
