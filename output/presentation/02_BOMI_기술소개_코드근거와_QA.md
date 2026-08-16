# BOMI 기술 소개 - 코드 근거, 검증 범위, Q&A

> 이 문서는 발표자와 개발 담당자가 보관하는 증거 문서입니다.  
> PPT 담당자에게는 `01_BOMI_기술소개_PPT_담당자용_콘티.md`를 먼저 전달하고, 기술 확인이 필요할 때만 이 문서를 함께 전달합니다.

## 1. 분석 기준

작업트리에 사용자 수정이 많이 남아 있어 브랜치를 직접 전환하지 않았습니다. 대신 동일한 결과를 얻을 수 있도록 `git ls-tree`, `git show`, `git grep`으로 각 원격 브랜치의 Git 객체를 직접 읽었습니다.

| 영역 | 분석 ref | 커밋 | 기준 시각 |
|---|---|---|---|
| AI Chat / AI Vision | `origin/ai-develop` | `79ce1e20fda6ae4ac2728d573f2ac93f83137232` | 2026-08-05 15:28 KST |
| Backend / Infra | `origin/be-develop` | `c1af86a2f83b43e895366c46bc18b7cb9cdb87f5` | 2026-08-05 16:17 KST |
| Guardian Frontend | `origin/fe-develop` | `99157dda61e28f2c253de832425e831313caf1c1` | 2026-08-02 23:15 KST |
| Robot / ROS2 | `origin/robot-develop` | `1ace7063205b18f544bb4222a64b7c406bf39bc7` | 2026-08-04 17:00 KST |

정적 파일 집계는 다음과 같습니다. 이는 코드 규모를 설명하는 자료이지, 테스트 통과 수치가 아닙니다.

| 범위 | 파일 | 소스 파일 | 테스트 파일 | 문서 |
|---|---:|---:|---:|---:|
| AI Chat | 173 | 148 | 66 | 19 |
| AI Vision | 52 | 27 | 12 | 13 |
| Backend | 335 | 297 | 75 | 2 |
| Frontend | 47 | 37 | 0 | 1 |
| Robot | 163 | 84 | 38 | 27 |

## 2. 한 문장 기술 포지셔닝

**BOMI는 로봇이 무엇을 할지뿐 아니라, 무엇을 말하고 무엇을 믿고 무엇을 공유할지까지 관리합니다.**

본편에 쓸 기술 이야기는 다음 다섯 개면 충분합니다.

| 기술 이야기 | 관객이 기억할 문장 | 실제 코드 강점 |
|---|---|---|
| 먼저 찾아감 | 신호는 여러 번 와도 돌봄은 한 번만 | 시나리오 충돌·중복·시간 초과 관리 |
| 말할 때를 고름 | 모든 알림 대신 지금 필요한 한마디만 | 능동 발화 게이트·우선순위·침묵 |
| 위험을 먼저 봄 | 위험 가능성은 답변보다 먼저 | LLM 이전 안전 분기·확인 질문·outbox |
| 기억의 선을 지킴 | 대화는 기억하되 약은 다시 묻기 | 후보·동의·위험도·권한 필터·사람 확인 |
| 헷갈리면 멈춤 | 한 명이 확실하고 길이 안전할 때만 이동 | 비전 상태 머신·LiDAR 우선·하위 watchdog |

---

# 3. 기술 이야기별 코드 근거

## A. 먼저 찾아가는 돌봄 - 시나리오 오케스트레이션

### 왜 필요한가

센서, 복약 시간, 호출이 동시에 들어올 수 있고 MQTT QoS 1은 이벤트가 한 번 이상 전달될 수 있습니다. 로봇 한 대가 행동 두 개를 동시에 시작하면 이동·대화가 충돌하거나 다음 돌봄이 영원히 막힐 수 있습니다.

### 코드에서 확인한 구현

- `ScenarioStartGuard`가 어르신 단위로 활성 시나리오와 쿨다운을 확인합니다.
- DB 부분 유니크 인덱스가 활성 시나리오 중복을 최종 방어합니다.
- `Scenario`가 이동·대화·복귀·종료 상태 전이를 소유합니다.
- `scenarioId`, `commandId`, `robotId`를 대조해 늦거나 잘못 붙은 결과를 거절합니다.
- AI 대화 시작, 전체 대화, 활성 시나리오에 별도 timeout/watchdog가 있습니다.
- 웨이크워드 호출은 영속 receipt로 재시작 뒤 중복도 막도록 구현됐습니다.

### 주요 경로

```text
origin/be-develop:backend/src/main/java/com/ssafy/bomi/scenario/application/ScenarioStartGuard.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/scenario/domain/Scenario.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/scenario/application/HomecomingOrchestrator.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/scenario/application/WellnessCheckOrchestrator.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/scenario/application/MedicationReminderScheduler.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/scenario/application/WakeWordCallOrchestrator.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/scenario/application/AiConversationTimeoutWatchdog.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/scenario/application/ScenarioTimeoutWatchdog.java
origin/be-develop:backend/src/main/resources/db/migration/V15__add_wake_word_call_runtime.sql
```

### 검증과 한계

- 코드와 자동 테스트가 존재합니다.
- `HomecomingE2eTest`는 H2와 기록형 publisher로 귀가·온습도·복약·호출 논리를 검증합니다.
- 로컬 E2E 문서는 실제 PostgreSQL과 MQTT broker 왕복을 기록했지만 센서·로봇·AI는 대역입니다.
- 일반 MQTT eventId dedup은 10분 인메모리이므로 모든 이벤트의 영속 exactly-once를 보장하지 않습니다.
- 귀가·안부·복약·호출 시나리오는 구현됐지만 `낙상`, `산책`은 본 구현 범위가 아닙니다.
- Backend는 대화 종료 뒤 `DEFAULT` 복귀 명령을 만들지만 Robot bridge의 waypoint lookup은 현재 `DEFAULT`를 미지원합니다. 전체 자동 복귀 성공은 별도 통합 검증 전까지 주장하지 않습니다.

## B. 말할 때를 고르는 AI - 능동 발화 게이트

### 왜 필요한가

복약, 일정, 현관 인사, 안부가 각각 직접 말하면 로봇이 새벽에 말하거나 몇 분 간격으로 같은 말을 반복할 수 있습니다.

### 코드에서 확인한 구현

- 네 기능은 직접 말하지 않고 `SpeechProposal`을 제출합니다.
- 만료되거나 이미 완료된 제안은 폐기합니다.
- 아직 말할 시점이 아닌 제안은 연기합니다.
- 어르신의 로컬 시간대와 자정을 넘는 quiet hours를 처리합니다.
- 최근 발화와의 cooldown을 적용합니다.
- 중요도 정책에 따라 한 건만 선택하고 나머지는 다음 tick에 남깁니다.
- 살아남은 제안이 없으면 그래프가 `END`로 종료합니다. 즉 침묵이 정상 결과입니다.
- 모든 출력은 response shaper를 지나 최대 문장 수가 제한됩니다.

### 주요 경로

```text
origin/ai-develop:robot/ai_chat/src/bomi_ai_chat/graph/gate.py
origin/ai-develop:robot/ai_chat/src/bomi_ai_chat/graph/build.py
origin/ai-develop:robot/ai_chat/src/bomi_ai_chat/graph/output.py
origin/ai-develop:robot/ai_chat/src/bomi_ai_chat/policy.py
origin/ai-develop:robot/ai_chat/src/bomi_ai_chat/jobs/ticks.py
origin/ai-develop:robot/ai_chat/src/bomi_ai_chat/state.py
```

### 검증과 한계

- 우선순위·유효시간·quiet hours·cooldown·대기열은 구현됐습니다.
- `audio_ctx.someone_speaking`, `rest_state` 인터페이스는 있지만 실제 감지 생산 연결을 확인하지 못했습니다.
- 따라서 `TV와 대화를 구분`, `쉬는 것을 보고 말하지 않음`은 발표 금지입니다.
- 출력 계층에는 비동기 재생과 중단을 위한 구조가 있지만 현재 웨이크워드 대화 루프는 재생이 끝난 뒤 다시 듣도록 의도적으로 기다립니다. `언제든 자연스럽게 끼어들기`라고 말하면 안 됩니다.

## C. 위험을 먼저 보는 AI - 안전 분기와 알림 보존

### 왜 필요한가

위험 가능성이 있는 문장을 일반 LLM 답변으로 넘기면 표현과 지연이 흔들릴 수 있습니다. 네트워크가 끊겼을 때 보호자 알림이 사라져도 안 됩니다.

### 코드에서 확인한 구현

- `safety_triage`가 intent 분류와 LLM 처리보다 먼저 실행됩니다.
- 자해 위험 표현은 별도 경로로 즉시 T1 처리합니다.
- 급성 신체 표현은 한 문장 확인 질문을 거칩니다.
- 명시적 요청 또는 확인 뒤 위험이 남으면 일반 대화를 우회합니다.
- 확인 뒤 무응답은 local runtime state와 silence tick이 이어받습니다.
- T1 알림은 전송 전에 로컬 SQLite outbox에 저장됩니다.
- 네트워크 실패 시 retry하고, T1은 단순 시도 횟수로 폐기하지 않습니다.

### 주요 경로

```text
origin/ai-develop:robot/ai_chat/src/bomi_ai_chat/graph/triage.py
origin/ai-develop:robot/ai_chat/src/bomi_ai_chat/graph/build.py
origin/ai-develop:robot/ai_chat/src/bomi_ai_chat/localstore/outbox.py
origin/ai-develop:robot/ai_chat/src/bomi_ai_chat/jobs/ticks.py
origin/ai-develop:robot/ai_chat/src/bomi_ai_chat/policy.py
origin/be-develop:backend/src/main/java/com/ssafy/bomi/care/application/GuardianAlertService.java
```

### 검증과 한계

- 별도 안전 경로와 outbox 설계는 구현됐습니다.
- 의료 진단, 임상 검증된 응급 탐지, 119 자동 신고 기능은 아닙니다.
- 자해 표현 목록은 코드상 전문가 검토 완료 상태가 아닙니다.
- 실제 고령자·현장 소음 환경 성능 수치는 없습니다.
- 보호자 웹에는 WebSocket/push 구현이 없습니다. 현재 화면은 REST 조회입니다.

## D. 기억의 선을 지키는 AI - 후보, 동의, 위험도, 권위 있는 검색

### 왜 필요한가

“주말에 손자가 온다”와 “아침 약 이제 안 먹는다”를 똑같이 저장하면 STT나 AI 분류 오류가 실제 돌봄 사실이 됩니다. 의미 검색은 `혈압약`과 `혈당약`을 가깝게 볼 수도 있습니다.

### 코드에서 확인한 쓰기 경로

- 대화에서 추출된 정보는 `FactCandidate`로 먼저 들어옵니다.
- conversation/senior/sourceMessage 소유권과 중복을 검증합니다.
- 개인화·건강·일정 동의를 종류별로 확인합니다.
- 먼저 꺼내면 안 되는 인물과 하루 50건 상한을 검사합니다.
- MEMORY와 일정처럼 되돌리기 쉬운 정보는 제한적으로 반영합니다.
- CARE_RECORD의 복약·건강·알 수 없는 타입은 확인 대기로 둡니다.
- 재질의는 한 번에 한 필드만 묻고, 복창 확인 뒤 확정합니다.
- 보호자 웹은 `확정 / 수정 / 거절 / 다시 질문 / 되돌리기`를 지원합니다.

### 코드에서 확인한 읽기 경로

- 정확해야 하는 프로필·건강·복약·일정은 PostgreSQL 정확 조회를 사용합니다.
- 기억도 PostgreSQL에서 senior, lifecycle, rejection, visibility를 먼저 필터합니다.
- Qdrant는 기억 본문이 아니라 `id + similarity score`만 반환합니다.
- Qdrant 점수는 허용된 기억의 순위를 바꾸는 데만 사용합니다.
- Qdrant/임베딩이 꺼지면 키워드·중요도·최근성·최근 사용 감점으로 계속 동작합니다.
- 보호자 context에는 raw message와 conversation summary가 제외됩니다.
- PRIVATE memory는 보호자 대시보드에서 제외됩니다.

### 주요 경로

```text
origin/be-develop:backend/src/main/java/com/ssafy/bomi/fact/application/ConversationFactIntakeService.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/fact/application/FactRiskPolicy.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/fact/application/RobotClarificationService.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/fact/application/FactMaterializer.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/fact/domain/FactCandidate.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/context/application/ConversationContextService.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/context/application/QdrantMemorySearch.java
origin/be-develop:backend/src/main/java/com/ssafy/bomi/memory/repository/MemoryRepository.java
origin/fe-develop:frontend/src/pages/ConfirmationRequestsPage.tsx
origin/fe-develop:frontend/src/pages/ConversationPreferencesPage.tsx
origin/fe-develop:frontend/src/services/bomiService.ts
```

### 검증과 한계

- 권한 필터를 벡터 결과가 우회하지 못하도록 하는 전용 테스트가 존재합니다.
- `모든 건강 발화가 자동으로 확인됨`은 과장입니다. AI가 targetDomain과 factType을 올바르게 분류한다는 계약에 의존합니다.
- MEMORY 기본 visibility는 PRIVATE지만 verification은 UNVERIFIED입니다.
- 확인 요청 undo snapshot은 인메모리라 서버 재시작 뒤 유지되지 않습니다.
- raw message 만료 시각은 기록하지만 실제 삭제 배치는 확인되지 않았습니다.
- Gemini 요약·embedding·Qdrant는 기본 OFF일 수 있습니다.

## E. 헷갈리면 멈추는 로봇 - 비전, LiDAR, Pico

### AI Vision에서 확인한 구현

- YOLO11n과 ByteTrack으로 사람 탐지·프레임 간 추적을 수행합니다.
- `not_detected`, `tracking`, `temporarily_lost`, `multiple_pending`, `multiple_persons`, `single_recovery` 6상태를 관리합니다.
- 정상 `tracking`에서만 대표 Track ID와 위치를 제공합니다.
- 여러 명, 일시 누락, 한 명 복귀 안정화 중에는 대표 대상을 주지 않습니다.
- 방향 결과는 `turn_left`, `turn_right`, `move_forward`, `stop` 네 가지입니다.
- 뒤로 가는 명령은 만들지 않습니다.
- 불확실하거나 값이 잘못되면 항상 `stop`입니다.

### ROS2에서 확인한 구현

- 카메라 → AI Vision → UDP → `/vision/follow_result` → `person_follower` 경로가 있습니다.
- 사람 추적 상태와 LiDAR 거리를 함께 읽어 최종 `Twist`를 만듭니다.
- 여러 사람, 비전 timeout, LiDAR timeout, 잘못된 scan, 가까운 장애물은 STOP입니다.
- 사람 접근 정지와 재출발 거리를 다르게 둬 경계에서 떨리는 동작을 줄입니다.
- 기본 출력은 `/cmd_vel_follow`여서 명시적으로 연결하기 전에는 로봇을 움직이지 않습니다.
- Pico driver는 `/cmd_vel`을 바퀴 속도로 바꾸고 시리얼로 전송하며 `/odom`, `/imu`를 발행합니다.
- ROS cmd_vel timeout과 Pico watchdog이 별도로 존재합니다.

### 주요 경로

```text
origin/ai-develop:robot/ai_vision/src/bomi_vision/tracking.py
origin/ai-develop:robot/ai_vision/src/bomi_vision/follow.py
origin/ai-develop:robot/ai_vision/src/bomi_vision/application.py
origin/ai-develop:robot/ai_vision/src/bomi_vision/adapters/tracking.py
origin/robot-develop:robot/ros2_ws/src/core/core/vision_udp_bridge.py
origin/robot-develop:robot/ros2_ws/src/core/core/follow_state_machine.py
origin/robot-develop:robot/ros2_ws/src/core/core/person_following_controller.py
origin/robot-develop:robot/ros2_ws/src/core/core/person_follower.py
origin/robot-develop:robot/ros2_ws/src/core/core/pico_driver.py
origin/robot-develop:robot/ros2_ws/src/core/core/pico_protocol.py
origin/robot-develop:robot/ros2_ws/src/core/config/person_following.yaml
```

### 문서에 기록된 실제 검증 범위

- 실물 모터 전진·후진·좌우회전·제자리회전
- Jetson↔Pico protocol과 ROS2 driver
- 실제 카메라 한 명 추적, 두 명 정지, 한 명 복귀 안정화
- 실제 X4 LiDAR 약 11 Hz와 장애물 안전 정지 우선
- 최종 이동은 Gazebo 로봇
- 관련 core pytest 42개 통과 기록

### 한계

- 실제 모터 사람 추종은 검증 범위 밖입니다.
- 실물 Nav2 자율주행 결과는 없습니다.
- Robot 브랜치의 `robot/ai_vision`은 초기 scaffold이고, 실제 YOLO/ByteTrack 구현은 `origin/ai-develop`에 있습니다.
- Nav2와 사람 추종이 동시에 `/cmd_vel`을 발행하면 충돌하므로 하나만 실행해야 합니다.
- 자동 모드 중재기는 확인되지 않았습니다.
- 유효 tread 정밀 보정과 실제 전류·퓨즈·저전압 기준이 남아 있습니다.

---

# 4. 보호자 웹 기능 근거

## 실제 구현 화면

| 경로 | 구현 기능 | 발표에서 쓸 장면 |
|---|---|---|
| `/dashboard` | 어르신·로봇·환경·이벤트, 일정, 복약, 확인 요청, 최근 기억 | 서비스 전체 요약 |
| `/elder/profile` | 기본 정보, 온보딩, 동의, 말하기 속도·음량 | 동의 기반 설정 |
| `/conversation-preferences` | 기억 검색·종류 필터, 출처·확정·공유 범위 | 기억과 공개 범위 |
| `/confirmation-requests` | 근거, 현재/제안 값, 확정·수정·재질문·거절·되돌리기 | 핵심 기술 데모 |
| `/medications` | 복약 CRUD, 알림, 오늘 응답 | 생활 돌봄 |
| `/schedules` | 일정 CRUD, 사전 알림, 사후 안부 질문 | 선제적 돌봄 |

주요 경로:

```text
origin/fe-develop:frontend/src/App.tsx
origin/fe-develop:frontend/src/pages/DashboardPage.tsx
origin/fe-develop:frontend/src/pages/ElderProfilePage.tsx
origin/fe-develop:frontend/src/pages/ConversationPreferencesPage.tsx
origin/fe-develop:frontend/src/pages/ConfirmationRequestsPage.tsx
origin/fe-develop:frontend/src/pages/HealthPage.tsx
origin/fe-develop:frontend/src/pages/SchedulesPage.tsx
origin/fe-develop:frontend/src/services/bomiService.ts
origin/fe-develop:frontend/src/state/BomiContext.tsx
```

중요 상태:

- 기본은 `VITE_USE_MOCK_API=true`입니다.
- 실 API 모드에는 dashboard, profile, memory, confirmation, schedule, medication 연결이 있습니다.
- WebSocket, SSE, polling 구현은 없습니다.
- 첫 로드, 수동 새로고침, 쓰기 성공 뒤 재조회 방식입니다.
- FE 자동 테스트 파일은 없습니다. `typecheck`와 `build` script만 정의돼 있습니다.
- `Mock Data` 배너가 보이는 화면을 실데이터처럼 촬영하면 안 됩니다.

---

# 5. 테스트 숫자를 발표에 쓰는 기준

| 영역 | 저장소에 남은 기록 | 이번 분석에서 실행했는가 | 발표 표기 |
|---|---|---|---|
| AI Chat | `docs/carebot/검증 절차.md`에 `633 passed + All checks passed` 체크 기준 | 아니오 | 발표 직전 재실행 후에만 `자동 테스트 633개` |
| AI Vision | 완료 문서에 `171개 단위·통합 테스트`, mypy 17파일 기록 | 아니오 | 최신 코드 재실행 후에만 사용 |
| Backend | Test class 74개, `@Test` 460개 정적 집계 | 아니오 | `460개 통과` 금지 |
| Robot person following | README에 `42 passed`와 실센서→Gazebo 검증 기록 | 아니오 | `문서상 42 passed 기록`, 가능하면 재실행 |
| Frontend | 테스트 파일 없음 | 해당 없음 | 테스트 수치 사용 금지 |

정확도, 응답시간, FPS, 인식률은 저장소에서 실측 근거를 확인하지 못했습니다. 발표 전에 측정하지 않았다면 숫자를 만들지 않습니다.

---

# 6. 예상 질문과 정직한 답변

## “실물로 어디까지 됐나요?”

> 실물에서는 기본 모터 구동과 Pico 통신·정지를 확인했습니다. 사람 추종은 실제 카메라와 실제 LiDAR 입력을 사용하되 최종 이동은 Gazebo에서 검증했습니다. 실물 자율주행과 실물 사람 추종은 발표 전 별도 통합 검증 범위입니다.

## “왜 상태 머신이 필요한가요?”

> 로봇은 한 대라 행동 둘을 동시에 할 수 없고, 늦게 도착한 결과가 다른 돌봄 작업에 붙으면 안 됩니다. 그래서 시작·이동·대화·복귀·시간 초과를 명시적인 상태로 관리합니다.

## “Qdrant가 꺼지면 기억을 못 하나요?”

> 아닙니다. Qdrant는 정답 저장소가 아니라 허용된 기억의 순위를 돕는 파생 인덱스입니다. 꺼지면 PostgreSQL 권한 필터와 키워드·중요도·최근성 기반 순위로 대화가 계속됩니다.

## “대화가 보호자에게 전부 보이나요?”

> 아닙니다. 현재 코드상 보호자 문맥에는 원문 발화와 대화 요약이 빠지고, PRIVATE 기억도 대시보드에서 제외됩니다. 다만 운영 로그인 계층은 아직 완성 상태가 아니므로 보안이 완성됐다고 주장하지는 않습니다.

## “BOMI가 응급상황을 진단하나요?”

> 진단하지 않습니다. 위험 가능성이 있는 표현을 일반 대화보다 먼저 확인하고, 필요할 때 사람에게 연결하도록 별도 경로를 둔 것입니다.

## “알림이 실시간으로 오나요?”

> 현재 보호자 웹은 REST 조회 방식입니다. 백엔드에 알림 기록과 라우팅은 있지만 WebSocket이나 push provider는 아직 없습니다. 시연에서는 새로고침을 포함합니다.

## “왜 모든 말을 바로 기억하지 않나요?”

> 오인식이나 잘못된 AI 추출이 복약·건강 사실이 되면 위험하기 때문입니다. 먼저 후보로 보관하고 동의와 위험도에 따라 자동 반영, 사람 확인, 거절 경로를 나눕니다.

## “두 사람이 보이면 어떻게 하나요?”

> 임의로 한 명을 고르지 않습니다. 다중 인물 확인 상태부터 대표 대상을 내주지 않고 STOP을 반환합니다. 다시 한 명이 돼도 안정화 구간을 지난 뒤 추적을 재개합니다.

## “AI가 전진하라고 했는데 장애물이 있으면요?”

> 카메라가 만든 것은 희망 방향일 뿐입니다. ROS2의 사람 추종 노드가 LiDAR 거리와 입력 시간 초과를 다시 확인하며, 안전 조건이 멈추라고 하면 최종 속도는 0입니다.

---

# 7. 메인 장표에서 빼고 부록에 둘 기술 스택

기술명은 질문을 받았을 때만 아래처럼 답합니다.

| 층 | 실제 기술 |
|---|---|
| Guardian Web | React, TypeScript, Vite |
| Backend | Java 17, Spring Boot 3.4, JPA, Flyway, PostgreSQL |
| Messaging | MQTT QoS 1, Spring Integration MQTT, Mosquitto |
| Memory Search | Qdrant, Upstage embedding 선택 연결, PostgreSQL source of truth |
| AI Chat | Python, LangGraph, RTZR STT, Gemini 2.5 Flash Lite, Typecast TTS, openWakeWord |
| AI Vision | YOLO11n, ByteTrack, OpenCV |
| Robot | ROS2 Humble, Nav2, AMCL, SLAM Toolbox, YDLIDAR X4 Pro |
| Motor Control | Raspberry Pi Pico H, encoder feedback, serial protocol, watchdog |
| Deployment | Docker, Nginx, TLS, read-only containers, MQTT ACL |

이 표를 본편 첫 장에 넣으면 관객은 기술명만 듣고 사용자 가치를 놓치므로 부록에 둡니다.

---

# 8. 발표 금지 과장 전체 목록

1. 실물 Nav2 자율주행 완료
2. 실제 모터 사람 추종 완료
3. 낙상·수면·감정·얼굴 인식 완료
4. 실기기 전체 E2E 완료
5. 응급상황 정확 탐지 또는 의료 진단
6. 119 자동 신고
7. 실시간 보호자 push/WebSocket
8. 가디언 로그인과 완전한 인증 완료
9. 모든 MQTT 메시지 exactly-once
10. 모든 건강 발화 자동 확인
11. 모든 대화 영구 기억
12. 원문 30일 뒤 자동 삭제
13. 의미 검색과 대화 요약이 항상 켜짐
14. 복약 대답이 자동으로 `MEDICATION_TAKEN`에 반영
15. 대시보드가 건강 위험을 자동 판정
16. 언제든 자연스럽게 barge-in 가능
17. 임상 검증된 정확도, 2초 응답, Jetson FPS

발표 파트의 신뢰를 지키는 가장 좋은 방법은 **구현 범위를 숨기는 것이 아니라, 실물·실센서·시뮬레이션을 정확히 구분해 보여주는 것**입니다.
