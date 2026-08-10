# BOMI 포팅 매뉴얼 ④ — 시연 시나리오

> 시연 순서에 따른 **화면별·실행별 상세 설명**입니다.
> `[리허설 후 확정]` 표시는 마지막 리허설에서 실측해 채웁니다.

- 시연 URL: <https://i15e102.p.ssafy.io>
- 기준 커밋: `[머지 후 기입]` / 작성일: `2026-08-__`
- 총 소요: `[리허설 후 확정]` 분

---

## 0. 시연 개요

BOMI는 **AIoT 기반 개인 종합 돌봄 로봇**입니다. 시연은 어르신의 하루를 따라가며
**5대 시나리오**가 순서대로 동작하는 것을 보이고, 그 결과가 보호자 웹에 쌓이는 것으로 마칩니다.

| # | 시나리오 | 내부 타입 | 시작 트리거 | 대화 방식 |
| --- | --- | --- | --- | --- |
| 1 | **현관 인사** | `HOMECOMING` | 문 열림(`DOOR_OPENED`) + PIR | `START_CONVERSATION` |
| 2 | **호출** | `WAKE_WORD_CALL` | "보미야" 웨이크워드 | AI가 자체 시작 |
| 3 | **복약 알림** | `MEDICATION_REMINDER` | 복약 일정 시각 | `START_CONVERSATION` |
| 4 | **온습도 안부** | `WELLNESS_CHECK` | DHT11 임계값 초과 | `START_CONVERSATION` |
| 5 | **산책** | `WALK` | 대화 중 요청 | `FOLLOW_START` / `FOLLOW_STOP` |

### 등장 화면

| 화면 | 접근 | 용도 |
| --- | --- | --- |
| **보호자 웹** | `https://i15e102.p.ssafy.io` | 시연 시작·마무리 |
| **로봇 본체** | 현장 | 이동·대화·표정 |
| **운영자 콘솔** | `/operator-console/` (Basic 인증) | ★ 장애 시 복구 전용 — 시연 중 화면에 띄우지 않음 |
| **웨이포인트 편집기** | `/waypoint-editor/` (Basic 인증) | 사전 준비용 |

### 역할 분담 `[리허설 후 확정]`

| 역할 | 담당 | 하는 일 |
| --- | --- | --- |
| 발표 | | 설명 진행, 보호자 웹 조작 |
| 어르신 역 | | 로봇과 대화, 문 열기 |
| 로봇 감시 | | 물리 E-stop 대기, 이동 경로 확보 |
| 콘솔 대기 | | 장애 시 취소·복구 API 실행 |

---

## 1. 사전 준비 (시연 30분 전)

> 여기서 하나라도 걸리면 시연 중에는 못 고칩니다. 순서대로 전부 확인합니다.

### 1-1. 서버

```bash
ssh -i <키>.pem ubuntu@i15e102.p.ssafy.io
docker compose --env-file /home/ubuntu/bomi/secrets/production.env \
  -f infra/compose.prod.yml ps
```

- [ ] `bomi-postgres`, `bomi-qdrant`, `bomi-backend`, `bomi-frontend`, `bomi-nginx` 전부 **healthy**
- [ ] `curl --fail https://i15e102.p.ssafy.io/api/health` → `UP`
- [ ] MQTT 브로커 확인: `scripts/deploy/verify-mqtt.sh`

### 1-2. 로봇 (Jetson)

- [ ] 전원·배터리 잔량 확인
- [ ] `printenv ROS_DISTRO` → `humble`
- [ ] Nav2 기동, 지도 로드, **AMCL 초기 위치가 실제 위치와 일치**
- [ ] `robot/ai_chat/.env` 의 `ROBOT_DEVICE_ID` 설정됨 (비어 있으면 `UNKNOWN_ROBOT` 으로 **조용히** 차단)
- [ ] `MQTT_ENABLED=true`, `MQTT_BROKER_URL` 이 운영 브로커(`mqtts://...:8883`)를 가리킴
- [ ] `BACKEND_SHARED_SECRET` 이 서버의 `ROBOT_SHARED_SECRET` 과 **같은 값**
- [ ] 마이크/스피커 장치 인덱스 확인 (`AUDIO_MODE=robot` 이면 장치 지정 필수)
- [ ] 웨이크워드 모델 `models/bomiya.onnx` 존재, `WAKEWORD_ENABLED=1`
- [ ] **실물 로봇과 `robot-sim` 을 같은 `robotId` 로 동시에 띄우지 않았는지 확인**

### 1-3. IoT (Raspberry Pi)

- [ ] Zigbee2MQTT 기동, 문 센서(SNZB-04P)·PIR(SNZB-03P) 연결 확인
- [ ] DHT11 수집기 동작: `mosquitto_sub -t 'bomi/v1/iot/+/events' -v` 로 이벤트 흐름 확인
- [ ] `SENSOR_ID` 가 백엔드 `application.yml` 의 `bomi.observation.ambient-sensor-to-senior` 등록값과 **정확히 일치**

### 1-4. 데이터 상태

```bash
exec/scripts/dump-db.sh --reset --no-verify   # reset만 적용하고 싶으면 아래 직접 실행
# 또는
docker exec -i bomi-postgres psql -U bomi -d bomi < scripts/dev/reset-demo.sql
```

- [ ] 로봇 mode 가 `SAFE_STOP` 이 **아님**
- [ ] 활성 시나리오 **0건** (`ACTIVE_SCENARIO_EXISTS` 로 차단되면 시연이 시작조차 안 됨)
- [ ] 시드 데이터(김순자) 존재

### 1-5. 물리 환경

- [ ] 로봇 이동 경로에 사람·장애물 없음
- [ ] 물리 E-stop 즉시 조작 가능한 사람 배치
- [ ] 조명 확보 (비전 인식)
- [ ] 소음 통제 (STT 정확도)
- [ ] 웨이포인트 `ENTRANCE` / `LIVING_ROOM` / `DEFAULT` 위치 실측 확인

### 1-6. 발표 PC

- [ ] 보호자 웹을 **브라우저 탭 1**에 미리 열어 둠 (`https://i15e102.p.ssafy.io`)
- [ ] 운영자 콘솔을 **탭 2**에 로그인해 두되 **화면 공유에는 띄우지 않음**
- [ ] 터미널 1개 대기 (취소·복구 API용, `OPERATOR_SHARED_SECRET` 환경변수 export 완료)

---

## 2. 시연 순서

### 장면 0 — 서비스 소개 (보호자 웹)

| 항목 | 내용 |
| --- | --- |
| 화면 | 랜딩 페이지 `/` |
| 조작 | 브라우저 주소창에 `https://i15e102.p.ssafy.io` 입력 |
| 소요 | `[리허설 후 확정]` |

**설명 포인트** — "보호자가 보는 화면입니다. 어르신 곁의 로봇이 관찰한 것이 여기로 모입니다."

**조작:** 랜딩 화면에서 **시작 버튼** 클릭 → `/dashboard` (사이드바 `돌봄 보기 > 오늘`)

**오늘 화면에서 짚을 것**
- 상단바 왼쪽 **`돌봄 대상`** 셀렉터 — 현재 어르신 이름 표시
- 상단바 오른쪽 **`마지막 관찰`** 시각 + 새로고침 버튼
- 상단바 우측 **알림 배지** — `확인할 일 N건`

> 📷 **스크린샷 ①** — 오늘(대시보드) 초기 화면 `[리허설 때 촬영]`

---

### 장면 1 — 현관 인사 (`HOMECOMING`)

> 첫 시연이자 프로젝트의 1차 목표 흐름입니다.

**흐름**

```text
문 열림(SNZB-04P) + PIR(SNZB-03P)
   → IoT 번역기 → bomi/v1/iot/{sourceId}/events (DOOR_OPENED)
   → Backend: scenario(HOMECOMING) 생성
   → MQTT NAVIGATE(ENTRANCE) → 로봇 현관 이동
   → NAVIGATION_RESULT(ARRIVED)
   → START_CONVERSATION → AI 대화
   → CONVERSATION_ENDED → NAVIGATE(DEFAULT) 복귀
   → scenario COMPLETED
```

| 단계 | 조작 위치 | 관찰 지점 | 예상 소요 |
| --- | --- | --- | --- |
| 1 | **현관문을 실제로 연다** | 로봇이 현관 방향으로 출발 | `[확정]` |
| 2 | (자동) | 로봇 도착 후 정지·표정 변화 | `[확정]` |
| 3 | 어르신 역이 로봇 앞에 선다 | 로봇이 인사 발화 | `[확정]` |
| 4 | 어르신 역이 대답한다 | STT → 응답 | `[확정]` |
| 5 | 대화 종료 | 로봇이 기본 위치로 복귀 | `[확정]` |

**설명 포인트**
- "센서가 감지한 것은 '문이 열렸다'뿐입니다. 방향 판정과 시나리오 결정은 백엔드가 합니다."
- "이동 중 장애물 회피와 경로 추종은 지연을 줄이려고 로봇 안에서 처리하고, 결과 이벤트만 백엔드로 보냅니다."

**주의**
- `ENTRANCE_DIRECTION_RESOLUTION_ENABLED` 가 `true` 이면 PIR 설치 위치에 따라 **귀가가 외출로 뒤집힐 수 있습니다.** 리허설에서 확인한 값으로 고정합니다 → 실제 사용값: `[리허설 후 확정]`
- 문을 여러 번 여닫으면 `ENTRANCE_REVERSAL_WINDOW`(30초) 안에서 판정이 뒤집힙니다. **한 번만** 엽니다.

> 📷 **스크린샷 ②** — 로봇 현관 이동 중 `[리허설 때 촬영]`
> 📷 **스크린샷 ③** — 대화 중 로봇 표정 `[리허설 때 촬영]`

---

### 장면 2 — 호출 (`WAKE_WORD_CALL`)

**흐름** — 다른 시나리오와 달리 **AI가 스스로 대화를 시작**합니다. 백엔드는 `NAVIGATE(LIVING_ROOM)` 만 관리합니다.

| 단계 | 조작 | 관찰 지점 |
| --- | --- | --- |
| 1 | 어르신 역이 **"보미야"** 라고 부른다 | 로봇이 소리 방향으로 회전 |
| 2 | (자동) | 짧은 응답 후 거실로 이동 |
| 3 | 어르신 역이 말을 건다 | 대화 진행 |

**설명 포인트**
- "웨이크워드는 **로봇 안에서 로컬 모델(openWakeWord)** 로 감지합니다. 상시 녹음을 서버로 보내지 않습니다."
- "소리 방향은 MQTT 계약에 실을 수 없어서, '언제 시작할지'는 MQTT로, '어디로 돌지'는 UDP로 나눠 보냅니다."

**주의**
- `WAKE_MOVEMENT_WAIT_ENABLED` 가 `true` 여야 이동 후 본 대화가 열립니다. `false` 면 제자리에서 대화합니다 → 실제 사용값: `[리허설 후 확정]`
- `BEAM_FIX_ENABLED=1` 이면 방향값이 항상 정면이라 **전체 한 바퀴 탐색**으로 넘어갑니다(느릴 뿐 성립).

> 📷 **스크린샷 ④** — 호출 후 회전·이동 `[리허설 때 촬영]`

---

### 장면 3 — 복약 알림 (`MEDICATION_REMINDER`)

| 단계 | 조작 위치 | 관찰 지점 |
| --- | --- | --- |
| 1 | 보호자 웹 사이드바 **`세부 관리 > 복약 관리`** (`/medications`) | 등록된 복약 일정 확인 |
| 2 | 일정 시각 도달 (또는 시연용 일정 등록) | 로봇이 이동 후 복약 안내 |
| 3 | 어르신 역이 "먹었어" 라고 답한다 | `MEDICATION_TAKEN` 기록 |
| 4 | 보호자 웹 **`돌봄 보기 > 오늘`** 새로고침 | 복약 상태 갱신 확인 |

**설명 포인트** — "복약은 알림으로 끝나지 않고 **복용 여부까지 대화로 확인**해서 기록합니다."

**주의** — `MEDICATION_GRACE_MINUTES`(기본 15분) 유예가 있습니다. 시연 시각을 맞추기 어려우면 이 값을 조정합니다(컨테이너 재시작만으로 반영) → 시연용 값: `[리허설 후 확정]`

> 📷 **스크린샷 ⑤** — 복약 관리 화면 `[리허설 때 촬영]`

---

### 장면 4 — 온습도 안부 (`WELLNESS_CHECK`)

| 단계 | 조작 | 관찰 지점 |
| --- | --- | --- |
| 1 | DHT11 주변 온도를 올린다 (또는 임계값을 낮춘다) | 30초 주기로 이벤트 발행 |
| 2 | (자동) | 임계값 초과 시 로봇이 안부 대화 시작 |

**설명 포인트** — "센서 값 하나하나가 로봇을 움직이지 않습니다. 백엔드가 **최신 관측값만 저장**해 두었다가, 안부 시나리오를 열 때 대화 재료로 씁니다."

**주의**
- 임계값: `WELLNESS_TEMP_THRESHOLD`(30.0°C) / `WELLNESS_HUMIDITY_THRESHOLD`(80.0%)
- 쿨다운 `WELLNESS_COOLDOWN_MINUTES`(30분) — **리허설에서 한 번 발동시키면 30분 안에 다시 안 됩니다.** 시연 직전 리허설은 이 시나리오를 빼거나 쿨다운을 줄입니다 → 시연용 값: `[리허설 후 확정]`
- 귀가 연속 시연에서는 로봇의 독립 이동을 막기 위해 `WELLNESS_SCENARIO_ENABLED=false` 로 두고 AI가 관측값만 대화에 쓰는 구성도 가능합니다 → 실제 구성: `[리허설 후 확정]`

---

### 장면 5 — 산책 (`WALK`)

| 단계 | 조작 | 관찰 지점 |
| --- | --- | --- |
| 1 | 대화 중 "산책 가자" 요청 | `FOLLOW_START` 발행 |
| 2 | 어르신 역이 천천히 걷는다 | 로봇이 일정 거리 유지하며 추종, 근접 시 정지 |
| 3 | "그만" 요청 | `FOLLOW_STOP` |

**설명 포인트** — "추종은 카메라의 사람 추적 결과와 LiDAR 거리를 함께 씁니다. 너무 가까워지면 멈춥니다."

**주의**
- ★ **Nav2 자율주행과 추종을 동시에 실행하지 않습니다.** 둘 다 `/cmd_vel` 에 발행해 명령이 충돌합니다.
- `WALK_MAX_DURATION`(2h), `WALK_FOLLOW_START_ACK_TIMEOUT`(10s)
- 실물 시험이므로 **이동 범위에 사람·장애물이 없는지** 다시 확인합니다.

> 📷 **스크린샷 ⑥** — 사용자 추종 중 `[리허설 때 촬영]`

---

### 장면 6 — 보호자 웹에서 결과 확인 (마무리)

앞의 시나리오들이 실제로 기록으로 남았음을 보입니다. **사이드바 순서대로** 이동합니다.

| # | 사이드바 위치 | 경로 | 보여줄 것 |
| --- | --- | --- | --- |
| 1 | `돌봄 보기 > 오늘` | `/dashboard` | 오늘 하루 요약, 마지막 관찰 시각 갱신 |
| 2 | `돌봄 보기 > 생활 기록` | `/records` | 방금 나눈 대화·귀가 기록이 올라온 것 |
| 3 | `돌봄 보기 > 확인할 일` | `/confirmation-requests` | 대화에서 추출된 **사실 후보**의 보호자 확인 요청 |
| 4 | `돌봄 보기 > 돌봄 계획` | `/care-plan` | 확인된 사실이 반영된 돌봄 계획 |
| 5 | `돌봄 보기 > 보미와 집` | `/bomi-home` | 로봇·집 상태 |
| 6 | `세부 관리 > 공유된 생활 정보` | `/conversation-preferences` | 어르신이 공유에 동의한 정보 범위 |

**설명 포인트 (프로젝트의 핵심 주장)**
- "대화에서 나온 이야기를 **바로 기록으로 확정하지 않습니다.** 먼저 `확인할 일`로 보내 보호자가 확인한 것만 반영합니다."
- "음성 원본과 모델 원응답은 저장하지 않습니다. 텍스트 발화만 남깁니다."

> 📷 **스크린샷 ⑦** — 생활 기록 `[리허설 때 촬영]`
> 📷 **스크린샷 ⑧** — 확인할 일 `[리허설 때 촬영]`

---

## 3. 장애 대응 (Plan B)

> 시연 중에는 **원인을 찾지 않습니다.** 아래 표대로 복구하고 다음 장면으로 넘어갑니다.

| 증상 | 즉시 판단 | 대응 |
| --- | --- | --- |
| 로봇이 안 움직임 | 활성 시나리오 걸림 | §3-1 취소 API |
| 로봇 mode 가 `SAFE_STOP` | 정지 상태 잠김 | §3-2 복구 API |
| `ACTIVE_SCENARIO_EXISTS` 로 시작 안 됨 | 앞 시나리오 미종료 | §3-1 → §3-2 순서로 |
| STT 가 못 알아들음 | 소음/거리 | 더 가까이서, 천천히, 또렷하게 재시도 |
| 대화가 안 끝남 | AI 이벤트 유실 | `SCENARIO_ACTIVE_TIMEOUT`(10분) 대기 또는 §3-1 |
| 보호자 웹이 빈 화면 | 프런트 빌드 플래그 문제 | 시연 중 복구 불가 — 스크린샷으로 대체 |
| 로봇이 사람에게 접근 | — | **물리 E-stop 즉시** |

### 3-1. 활성 내비게이션 취소

> **먼저 로봇 주변과 이동 경로의 물리적 안전을 확인합니다.**

```bash
curl -X POST \
  "https://i15e102.p.ssafy.io/api/v1/operator/robots/bomi-AA001/active-scenario-cancellations" \
  -H "X-Operator-Shared-Secret: $OPERATOR_SHARED_SECRET" \
  -H 'Content-Type: application/json' \
  -d '{"physicalSafetyConfirmed": true, "reason": "시연 중 이동 시나리오 정지"}'
```

성공 시 백엔드가 한 트랜잭션으로 처리합니다: MQTT `CANCEL` 발행 예약 → Scenario `CANCELLED` →
Robot mode `SAFE_STOP` → 감사 테이블 기록.

- 활성 시나리오가 없으면 `NO_OP_NO_ACTIVE_SCENARIO`
- 활성 시나리오가 여러 개거나 내비게이션 명령이 없으면 **409** (자동으로 상태를 바꾸지 않음)

### 3-2. `SAFE_STOP` → `IDLE` 복구

> **Jetson/Nav2 에서 로봇이 실제로 멈춘 것을 눈으로 확인한 뒤** 호출합니다.

```bash
curl -X POST \
  "https://i15e102.p.ssafy.io/api/v1/operator/robots/bomi-AA001/mode-recoveries" \
  -H "X-Operator-Shared-Secret: $OPERATOR_SHARED_SECRET" \
  -H 'Content-Type: application/json' \
  -d '{"physicalSafetyConfirmed": true, "reason": "CANCEL 처리 및 Robot 정지 확인"}'
```

- 취소 API와 복구 API를 합치지 않은 이유: **MQTT 취소 발행과 실제 모터 정지 사이에 시간 차**가 있습니다.
- 활성 Scenario 가 남아 있으면 거절됩니다. **SQL 로 강제 복구하지 않습니다.**
- 서버의 `OPERATOR_SHARED_SECRET` 또는 `OPERATOR_ID` 가 비어 있으면 fail-closed 로 거절됩니다.

### 3-3. 절대 하지 말 것

- ❌ 실물 로봇 동작 중 `scripts/dev/publish_event.py` 나 수동 MQTT publish 로 이동 시나리오 시작
- ❌ Swagger `Try it out` 으로 이동 명령 발행
- ❌ 실물 Bridge 와 `robot-sim` 을 같은 `robotId` 로 동시 실행
- ❌ DB 를 직접 UPDATE 해서 mode 강제 변경

---

## 4. 리허설 체크리스트

> 시연 전 **최소 1회 전체 리허설**을 돌리고 아래를 채웁니다. 채운 뒤 DB 덤프를 뜹니다(③번 문서 §2).

| # | 항목 | 결과 |
| --- | --- | --- |
| 1 | 장면 0~6 전체 소요 시간 | ___ 분 |
| 2 | 장면별 소요 시간 (표의 `[확정]` 칸) | |
| 3 | 스크린샷 ①~⑧ 촬영 | |
| 4 | `ENTRANCE_DIRECTION_RESOLUTION_ENABLED` 최종값 | |
| 5 | `WAKE_MOVEMENT_WAIT_ENABLED` 최종값 | |
| 6 | `WELLNESS_*` 임계값·쿨다운 최종값 | |
| 7 | `MEDICATION_GRACE_MINUTES` 최종값 | |
| 8 | 웨이포인트 `ENTRANCE`/`LIVING_ROOM`/`DEFAULT` 도달 확인 | |
| 9 | 5개 시나리오 전부 1회 이상 성공 | |
| 10 | 역할 분담 확정 (§0) | |
| 11 | 취소·복구 API 1회 실전 연습 | |
| 12 | **리허설 후 `reset-demo.sql` 적용** | |
| 13 | 시연 상태에서 DB 덤프 생성·검증 | |

---

## 5. 관련 문서

| 문서 | 경로 |
| --- | --- |
| 빌드·배포 | `exec/01-build-deploy.md` |
| 외부 서비스 | `exec/02-external-services.md` |
| DB 덤프 | `exec/03-database-dump.md` |
| **5대 시나리오 MQTT 계약 v1 (최종 기준)** | `docs/mqtt/scenario-contract-v1.md` |
| 귀가 환영 시나리오 상세 | `docs/scenario/homecoming-welcome.md` |
| Robot·IoT 통합 가이드 | `docs/scenario/integration-guide.md` |
| 운영자 내비게이션 취소 | `docs/scenario/operator-navigation-cancellation.md` |
| MQTT 토픽 규약 | `docs/mqtt/topic-convention.md` |
| 로컬 E2E 리포트 | `docs/scenario/local-e2e-report.md` |
