# BOMI

BOMI는 사용자의 일상에 지속적으로 개입해 대화·행동·안전 데이터를 축적하고, 이상 징후 발생 시 현장으로 이동해 대응하는 AIoT 기반 개인 종합 돌봄 로봇 프로젝트입니다.

## 1차 목표

첫 시연은 **현관 센서 감지 → 로봇 현관 이동 → 맞춤 인사 → STT/TTS 대화 → 대화·귀가 기록 → 보호자 대시보드 확인** 흐름을 끝까지 연결하는 데 집중합니다. 준비되지 않은 센서·로봇·AI 기능은 Mock으로 대체할 수 있습니다.

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Frontend | React, Vite, JavaScript, npm |
| Backend | Spring Boot, Java 17, Gradle, JPA, WebSocket, MQTT |
| Database / Broker | MySQL 8, Eclipse Mosquitto 2 |
| Robot | Ubuntu 22.04, ROS 2 Humble, Python 3.10, Nav2, SLAM Toolbox |
| Hardware | Jetson Orin Nano, Raspberry Pi 5, LiDAR, Camera, IMU |

## 모노레포 구조

```text
frontend/   보호자용 React 대시보드
backend/    Spring Boot 중앙 백엔드
robot/      ROS 2 워크스페이스와 로봇 제어 설정
iot/        Raspberry Pi, Jetson, 센서, MQTT 코드
docs/       아키텍처, API, MQTT, 시나리오, DB, 하드웨어 문서
infra/      Docker, Mosquitto, Jenkins, Nginx 설정
scripts/    개발 환경 설정·실행·배포 보조 도구
.github/    PR 및 Issue 템플릿
```

## 빠른 시작

### 1. 환경변수

```bash
cp .env.example .env
```

`.env`의 `change-me` 값을 로컬 개발용 값으로 변경합니다. PowerShell에서는 `Copy-Item .env.example .env`를 사용합니다.

### 2. MySQL과 Mosquitto

```bash
docker compose up -d
docker compose ps
```

- MySQL: `localhost:3306`
- MQTT: `localhost:1883`
- MQTT WebSocket: `localhost:9001`

종료는 `docker compose down`, 데이터까지 제거하려는 경우에만 `docker compose down -v`를 사용합니다.

### 3. Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

기본 주소는 `http://localhost:5173`이며 프로덕션 빌드는 `npm run build`입니다.

### 4. Backend

Docker 서비스가 준비된 뒤 실행합니다.

```bash
cd backend
./gradlew bootRun
```

Windows에서는 `gradlew.bat bootRun`을 사용합니다. 상태 확인은 `GET http://localhost:8080/api/health`입니다.

### 5. Robot / IoT

Robot은 Ubuntu 22.04 및 ROS 2 Humble 환경에서 `robot/README.md`를 따릅니다. IoT Python 의존성은 대상 장치에서 `pip install -r iot/requirements.txt`로 설치합니다.

## 디렉터리 책임

- Backend는 전체 이벤트·시나리오·기록·상태·알림을 중앙 관리합니다.
- 장애물 회피, Nav2 경로 추종, 영상·음성 스트리밍은 지연을 줄이기 위해 로봇/AI 내부에서 처리하고 결과 이벤트만 백엔드로 보냅니다.
- Frontend는 REST 조회와 WebSocket 실시간 상태 표시를 담당합니다.
- IoT는 센서 데이터를 정규화하고 MQTT 이벤트로 발행합니다.

## 브랜치 전략

- `main`: 시연·배포 가능한 안정 버전, PR로만 병합
- `develop`: 기능 통합 브랜치
- `feature/*`: 기능별 작업 브랜치(예: `feature/be-door-event`)

## 민감정보 관리

실제 비밀번호, API Key, MQTT 인증정보, SSH 개인키, 장치 네트워크 설정은 커밋하지 않습니다. `.env`, `application-local.yml`, `application-secret.yml`, 실제 `config/*.yaml`은 `.gitignore` 대상이며 저장소에는 `.env.example` 및 `*.example.yaml`만 둡니다. Mosquitto의 익명 접속 설정은 로컬 개발 전용입니다.

## 현재 구현 범위

- 포함: 초기 React 화면, 백엔드 Health API, MySQL/Mosquitto Compose, 환경변수 기반 설정, ROS 2/IoT 디렉터리, 핵심 문서와 GitHub 템플릿
- 미포함: 실제 센서 제어, MQTT 구독·발행 비즈니스 흐름, DB 도메인 모델, 로봇 자율주행, STT/TTS, AI 대화, WebSocket 화면 연동, 운영 보안·배포 설정

