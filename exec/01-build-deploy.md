# BOMI 포팅 매뉴얼 ① — 빌드 및 배포

> GitLab 소스를 클론한 상태에서 빌드·배포를 재현하기 위한 문서입니다.
> 저장소 루트 기준 경로를 사용합니다.

- 대상 저장소: `S15P11E102` (모노레포)
- 배포 도메인: `https://i15e102.p.ssafy.io`
- 배포 대상: AWS EC2 (Ubuntu) 단일 호스트 + Docker Compose
- 작성 기준 커밋: `[머지 후 기입]` / 작성일: `2026-08-__`

---

## 0. 저장소 구조

| 디렉터리 | 내용 | 빌드 산출물 |
| --- | --- | --- |
| `backend/` | Spring Boot 중앙 백엔드 | `bomi-backend` 이미지 (`app.jar`) |
| `frontend/` | React 보호자 대시보드 | `bomi-frontend` 이미지 (정적 파일 + nginx) |
| `robot/` | ROS 2 워크스페이스, AI 대화(`ai_chat`), AI 비전(`ai_vision`), Pico 펌웨어 | 로봇 장비에서 직접 빌드 |
| `robot/tools/waypoint_editor/` | 웨이포인트 편집 도구 (Streamlit) | `bomi-waypoint-editor` 이미지 |
| `backend/tools/operator_console/` | 운영자 콘솔 (Streamlit) | `bomi-operator-console` 이미지 |
| `iot/` | Raspberry Pi 5 / Jetson / 센서 / MQTT | 장치에서 직접 설치 |
| `infra/` | Compose, Nginx, Mosquitto, Jenkins, Postgres 초기화 | — |
| `scripts/deploy/` | 배포 스크립트 | — |
| `docs/` | 아키텍처·API·MQTT·DB·시나리오 문서 | — |

---

## 1. 사용 제품 종류·설정값·버전

### 1.1 개발 환경 (IDE)

| 항목 | 값 |
| --- | --- |
| Backend IDE | IntelliJ IDEA 2023.3.8 (Ultimate Edition) |
| Frontend IDE | VS Code 1.132.0 |
| Robot 개발 환경 | Ubuntu 22.04 (WSL2 포함), VS Code 1.132.0 |
| 형상 관리 | GitLab (SSAFY) + GitHub 미러 |

### 1.2 Backend

| 항목 | 종류 / 버전 | 근거 파일 |
| --- | --- | --- |
| JVM (빌드) | Eclipse Temurin **17** JDK (`eclipse-temurin:17-jdk-jammy`) | `backend/Dockerfile` |
| JVM (런타임) | Eclipse Temurin **17** JRE (`eclipse-temurin:17-jre-jammy`) | `backend/Dockerfile` |
| Java toolchain | `JavaLanguageVersion.of(17)` | `backend/build.gradle` |
| 빌드 도구 | Gradle Wrapper **8.14.2** | `backend/gradle/wrapper/gradle-wrapper.properties` |
| 프레임워크 | Spring Boot **3.4.7** | `backend/build.gradle` |
| 의존성 관리 | `io.spring.dependency-management` **1.1.7** | `backend/build.gradle` |
| **WAS** | **Spring Boot 내장 Tomcat** (별도 WAS 제품 없음, 실행형 JAR) | `spring-boot-starter-web` |
| 서비스 포트 | 컨테이너 내부 **8080** (호스트 미공개) | `infra/compose.prod.yml` |
| API 문서 | springdoc-openapi-starter-webmvc-ui **2.8.17** | `backend/build.gradle` |
| DB 마이그레이션 | Flyway (`flyway-core`, `flyway-database-postgresql`) — Spring Boot 관리 버전 | `backend/build.gradle` |
| 벡터 DB 클라이언트 | `io.qdrant:client` **1.18.3** (gRPC) | `backend/build.gradle` |
| MQTT | `spring-integration-mqtt` | `backend/build.gradle` |
| 기타 | WebSocket, Actuator, Micrometer Prometheus, Lombok, JPA, Validation | `backend/build.gradle` |
| JVM 런타임 옵션 | `-XX:MaxRAMPercentage=75.0 -XX:+ExitOnOutOfMemoryError -Duser.timezone=UTC` | `infra/compose.prod.yml` |
| 컨테이너 자원 | 메모리 1GB / CPU 1.5 / read-only FS / non-root(uid 10001) | `infra/compose.prod.yml` |

**빌드 명령**

```bash
# 로컬
cd backend && ./gradlew bootJar      # Windows: gradlew.bat bootJar
cd backend && ./gradlew bootRun      # 개발 실행

# 컨테이너 (빌드 컨텍스트가 저장소 루트인 점에 주의)
docker build -f backend/Dockerfile -t bomi-backend .
```

> ⚠️ `backend/Dockerfile`의 빌드 컨텍스트는 **저장소 루트**입니다. `build.gradle`의
> `processResources`가 `docs/database/onboarding-question-set-v1.json`을 클래스패스로
> 복사하므로, `backend/` 디렉터리만으로는 빌드되지 않습니다.

**테스트 태스크 (외부 의존/과금 분리)**

| 명령 | 범위 | 외부 의존 | 과금 |
| --- | --- | --- | --- |
| `./gradlew test` | 단위 테스트 (`integration`·`billed` 태그 제외) | 없음 | 없음 |
| `QDRANT_HOST=localhost ./gradlew integrationTest` | Qdrant 필요 통합 테스트 | Qdrant | 없음 |
| `UPSTAGE_API_KEY=... ./gradlew billedTest` | 실제 Upstage 임베딩 왕복 | Upstage API | **과금** |

### 1.3 Frontend

| 항목 | 종류 / 버전 | 근거 파일 |
| --- | --- | --- |
| Node.js (빌드) | **24.18.0** (`node:24.18.0-alpine`) | `frontend/Dockerfile` |
| 패키지 매니저 | npm (`npm ci`, `package-lock.json` 고정) | `frontend/Dockerfile` |
| 번들러 | Vite | `frontend/package.json` |
| 언어 | TypeScript (`tsc --noEmit` → `vite build`) | `frontend/package.json` |
| UI | React + `@vitejs/plugin-react`, three.js `^0.185.1` | `frontend/package.json` |
| 정적 서빙 | **nginx 1.30.4-alpine**, 컨테이너 내부 **8080** | `frontend/Dockerfile`, `frontend/nginx.conf` |
| 개발 서버 포트 | 5173 | `README.md` |
| 컨테이너 자원 | 메모리 128MB / CPU 0.5 / read-only FS | `infra/compose.prod.yml` |

**빌드 명령**

```bash
cd frontend
npm ci          # 또는 npm install
npm run dev     # 개발 서버 (5173)
npm run build   # tsc --noEmit && vite build → dist/
```

### 1.4 웹서버 / 리버스 프록시

| 항목 | 값 |
| --- | --- |
| 제품 | **nginx 1.30.4-alpine** (공개 진입점) |
| 공개 포트 | 80 (HTTPS 리다이렉트), 443 |
| 설정 파일 | `infra/nginx/conf.d/bomi.conf` (운영), `infra/nginx/bootstrap.conf` (인증서 최초 발급용) |
| TLS 인증서 | Let's Encrypt, `certbot/certbot:v5.7.0` |
| 인증서 경로 | `/home/ubuntu/bomi/data/certbot/conf` |
| ACME webroot | `/home/ubuntu/bomi/data/certbot/www` |
| 갱신 | `scripts/deploy/renew-certificates.sh`, cron **UTC 03:17 (KST 12:17)** 매일 |
| 라우팅 | `/` → frontend, `/api/` → backend:8080, `/ws` → backend WebSocket, `/operator-console/`·`/waypoint-editor/` → Streamlit(Basic 인증), `/jenkins` → Jenkins |
| 차단 | `/actuator` 외부 노출 차단(404) |

### 1.5 데이터 저장소 / 브로커

| 항목 | 종류 / 버전 | 포트 | 비고 |
| --- | --- | --- | --- |
| RDB | **pgvector/pgvector:0.8.5-pg17** (PostgreSQL 17 + pgvector 0.8.5) | 5432 (내부 전용) | 데이터: `/home/ubuntu/bomi/data/postgres` |
| 벡터 스토어 | **qdrant/qdrant:v1.18.3** | 6333(HTTP)/6334(gRPC), 내부 전용 | named volume `bomi-qdrant-storage` |
| MQTT 브로커 | **eclipse-mosquitto:2** | 1883 / 9001(WS) / 8883(TLS, 운영) | `infra/compose.mqtt.prod.yml` 별도 스택 |

> pgvector가 아닌 Qdrant를 쓰는 이유: Upstage `solar-embedding-1-large` 출력이 **4096차원**인데
> pgvector 0.8.5의 인덱싱 상한은 vector 2,000 / halfvec 4,000차원이라 인덱스를 만들 수 없습니다.
> PostgreSQL이 여전히 **권위 저장소**이고 Qdrant는 파생 인덱스입니다(볼륨 유실 시 `embedding_status`
> 컬럼으로 전량 재색인 가능, `V5__add_embedding_sync_columns.sql`).

### 1.6 CI/CD

| 항목 | 값 |
| --- | --- |
| CI 도구 | **Jenkins 2.555.3** (`jenkins/jenkins:2.555.3-jdk21` 기반 커스텀 이미지) |
| 접근 경로 | `https://i15e102.p.ssafy.io/jenkins` (`JENKINS_OPTS=--prefix=/jenkins`) |
| JVM 옵션 | `-Xms256m -Xmx1536m -Djava.awt.headless=true` |
| 플러그인 | `credentials-binding`, `git`, `gitlab-plugin:1.9.16`, `pipeline-stage-view`, `workflow-aggregator` |
| 파이프라인 | 저장소 루트 `Jenkinsfile` (Checkout → Validate → Build → Deploy, 타임아웃 20분) |
| 워크스페이스 | `/home/ubuntu/bomi/data/jenkins/workspace/bomi-production` |
| Docker 접근 | `/var/run/docker.sock` 마운트 + `DOCKER_GID` group_add |

### 1.7 Robot (별도 장비)

| 항목 | 값 |
| --- | --- |
| OS | Ubuntu **22.04** |
| ROS | **ROS 2 Humble** |
| Python | **3.10** (ai_chat은 `>=3.10,<3.13`) |
| 빌드 | `colcon build --symlink-install` |
| 내비게이션 | Nav2, SLAM Toolbox, AMCL |
| 주요 패키지 | `core`, `description`, `simulation`, `mapping`, `bomi_lidar`, `bomi_obstacle_detection`, `bridge` |
| 외부 소스 | `src/rf2o_laser_odometry` — Git 미추적, `robot/ros2_ws/rf2o.repos`로 가져옴 |
| AI 대화 (`robot/ai_chat`) | langgraph `>=1.2,<2`, langgraph-checkpoint-sqlite `>=3.1,<4`, APScheduler `>=3.10`, openwakeword `>=0.6`, onnxruntime, sounddevice, paho-mqtt `>=1.6,<2` |
| 컴퓨트 | Jetson Orin Nano (systemd `iot/jetson/bomi-robot.service`) |
| 구동계 | JGB37-520 엔코더 모터 ×4, MDD10A, Raspberry Pi Pico H (펌웨어 `robot/pico/`) |
| 센서 | YDLIDAR X4-PRO, 카메라, IMU |

**빌드 명령**

```bash
cd robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install          # 일부만: --packages-up-to core
source install/setup.bash
```

> ⚠️ `paho-mqtt`는 **1.x 계열 고정**입니다. 2.x는 생성자에서 `CallbackAPIVersion`을
> 요구하므로 `ai_chat/door/mqtt.py`, `robot_events.py`, `ros2_ws`의 `bridge` 세 곳을
> 함께 수정하지 않으면 즉시 실패합니다.
>
> ⚠️ Jetson(aarch64)에서는 `onnxruntime`이 ARM wheel로 설치되는지 장치에서 직접 확인해야 합니다.

### 1.8 IoT (별도 장비)

| 항목 | 값 |
| --- | --- |
| 게이트웨이 | Raspberry Pi 5 |
| Zigbee | Zigbee2MQTT + 로컬 Mosquitto (`iot/raspberry-pi/zigbee2mqtt/compose.yaml`) |
| 번역기 | Python (`iot/raspberry-pi/translator/`), `requirements.txt` |
| 온습도 | DHT11 — BCM GPIO4(물리 7번), 3.3V(1번), GND(9번), 30초 주기, QoS 1, retain false |
| 자동 실행 | `translator/config/bomi-dht11.service` (systemd, 배포 경로 `/opt/bomi/iot`) |
| 발행 토픽 | `bomi/v1/iot/<sourceId>/events` |

---

## 2. 빌드 시 사용되는 환경 변수

### 2.1 환경변수 파일 3계층

| 계층 | 파일 | Git 관리 | 용도 |
| --- | --- | --- | --- |
| 예제 | `.env.example`, `backend/.env.example`, `frontend/.env.example`, `infra/production.env.example`, `infra/mqtt.env.example` | **O** | 형식·기본값 정의 |
| 로컬 개발 | `.env`, `backend/.env`, `frontend/.env` | **X** (`.gitignore`) | 개발자 로컬 값 |
| 운영 | `/home/ubuntu/bomi/secrets/production.env` (권한 600) | **X** (서버에만 존재) | 실제 비밀값 |

### 2.2 로컬 개발 환경변수 (`.env.example` 기준)

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `localhost` / `5432` | 로컬 DB |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `bomi` / `bomi` / `change-me` | DB 계정 |
| `MQTT_BROKER_HOST` / `MQTT_BROKER_PORT` | `localhost` / `1883` | 로컬 브로커 |
| `MQTT_ENABLED` | `false` | 로컬 기본 비활성 |
| `MQTT_CLIENT_ID_PREFIX` | `bomi-backend` | 클라이언트 ID 접두 |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | `change-me` | 브로커 인증 |
| `BACKEND_PORT` / `FRONTEND_PORT` | `8080` / `5173` | 서비스 포트 |
| `AI_CONVERSATION_START_TIMEOUT` | `10s` | AI 대화 시작 확인 타임아웃 |
| `AI_CONVERSATION_MAX_DURATION` | `5m` | 대화 최대 지속 |
| `AI_CONVERSATION_TIMEOUT_CHECK_INTERVAL_MILLIS` | `1000` | 타임아웃 점검 주기 |
| `EMBEDDING_ENABLED` | `false` | ★ 과금 API — 명시적으로만 켬 |
| `EMBEDDING_SYNC_ENABLED` | `false` | 배경 재색인 잡 (최초 1회만 켜서 채운 뒤 끔) |
| `QDRANT_HOST` | (빈값) | 비우면 의미 검색 OFF로 기동 |
| `UPSTAGE_API_KEY` | (빈값) | 비우면 임베딩 생성 불가 |
| `LLM_ENABLED` | `false` | ★ 과금 API |
| `GEMINI_API_KEY` | (빈값) | 비우면 대화 요약 생성 불가 |

### 2.3 Frontend 환경변수 (`frontend/.env.example`)

| 변수 | 로컬 기본 | 운영 값 | 설명 |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | `/api` | `/api` | Nginx 동일 출처 프록시 |
| `VITE_WS_URL` | `/ws` | `/ws` | WebSocket 경로 |
| `VITE_USE_MOCK_API` | `true` | **`false`** | 구현체 선택 (`MockBomiService` ↔ `HttpBomiService`) |
| `VITE_GUARDIAN_API_AUTH_READY` | `false` | **`true`** | `HttpBomiService`의 `assertGuardianApiReady()` 게이트 |

> ### ★★ 가장 중요한 빌드 특이사항
> Vite는 `import.meta.env.VITE_*`를 **빌드 타임에 정적 치환**합니다.
> 컨테이너 런타임 환경변수로는 **절대 바뀌지 않습니다.** 따라서 두 플래그는
> `frontend/Dockerfile`의 `ARG`로 굳혀져 있습니다(`VITE_USE_MOCK_API=false`,
> `VITE_GUARDIAN_API_AUTH_READY=true`).
>
> **두 값은 반드시 함께 뒤집어야 합니다.** 하나만 바꾸면 `HttpBomiService`를 고르고도
> 게이트에 막혀 전 화면이 비어 보입니다.
>
> 예시 데이터로 롤백:
> ```bash
> docker compose build \
>   --build-arg VITE_USE_MOCK_API=true \
>   --build-arg VITE_GUARDIAN_API_AUTH_READY=false frontend
> ```

### 2.4 운영 환경변수 (`infra/production.env.example` → `secrets/production.env`)

#### (1) 데이터베이스

| 변수 | 값/예시 | 비고 |
| --- | --- | --- |
| `POSTGRES_DB` | `bomi` | 필수 (`:?` 선언) |
| `POSTGRES_USER` | `bomi` | 필수 |
| `POSTGRES_PASSWORD` | `openssl rand -hex 32` 결과 | 필수 · **비밀** |
| `POSTGRES_DATA_DIR` | `/home/ubuntu/bomi/data/postgres` | 필수 · 절대 경로 (bind mount) |

#### (2) 벡터 스토어 / 의미 검색

| 변수 | 기본 | 비고 |
| --- | --- | --- |
| `QDRANT_API_KEY` | (빈값) | 설정 시 Qdrant가 인증 요구 |
| `UPSTAGE_API_KEY` | (빈값) | ★ 과금 · **비밀** |
| `EMBEDDING_ENABLED` | `false` | ★ **`UPSTAGE_API_KEY`만 넣으면 켜지지 않습니다** |
| `EMBEDDING_SYNC_ENABLED` | `false` | 최초 1회 켜서 컬렉션을 채운 뒤 끔 |
| `EMBEDDING_SYNC_BATCH_SIZE` | `30` | 1회 실행당 과금 호출 상한 |
| `DOCUMENT_CORPUS_ENABLED` | `true` | 번들 코퍼스 (네트워크 불필요) |
| `DOCUMENT_CORPUS_RESOURCE` | `classpath:rag/welfare-corpus.json` | |

#### (3) 생성형 LLM (대화 요약)

| 변수 | 기본 | 비고 |
| --- | --- | --- |
| `GEMINI_API_KEY` | (빈값) | GMS 경유 · ★ 과금 · **비밀** |
| `LLM_ENABLED` | `false` | ★ 키만 넣으면 켜지지 않습니다 |
| `LLM_MAX_CALLS_PER_RUN` | `20` | 지출 상한 (튜닝값 아님) |
| `CONVERSATION_IDLE_TIMEOUT` | `30m` | 대화 경계 유휴시간 |

#### (4) 시나리오 / 런타임 튜닝 (재배포 없이 컨테이너 재시작만으로 반영)

| 변수 | 기본 | 설명 |
| --- | --- | --- |
| `WELLNESS_SCENARIO_ENABLED` | `true` | 온습도 안부 확인 시나리오 |
| `WELLNESS_TEMP_THRESHOLD` | `30.0` | 온도 임계값(°C) |
| `WELLNESS_HUMIDITY_THRESHOLD` | `80.0` | 습도 임계값(%RH) |
| `WELLNESS_COOLDOWN_MINUTES` | `30` | 재발동 쿨다운 |
| `ENTRANCE_DIRECTION_RESOLUTION_ENABLED` | `false` | 현관 IN/OUT 방향 판정 |
| `ENTRANCE_CORRELATION_WINDOW` | `15s` | 문↔PIR 상관 윈도우 |
| `ENTRANCE_GREETING_TTL` | `45s` | 인사 유효시간 |
| `ENTRANCE_REVERSAL_WINDOW` | `30s` | 방향 뒤집힘 허용 창 |
| `MEDICATION_GRACE_MINUTES` | `15` | 복약 알림 유예 |
| `SCENARIO_ACTIVE_TIMEOUT` | `10m` | 활성 시나리오 강제 타임아웃 |
| `AI_CONVERSATION_START_TIMEOUT` | `10s` | AI 시작 확인 |
| `AI_CONVERSATION_MAX_DURATION` | `5m` | 대화 최대 지속 |
| `WALK_FOLLOW_START_ACK_TIMEOUT` / `WALK_FOLLOW_STOP_ACK_TIMEOUT` | `10s` | 산책 FOLLOW 시작/종료 확인 |
| `WALK_MAX_DURATION` | `2h` | 산책 최대 지속 |

#### (5) 채널 인증

| 변수 | 비고 |
| --- | --- |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | 필수 · **비밀** |
| `ROBOT_SHARED_SECRET` | 로봇 채널 인증. **비우면 필터가 전부 통과시킵니다** · **비밀** |
| `OPERATOR_SHARED_SECRET` | 운영자 콘솔 인증 (필수, `:?` 선언) · **비밀** |
| `OPERATOR_ID` | 감사 로그용 서버 소유 식별자 |

#### (6) 이미지 태그 (배포 스크립트가 자동 갱신)

`BACKEND_IMAGE_TAG`, `OPERATOR_CONSOLE_IMAGE_TAG`, `WAYPOINT_EDITOR_IMAGE_TAG`, `FRONTEND_IMAGE_TAG`
→ `scripts/deploy/deploy-production.sh`가 배포 시 **커밋 SHA 12자리**로 덮어씁니다. 수동 편집 불필요.

#### (7) 도메인 / 인증서 / 호스트 경로

| 변수 | 값 |
| --- | --- |
| `BOMI_DOMAIN` | `i15e102.p.ssafy.io` |
| `LETSENCRYPT_EMAIL` | 팀 관리 이메일 |
| `CERTBOT_CONF_DIR` | `/home/ubuntu/bomi/data/certbot/conf` |
| `CERTBOT_WEBROOT_DIR` | `/home/ubuntu/bomi/data/certbot/www` |
| `NGINX_OPERATOR_CONSOLE_HTPASSWD_FILE` | Basic 인증 파일 경로 |
| `NGINX_WAYPOINT_EDITOR_HTPASSWD_FILE` | Basic 인증 파일 경로 |
| `JENKINS_HOME_DIR` | `/home/ubuntu/bomi/data/jenkins` |
| `DOCKER_GID` | 호스트 `docker` 그룹 GID (`getent group docker` 로 확인) |

### 2.5 ★ 컨테이너 환경변수 주입 규칙 (반복 발생한 함정)

Docker는 **호스트 환경변수를 컨테이너로 자동 전달하지 않습니다.**
`compose.prod.yml`의 `environment:` 블록에 명시하지 않은 변수는 `production.env`에 적어도
**컨테이너 안에 존재하지 않습니다.** 이 경우 `application.yml`의 기본값(`${EMBEDDING_ENABLED:false}` 등)이
조용히 이겨서 기능이 영원히 꺼진 채로 뜹니다.

**새 환경변수를 추가할 때는 반드시 세 곳을 함께 고칩니다.**

1. `infra/production.env.example` (형식·기본값 문서화)
2. `infra/compose.prod.yml`의 해당 서비스 `environment:` (컨테이너로 전달)
3. `backend/src/main/resources/application.yml` (프로퍼티 바인딩)

> 회귀 방지 테스트: `ComposeEnvironmentPassthroughTest`가 `../infra/compose.prod.yml`과
> `../infra/production.env.example`을 읽어 누락을 검사합니다. `build.gradle`에서 두 파일을
> `inputs.files`로 등록해 UP-TO-DATE 오판정을 막고 있습니다.

---

## 3. 배포 절차

### 3.1 서버 디렉터리 구조 (EC2)

```text
/home/ubuntu/bomi/
├── deploy/source/            # Git 클론 (Jenkins 워크스페이스와 별개 가능)
├── secrets/production.env    # 권한 600, Git 미추적
├── data/
│   ├── postgres/             # PostgreSQL 영속 데이터 (권한 750)
│   ├── certbot/conf/         # Let's Encrypt 인증서 (권한 700)
│   ├── certbot/www/          # ACME webroot (권한 755)
│   └── jenkins/              # Jenkins home
├── backup/                   # pg_dump 백업 (권한 700)
└── logs/                     # certbot 갱신 로그 등
```

### 3.2 최초 1회 세팅

```bash
# 1) 디렉터리 생성
sudo install -d -o ubuntu -g ubuntu -m 750 /home/ubuntu/bomi/data/postgres
sudo install -d -o ubuntu -g ubuntu -m 700 /home/ubuntu/bomi/secrets
sudo install -d -o ubuntu -g ubuntu -m 700 /home/ubuntu/bomi/backup
sudo install -d -o ubuntu -g ubuntu -m 700 /home/ubuntu/bomi/data/certbot/conf
sudo install -d -o ubuntu -g ubuntu -m 755 /home/ubuntu/bomi/data/certbot/www

# 2) 환경변수 파일
cp infra/production.env.example /home/ubuntu/bomi/secrets/production.env
chmod 600 /home/ubuntu/bomi/secrets/production.env
openssl rand -hex 32          # POSTGRES_PASSWORD 값 생성
nano /home/ubuntu/bomi/secrets/production.env   # 편집기로 입력 (셸 히스토리에 남기지 않음)

# 3) 방화벽
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw status numbered

# 4) 설정 검증 (컨테이너 실행 없음)
docker compose --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml config --quiet
```

**TLS 인증서 최초 발급** — 인증서가 없으면 HTTPS Nginx가 기동하지 못하므로 임시 HTTP Nginx를 먼저 띄웁니다.

```bash
# 임시 Nginx (ACME challenge 경로 제공)
docker compose --profile tools --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml up -d nginx-bootstrap
curl --fail http://localhost/nginx-health

# 인증서 발급
BOMI_DOMAIN=$(awk -F= '$1=="BOMI_DOMAIN"{print $2}' /home/ubuntu/bomi/secrets/production.env)
BOMI_LETSENCRYPT_EMAIL=$(awk -F= '$1=="LETSENCRYPT_EMAIL"{print $2}' /home/ubuntu/bomi/secrets/production.env)
docker compose --profile tools --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml run --rm certbot certonly \
  --webroot --webroot-path /var/www/certbot \
  --domain "$BOMI_DOMAIN" --email "$BOMI_LETSENCRYPT_EMAIL" \
  --agree-tos --no-eff-email --non-interactive

# 임시 Nginx 제거
docker compose --profile tools --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml rm -sf nginx-bootstrap
```

**인증서 갱신 cron 등록**

```bash
chmod 750 scripts/deploy/renew-certificates.sh
(
  crontab -l 2>/dev/null | grep -v 'renew-certificates.sh'
  echo '17 3 * * * /home/ubuntu/bomi/deploy/source/scripts/deploy/renew-certificates.sh >> /home/ubuntu/bomi/logs/certbot-renew.log 2>&1'
) | crontab -
```

### 3.3 자동 배포 (Jenkins)

`Jenkinsfile` 파이프라인 — GitLab push 트리거

| 단계 | 동작 |
| --- | --- |
| Checkout | `checkout scm` (기본 checkout 비활성, `customWorkspace` 사용) |
| Validate | `bash -n scripts/deploy/deploy-production.sh` + `docker compose config --quiet` |
| Build | `docker compose build backend operator-console waypoint-editor frontend` |
| Deploy | `scripts/deploy/deploy-production.sh` 실행 |

- 동시 빌드 금지(`disableConcurrentBuilds`), 타임아웃 20분
- 환경: `BOMI_ENV_FILE=/home/ubuntu/bomi/secrets/production.env`, `BOMI_COMPOSE_FILE=infra/compose.prod.yml`

### 3.4 수동 배포

```bash
cd /home/ubuntu/bomi/deploy/source
git pull                       # working tree가 clean해야 함
BOMI_SOURCE_DIR="$PWD" \
BOMI_ENV_FILE=/home/ubuntu/bomi/secrets/production.env \
  scripts/deploy/deploy-production.sh
```

**`deploy-production.sh`가 수행하는 순서**

1. `git`·`docker`·`curl` 존재 확인, 저장소/환경파일/compose 파일 가독 확인
2. **`git status --porcelain`이 비어 있는지 확인** — 더러우면 즉시 실패
3. `git rev-parse --short=12 HEAD`로 SHA 추출 → 4개 `*_IMAGE_TAG`를 `production.env`에 기록
4. `compose config --quiet` 검증
5. `postgres` 기동 및 healthy 대기 (60초)
6. `backend`, `operator-console`, `waypoint-editor`, `frontend` 이미지 빌드
7. 애플리케이션 컨테이너 기동 및 healthy 대기 (120초)
8. `nginx` `--force-recreate`로 재생성 (60초)
9. 6개 컨테이너 health 상태를 `docker inspect`로 개별 확인
10. HTTPS 검증
    - `https://$BOMI_DOMAIN/` → 200
    - `https://$BOMI_DOMAIN/api/health` → 200
    - `https://$BOMI_DOMAIN/operator-console/` → **401 이어야 함**
    - `https://$BOMI_DOMAIN/waypoint-editor/` → **401 이어야 함**

### 3.5 MQTT 스택 (별도 Compose)

MQTT 브로커는 `infra/compose.mqtt.prod.yml`로 분리 운영되며, `bomi-mqtt-net`을
**external network**로 공유합니다. 절차는 `scripts/deploy/MQTT_DEPLOYMENT.md`,
검증은 `scripts/deploy/verify-mqtt.sh`를 참고합니다.

> ⚠️ `compose.prod.yml`의 backend가 `bomi-mqtt-net`(external)에 붙으므로,
> **MQTT 스택을 먼저 올려 네트워크를 생성해야** 애플리케이션 배포가 성공합니다.

### 3.6 배포 후 확인

```bash
docker compose --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml ps

curl -I  http://i15e102.p.ssafy.io/api/health          # → 301/308 HTTPS 리다이렉트
curl --fail --silent https://i15e102.p.ssafy.io/api/health   # → UP
curl -I  https://i15e102.p.ssafy.io/actuator/health    # → 404 (외부 차단 정상)

docker port bomi-backend                                # 출력 없어야 정상
docker port bomi-postgres                               # 출력 없어야 정상
sudo ss -lnt | grep ':5432' || echo 'OK: DB not published'
```

---

## 4. 배포 시 특이사항

### 4.1 반드시 지켜야 할 것

| # | 항목 | 내용 |
| --- | --- | --- |
| 1 | **작업 트리 clean 필수** | `deploy-production.sh`는 `git status --porcelain`이 비어 있지 않으면 배포를 중단합니다. 서버에서 파일을 직접 고치면 배포가 막힙니다. |
| 2 | **`docker compose down -v` 운영 금지** | PostgreSQL 데이터 디렉터리 삭제와 함께 **운영 환경에서 금지**입니다. |
| 3 | **VITE_ 변수는 빌드 타임 고정** | 2.3절 참고. 런타임 변경 불가, 두 플래그는 항상 함께. |
| 4 | **compose `environment:` 누락** | 2.5절 참고. 세 곳(예제·compose·application.yml)을 함께 수정. |
| 5 | **MQTT 네트워크 선행** | `bomi-mqtt-net`이 external이므로 MQTT 스택을 먼저 기동. |
| 6 | **인증서 선행** | 인증서 없이는 HTTPS Nginx가 기동 불가. `nginx-bootstrap` 프로파일로 먼저 발급. |

### 4.2 네트워크 격리 구조

| 네트워크 | 속성 | 소속 서비스 |
| --- | --- | --- |
| `bomi-backend-net` | **internal: true** (외부 도달 불가) | postgres, qdrant, backend, operator-console |
| `bomi-proxy-net` | 일반 | backend, operator-console, waypoint-editor, frontend, jenkins, nginx |
| `bomi-mqtt-net` | **external** | backend (+ MQTT 스택) |

- PostgreSQL 5432, Qdrant 6333/6334, Backend 8080은 **호스트에 공개하지 않습니다.**
- Qdrant는 기본 인증이 없어 포트를 열면 개인 기억 벡터와 payload가 그대로 노출됩니다.
- `operator-console`은 `127.0.0.1:8501`로만 바인딩되며(루프백 전용), 외부 접근은 Nginx Basic 인증을 거칩니다.

### 4.3 기동 순서 의존성 (healthcheck)

```text
postgres (healthy) ─┐
                    ├─→ backend (healthy) ─→ operator-console (healthy) ─┐
qdrant   (healthy) ─┘                                                     ├─→ nginx
                       waypoint-editor (healthy) ────────────────────────┤
                       frontend        (healthy) ────────────────────────┘
```

- backend는 qdrant에 대해 `service_started`가 아닌 **`service_healthy`**를 요구합니다.
  Qdrant는 기동 직후 컬렉션 적재 중이라 그 사이 요청이 실패하고, 첫 기동에서만 조용히
  실패해 의미 검색이 영구히 꺼지는 문제가 있었습니다.
- Qdrant 이미지에는 `curl`·`wget`·`nc`가 없고 `/bin/sh`가 dash라 `/dev/tcp`를 못 씁니다.
  그래서 healthcheck가 `CMD-SHELL`이 아니라 **`bash -c`를 직접 호출**합니다. 이 줄을 건드리면
  healthcheck가 항상 실패하고 `depends_on`이 배포를 멈춥니다.

### 4.4 DB 마이그레이션 (Flyway)

- Backend 기동 시 **자동 실행**됩니다. 별도 명령이 필요 없습니다.
- 마이그레이션 위치: `backend/src/main/resources/db/migration/` (현재 `V1` ~ `V20`)
- pgvector 확장은 컨테이너 최초 초기화 시 `infra/docker/postgres/init/001-enable-vector.sql`이
  `CREATE EXTENSION`을 수행합니다. **덤프 복원 시에는 이 스크립트가 실행되지 않으므로
  복원 전에 확장을 먼저 생성해야 합니다.**
- 가이드: `docs/database/flyway-guide.md`

### 4.5 과금 API 기본 OFF 정책

`EMBEDDING_ENABLED`, `EMBEDDING_SYNC_ENABLED`, `LLM_ENABLED`는 **기본 `false`**입니다.
잔액이 시연까지 버텨야 하므로 명시적으로만 켭니다.

- 최초 1회: `EMBEDDING_SYNC_ENABLED=true`로 컬렉션을 채운 뒤 **다시 끕니다.**
- 시연 중에는 질의 임베딩만 돌고 백로그를 훑지 않아야 합니다.
- 키가 없으면 조용히 실패하지 않고 **기동 로그에 `embedding OFF`가 남습니다.**

### 4.6 현재 임시 보류 상태인 설정

| 항목 | 상태 |
| --- | --- |
| 가디언웹 Basic 인증 (`NGINX_GUARDIAN_HTPASSWD_FILE`) | 2026-08-05 임시 보류. `compose.prod.yml`의 마운트 줄과 `bomi.conf`의 `auth_basic` 두 줄이 주석 처리됨. 되살리려면 **양쪽을 함께** 해제 |
| 로컬 Mosquitto 익명 접속 | `infra/docker/mosquitto/config/mosquitto.conf`는 **로컬 개발 전용**. 운영은 `docker/mosquitto/production/` (인증 + ACL) 사용 |
| `ENTRANCE_DIRECTION_RESOLUTION_ENABLED` | 기본 `false`. PIR 설치 위치에 따라 귀가가 외출로 뒤집힐 수 있어 리허설 후 결정 |

### 4.7 백업

```bash
umask 077
docker compose --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "/home/ubuntu/bomi/backup/bomi-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

> Qdrant 볼륨은 **백업 대상이 아닙니다.** 파생 인덱스이므로 유실 시 `embedding_status`
> 부기 컬럼으로 전량 재색인됩니다.

---

## 5. 주요 계정 및 프로퍼티가 정의된 파일 목록

### 5.1 Git으로 관리되는 파일 (형식·기본값만, 실제 비밀값 없음)

| 파일 | 정의 내용 |
| --- | --- |
| `.env.example` | 로컬 개발 전체 환경변수 형식 |
| `backend/.env.example` | Backend 로컬 환경변수 |
| `frontend/.env.example` | Frontend 빌드 타임 변수 (`VITE_*`) |
| `infra/production.env.example` | **운영 환경변수 전체 형식** (39개 변수) |
| `infra/mqtt.env.example` | MQTT 스택 환경변수 형식 |
| `iot/raspberry-pi/zigbee2mqtt/.env.example` | Zigbee2MQTT 환경변수 |
| `iot/raspberry-pi/translator/config/device.example.yaml` | 센서 장치 매핑 설정 |
| `iot/raspberry-pi/translator/config/dht11.env.example` | DHT11 수집기 설정 |
| `robot/ai_chat/.env.example` | AI 대화 파이프라인 설정 (STT/TTS/LLM 등) |
| `backend/src/main/resources/application.yml` | **Spring 프로퍼티 정의 및 기본값** (모든 `${ENV:default}` 바인딩의 출처) |
| `backend/src/main/resources/application-docs.yml` | 문서 확인용 `docs` 프로파일 (H2) |
| `infra/compose.prod.yml` | 운영 서비스·이미지 태그·컨테이너 환경변수 주입 |
| `infra/compose.mqtt.prod.yml` | MQTT 브로커 스택 |
| `docker-compose.yml` | 로컬 개발 스택 (PostgreSQL, Mosquitto) |
| `infra/nginx/conf.d/bomi.conf` | 라우팅·TLS·Basic 인증 설정 |
| `infra/docker/mosquitto/production/mosquitto.conf` | 운영 브로커 설정 |
| `infra/docker/mosquitto/production/acl` | **MQTT 토픽 접근 제어 목록** |
| `infra/docker/postgres/init/001-enable-vector.sql` | pgvector 확장 생성 |
| `backend/src/main/resources/db/migration/V*.sql` | DB 스키마 정의 (V1~V20) |
| `Jenkinsfile` | CI 파이프라인 및 환경 경로 |
| `iot/jetson/bomi-robot.service` | Jetson systemd 유닛 |
| `iot/raspberry-pi/translator/config/bomi-dht11.service` | Pi systemd 유닛 |

### 5.2 Git에 없는 파일 (실제 계정·비밀값 — 서버/장치에만 존재)

| 경로 | 위치 | 포함 정보 | 권한 |
| --- | --- | --- | --- |
| `/home/ubuntu/bomi/secrets/production.env` | EC2 | **DB 비밀번호, MQTT 계정, Upstage/Gemini/Qdrant API 키, ROBOT/OPERATOR 공유 비밀키, 도메인·이메일** | 600 |
| `/home/ubuntu/bomi/secrets/mqtt.env` | EC2 | MQTT 브로커 계정 | 600 |
| `$NGINX_OPERATOR_CONSOLE_HTPASSWD_FILE` | EC2 | 운영자 콘솔 Basic 인증 | 600 |
| `$NGINX_WAYPOINT_EDITOR_HTPASSWD_FILE` | EC2 | 웨이포인트 편집기 Basic 인증 | 600 |
| `/home/ubuntu/bomi/data/certbot/conf/` | EC2 | Let's Encrypt 개인키·인증서 | 700 |
| Jenkins Credentials | Jenkins | GitLab 접근 토큰 | — |
| `.env`, `backend/.env`, `frontend/.env` | 개발자 로컬 | 로컬 개발 값 | — |
| `robot/ai_chat/.env` | 로봇/Jetson | AI 대화 API 키 | — |
| `iot/raspberry-pi/translator/config/device.yaml` | Raspberry Pi | 실제 센서 장치 매핑 | — |
| `iot/raspberry-pi/translator/config/dht11.env` | Raspberry Pi | DHT11 수집기 값 | — |

> **원칙**: 실제 비밀번호·API 키·MQTT 인증정보·SSH 개인키·장치 네트워크 설정은
> 커밋하지 않습니다. 저장소에는 `*.example` 파일만 둡니다.
> `docker compose config` 결과에는 비밀값이 렌더링되므로 로그나 메신저에 공유하지 않습니다.

### 5.3 ERD / 컬럼 정의서

| 문서 | 경로 |
| --- | --- |
| ERD | `docs/database/mvp-erd.md` |
| 컬럼 정의서 | `docs/database/column-definition/BOMI_컬럼정의서.xlsx` |
| 스냅샷 CSV | `docs/database/column-definition/snapshots/` (tables, columns, constraints, indexes, code-values, jsonb-fields, vector-fields, interface-mappings) |
| Flyway 가이드 | `docs/database/flyway-guide.md` |

---

## 6. 클론 후 로컬 재현 순서 (요약)

```bash
# 0) 클론
git clone <GitLab URL> && cd S15P11E102

# 1) 환경변수
cp .env.example .env                    # Windows: Copy-Item .env.example .env
#   .env 의 change-me 값을 로컬 값으로 수정

# 2) PostgreSQL(pgvector) + Mosquitto
docker compose up -d
docker compose ps
#   PostgreSQL 127.0.0.1:5432 / MQTT localhost:1883 / MQTT WS localhost:9001

# 3) Backend  (Flyway 마이그레이션 자동 실행)
cd backend && ./gradlew bootRun         # Windows: gradlew.bat bootRun
curl http://localhost:8080/api/health

# 4) Frontend
cd frontend
cp .env.example .env
npm install
npm run dev                             # http://localhost:5173

# 5) Robot (Ubuntu 22.04 / ROS 2 Humble 장비에서)
cd robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash

# 6) IoT 번역기 (Raspberry Pi 5)
pip install -r iot/raspberry-pi/translator/requirements.txt
cp iot/raspberry-pi/translator/config/device.example.yaml \
   iot/raspberry-pi/translator/config/device.yaml
python iot/raspberry-pi/translator/main.py
```

- 배포 Swagger UI: `https://i15e102.p.ssafy.io/swagger-ui.html`
- 종료: `docker compose down` (데이터까지 제거는 `down -v` — **로컬에서만**)

---

## 부록 A. 최종 검증 체크리스트

> **머지 완료 후 실제 값을 확인해 아래를 채우고, `[확인 필요]` 표시를 지웁니다.**

| # | 확인 항목 | 명령 | 결과 |
| --- | --- | --- | --- |
| 1 | 기준 커밋 SHA | `git rev-parse --short=12 HEAD` | |
| 2 | IntelliJ 버전 | `Help → About` | |
| 3 | VS Code 버전 | `code --version` | |
| 4 | 서버 OS | `lsb_release -a` | |
| 5 | 서버 Docker | `docker --version` | |
| 6 | 서버 Docker Compose | `docker compose version` | |
| 7 | 로컬 Node | `node -v` (빌드는 컨테이너 24.18.0 고정) | |
| 8 | 로컬 JDK | `java -version` | |
| 9 | Gradle | `cd backend && ./gradlew --version` (Wrapper 8.14.2) | |
| 10 | PostgreSQL / pgvector | `docker exec bomi-postgres psql -U bomi -d bomi -tAc "SELECT version(); SELECT extversion FROM pg_extension WHERE extname='vector';"` | |
| 11 | 로봇 ROS 배포판 | `printenv ROS_DISTRO` (humble) | |
| 12 | 로봇 Python | `python3 --version` | |
| 13 | Flyway 최종 버전 | `ls backend/src/main/resources/db/migration | tail -1` | |
| 14 | `production.env` 변수 누락 | `docker compose --env-file ... -f infra/compose.prod.yml config --quiet` | |
| 15 | 배포 스모크 | `curl https://i15e102.p.ssafy.io/api/health` | |

## 부록 B. 문서 링크

| 문서 | 경로 |
| --- | --- |
| 인프라 운영 상세 | `infra/README.md` |
| 배포 개요 | `scripts/deploy/DEPLOYMENT.md` |
| MQTT 배포 | `scripts/deploy/MQTT_DEPLOYMENT.md` |
| RAG 운영 | `infra/RAG_OPERATIONS.md` |
| Jenkins 설정 | `infra/jenkins/README.md` |
| Frontend 배포 | `infra/FRONTEND.md` |
| API 명세 | `docs/api/README.md` |
| MQTT 토픽 규약 | `docs/mqtt/topic-convention.md` |
| 시스템 개요 | `docs/architecture/system-overview.md` |
| 로봇 셋업 | `robot/README.md`, `robot/docs/ros2-humble-setup.md` |
| IoT 게이트웨이 | `iot/raspberry-pi/README.md` |
