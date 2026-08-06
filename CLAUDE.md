# CLAUDE.md — 5개 시나리오 실기 통합 (hotfix/scenario-integration)

**이 문서는 통합·시연 스프린트의 헌법이다.** 목표: 며칠 안에 실제 젯슨에서 5분 시연.
대화 런타임의 설계 헌법(구 CLAUDE.md)은 [`임시보류_claude.md`](임시보류_claude.md) 로 보관했고,
그 문서의 **§4(어휘)·§21(주석 표준)·§25~29(작업 규칙)는 지금도 그대로 유효하다** — 이 문서는
그 위에 얹히는 통합 스프린트 계약이다. 스프린트가 끝나면 이 문서의 내용은 각 라인 문서로
환류되고 구 CLAUDE.md 가 복귀한다.

---

## 0. 지금 어디에 있는가

- **2026-08-06 11:47, 4개 라인(ai/be/fe/robot)이 `main` 에 통합**됐다. 처음으로 모든 코드가
  한 트리에 있다.
- 이 브랜치(`hotfix/scenario-integration`)는 `origin/main` 에서 분기했다. 이름의 `hotfix` 는
  장식이다 — "main 에서 갈라진 통합 작업 브랜치"라는 뜻 이상이 아니다.
- 시연 범위: **보미야 호출(필수)·현관 인사·복약 알림·온습도 안부.** 산책은 보류(스텁 회신만).
- 실행 계획 원본: `C:\Users\SSAFY\.claude\plans\vectorized-humming-kernighan.md` (조사 근거 포함).

### 배포와 CI/CD — 왜 이 브랜치가 안전한가

이번 작업이 건드리는 기계는 전부 CI/CD 밖이다. 젯슨(ai_chat·bridge·ros2_ws)과 파이(iot)는
**수동 배포**다 (`ci/Jenkinsfile.{ai,robot}` 둘 다 "deployment is disabled; verification only").
라인별 CI/CD 로 배포되는 것은 EC2 의 backend/frontend 뿐인데 이번 작업은 백엔드를 건드리지
않는다. 따라서:

- **젯슨·파이는 이 브랜치를 직접 checkout 해서 실행한다.**
- 백엔드 수정이 불가피해지면 그 커밋만 be-develop 티켓 브랜치로 cherry-pick 한다.
- **커밋 규율: 한 커밋은 한 라인의 경로만 건드린다.** (`robot/ai_chat/**` ↔ `ros2_ws/**`·`iot/**`
  를 한 커밋에 섞지 않는다.) 시연 후 라인별 cherry-pick 환류를 기계적으로 만드는 유일한 규칙이다.

---

## 1. 시나리오 배선도 (완성 후 모습)

| 시나리오 | 트리거 | 흐름 |
|---|---|---|
| 보미야 호출 | ai_chat 웨이크워드 | `WAKE_WORD_DETECTED` 발행 + 짧은 첫 응답 → BE `NAVIGATE(LIVING_ROOM)` → 이동 중 침묵 → v1 `ARRIVED` 회신 → **사람 접근(로봇 내부, 백엔드 무관)** → 본 대화 |
| 현관 인사 | IoT `DOOR_OPENED` | `NAVIGATE(ENTRANCE)` → ARRIVED → `START_CONVERSATION(HOMECOMING_GREETING)` → STARTED/ENDED → `NAVIGATE(DEFAULT)` → 완료 |
| 복약 알림 | BE 스케줄러 (1분 폴링, 창=[예정−lead, 예정+15분)) | `NAVIGATE(LIVING_ROOM)` → 이하 현관과 동일 (intent=`MEDICATION_REMINDER`) |
| 온습도 안부 | IoT `AMBIENT_ENVIRONMENT_OBSERVED` ≥ 임계 (30°C ∨ 80%) | `NAVIGATE(LIVING_ROOM)` → 이하 동일 (intent=`WELLNESS_CHECK`) |
| 산책 | — | **보류.** `FOLLOW_*` 수신 시 실패 스텁 회신만 (무응답 금지) |

역할 분담 (한 젯슨 안의 세 프로세스):

```
[ai_chat]  웨이크워드·대화·TTS.  발행: robot/{id}/events (WAKE_WORD, CONVERSATION_*)
           구독: ai/{id}/commands (START_CONVERSATION), robot/{id}/results (도착 감지, 2-6),
                 iot/+/events (현관, 기존)
[bridge]   MQTT↔Nav2.  구독: robot/{id}/commands (NAVIGATE·CANCEL)
           발행: robot/{id}/results (NAVIGATION_RESULT v1)
[vision]   사람 추적 → UDP:5005 → vision_udp_bridge → person_follower (접근 단계에만)
```

`ai_chat` 쪽 배선 완료 항목 (2-3):
- `contracts/ai_commands.py` — START_CONVERSATION 파싱, CONVERSATION_STARTED/ENDED 봉투
- `ai_commands.py` — `AiCommandSubscriber`. paho 콜백 스레드에서 파싱·dedup·만료 확인·
  CONVERSATION_STARTED 즉시 발행까지 끝내고, 실제 대화 진행은 `Runtime.
  backend_conversation_queue` 로 메인 루프에 넘긴다(마이크는 한 스레드만 쥘 수 있어서)
- `bootstrap.py` — 메인 루프가 `wake.wait_for_wake()` 대기 중에도 이 큐를 확인할 수
  있도록 `WakeWordDetector.interrupt_check` 훅을 추가(§6 환경 함정 참고). 큐에 항목이
  있으면 `_run_backend_conversation` 이 첫 문장을 `backend_command` 경로로 말하고,
  이어지는 발화는 기존 `_run_graph_conversation`(보미야 세션과 동일 기계)을 그대로 탄다.
  종료 사유(farewell/no_speech/interrupted/seed 실패)를 CONVERSATION_ENDED outcome 으로
  옮긴다.
- `ingress.backend_command` 의 체크포인트 오염 버그 수정(2026-08-06 랭그래프 분석 P1-b) —
  빈 명령이 이전 턴의 intent/user_input 을 재사용하지 않도록 명시적으로 비운다.

**백엔드는 `SPEAK` 를 절대 발행하지 않는다** (main 전체 grep 0건). 대화는 전부
`START_CONVERSATION` 이고, bridge 는 이동만 담당한다.

---

## 2. MQTT 계약 요약 — 문서가 아니라 **코드가 기준**이다

정본 문서는 `docs/mqtt/scenario-contract-v1.md` 이지만, 백엔드 파서
(`MqttInboundMessageParser.java`)가 문서보다 좁다. **아래 표가 구현 기준이다.**

### 공통 (안 지키면 조용히 폐기된다 — 에러 응답 없음)

- **QoS 1 / retain=false.** QoS 0 은 폐기, retained 는 폐기.
- 봉투 필수: `eventId`(≤64자)·`type`·`occurredAt`(오프셋 포함 ISO 8601)·`payload` + **최상위
  `robotId`** (IoT 는 `sourceId`). 토픽의 `{robotId}` 와 본문 값이 일치해야 한다.
- `ROBOT_ID` 는 **deviceId 공간**(`bomi-AA001`, robot.device_id)이다. REST 온보딩의 UUID 와
  다르다 — 혼용 금지.
- 상관관계 ID(`scenarioId`·`conversationId`·`commandId`)는 **최상위**. payload 안에 넣으면 거부.
- UUID 는 canonical 36자만 (`1-1-1-1-1` 축약형 거부).
- **전 필드 화이트리스트**: 허용 목록 밖 필드가 하나라도 있으면 통째로 거부.

### 로봇 → BE 결과 (`NAVIGATION_RESULT`)

```json
{"eventId":"...", "type":"NAVIGATION_RESULT", "occurredAt":"...+09:00", "robotId":"bomi-AA001",
 "scenarioId":"(echo)", "commandId":"(echo)",
 "payload":{"outcome":"...", "resultCode":"...", "reasonCode":null}}
```

- `outcome` ∈ `SUCCEEDED|FAILED|CANCELLED|TIMED_OUT`
- `resultCode` ∈ `ARRIVED|NOT_ARRIVED` — 교차 제약: `SUCCEEDED`→`ARRIVED`+`reasonCode:null`,
  비성공→`NOT_ARRIVED`+`reasonCode` 필수
- **`reasonCode` 는 키 자체가 항상 존재해야 한다** (값 null 허용)
- `reasonCode` enum 은 문서(11개)가 아니라 코드 기준 **7개**: `COMMAND_EXPIRED` `UNKNOWN_TARGET`
  `PATH_BLOCKED` `LOCALIZATION_LOST` `EXECUTION_TIMEOUT` `SAFETY_STOP` `INTERNAL_ERROR`
- 선택 필드는 `location`(단, `ARRIVED` 일 때만)·`message` 뿐
- **legacy 형식(`payload:{scenarioId,status}`)은 파서는 통과하지만 보미야 호출 orchestrator 가
  거부한다.** v1 필수.

### BE → AI (`START_CONVERSATION`, 토픽 `bomi/v1/ai/{robotId}/commands`)

- payload 4필드 전부 필수: `seniorId`·`intent`·`text`·`triggerContext`
- `intent` ∈ `WELLNESS_CHECK|MEDICATION_REMINDER|HOMECOMING_GREETING` (셋뿐)
- ⚠️ **`expiresAt` 은 문서상 60초지만 실제 10초다** (`MqttConversationGateway.java:96`).
  `CONVERSATION_STARTED` 를 10초 안에 보내야 한다. 대화 최대 5분.
- `triggerContext` 는 계약 예시보다 필드가 많을 수 있다(`slotKey`·`location` 등) — 엄격 파싱 금지.

### AI → BE (`CONVERSATION_STARTED` / `CONVERSATION_ENDED`, 토픽 `robot/{id}/events`)

- STARTED: 최상위 `scenarioId`+`conversationId`+`commandId` 셋 다 필수, payload `{intent}` (일치 검증됨)
- ENDED: 최상위 `scenarioId`+`conversationId` (commandId 없음), payload
  `{outcome: COMPLETED|NO_RESPONSE|CANCELLED|FAILED, reasonCode}` — `FAILED` 면 reasonCode 필수

### 타임아웃 (로봇 입장의 데드라인)

| 대상 | 값 |
|---|---|
| `NAVIGATE` `expiresAt` | 2분 (만료 명령 실행 금지 → `COMMAND_EXPIRED` 회신) |
| `START_CONVERSATION` → `CONVERSATION_STARTED` | **10초** |
| 대화 최대 | 5분 (초과 시 BE 가 FAILED/CONVERSATION_TIMEOUT 처리) |
| `FOLLOW_*` ACK | 10초 (산책 보류지만 스텁은 이 안에 회신) |
| 시나리오 전체 | 20분 (BE 워치독 → TIMED_OUT → SAFE_STOP) |

---

## 3. 안전 — SAFE_STOP 과 리셋

**실패 결과 하나가 로봇을 잠근다.** `COMPLETED` 가 아닌 모든 시나리오 종료(FAILED/CANCELLED/
TIMED_OUT)는 로봇 mode 를 `SAFE_STOP` 으로 만들고, 이후 모든 이동 시나리오가 차단된다.
**자동 복구 경로는 없다** (재시작 무효, MQTT 로 못 품). 운영자 REST 는 시크릿 미설정으로 503.

→ 대비책은 `scripts/dev/reset-demo.sql`. **리허설 사이마다 실행한다.** (SAFE_STOP 뿐 아니라
`NAVIGATING` 으로 남은 시나리오의 `ACTIVE_SCENARIO_EXISTS` 차단도 함께 푼다.)

물리 안전 (`robot/docs/robot-joystick-slam.md` 준수):
- 모터 전원은 받침대 검증 전 OFF. 바퀴 띄운 채 ±0.03 m/s 부터.
- **명령 발행을 끊고 0.5초 안에 정지하지 않으면 실험 중단** (Pico 워치독 300ms).
- 하나의 `robotId` 에 명령 소비자 하나 — 실물 bridge 와 `publish_event.py robot-sim` 동시 실행 금지.
- 실물 브로커에 `publish_event.py` 로 이동 시나리오 시작 금지 (격리/로컬 브로커에서만).

---

## 4. 검증 사다리 — 현재 위치를 항상 이 표에 기록한다

| 단계 | 환경 | 통과 기준 | 상태 |
|---|---|---|---|
| V0 단위 | 로컬 | bridge·ai_chat 테스트 + ruff 초록 | 진행 전 |
| V1 계약 왕복 | 로컬 mosquitto + mock | wake → NAVIGATE → v1 ARRIVED → **DB scenario=COMPLETED, robot=IDLE** | 진행 전 |
| V2 실브로커 mock | `i15e102.p.ssafy.io:8883` | 보미야 1왕복 + START_CONVERSATION 왕복 | 진행 전 |
| V3 바퀴 띄움 | 젯슨 + Nav2 + 받침대 | NAVIGATE 3타깃 → Nav2 goal 확인, 접근 체인 수동 검증 | 진행 전 |
| V4 실주행 | 시연 장소 실측 map | §5 대본대로 4개 시나리오 리허설 | 진행 전 |

**증거 규칙 (구 §26 계승): 파서 통과가 아니라 DB 종결 상태가 증거다.** 각 단계 결과는
`docs/carebot/PROGRESS.md` 에 "로직 검증/실기 미검증" 구분으로 기록한다.

---

## 5. "잘"의 정의 — 시연 대본 기준 합격

보장 층위: **1층(계약·배선)은 코드가 보장** / 2층(주행 품질)은 현장 실측이 결정 /
3층(체감)은 아래 대본 기준으로만 판정한다. 대본 밖 임의 상황은 보장하지 않는다.

| 시나리오 | 대본 | 합격 기준 |
|---|---|---|
| 보미야 호출 | 어르신 소파 착석, 로봇 DEFAULT 에서 시작 | 호출 → 3초 내 첫 응답 → 이동(침묵) → 거실 도착 → **1m 내 접근·정지** → 본 대화. DB COMPLETED |
| 현관 인사 | 문 개방 (실센서 or `publish_event.py door` 폴백) | ENTRANCE 도착 → 인사 1왕복 이상 → DEFAULT 복귀 → COMPLETED |
| 복약 알림 | 시연 −5분에 care_record 슬롯 시드 | 창 내 tick → 이동 → 복약 대화 → 복귀 → COMPLETED |
| 온습도 안부 | `publish_event.py ambient --temp 31` | 임계 판정 → 이동 → 안부 대화 → 복귀 → COMPLETED |

사람 접근(2-5)은 **킬 스위치 필수** — 불안정하면 끄고 고정 좌표로 폴백한다.

---

## 6. 환경 함정 (실기에서 이미 밟은 것들 — 재발 방지)

| 함정 | 대응 |
|---|---|
| **PYTHONPATH 상반 요구** | ai_chat 테스트·단독 실행은 `env -u PYTHONPATH`(ROS 의 lark/numpy 가 pytest 죽임), **로봇 구동 시엔 유지**. 진입점마다 구분한다 |
| paho-mqtt 핀 3곳 상이 | bridge·ai_chat 코드는 1.x 콜백 스타일 → **`paho-mqtt>=1.6,<2` 통일** (2.x 는 생성자부터 깨짐) |
| `core` 미빌드 | waypoint 경로가 ament share 에서 오므로 `colcon build --packages-select core bridge` 없이는 bridge 가 전부 FAILED |
| `.env` CRLF | API 키 조용한 실패. 젯슨 반입 시 `dos2unix` |
| 오디오 장치 인덱스 | 재부팅마다 24↔25 뒤바뀜, `AUDIO_INPUT_DEVICE=1` 은 젯슨에선 HDMI. 부팅 후 목록 확인 |
| ROS2 launch 경로 TLS | `mqtt_bridge_node` 가 TLS 파라미터 미전달이었음 — 2-2 에서 수정. 수정 전 코드로 실브로커 접속 불가 |
| 좌표 미실측 | `room_waypoints.yaml` 의 `living_room`·`default` 는 실측 전까지 임시값 — 파일 주석에 표기 |
| **레거시 우회** | `USE_GRAPH_RUNTIME=false` 또는 `--legacy` 는 게이트·트리아지·침묵 감시·현관 연동을 **통째로 제거**한다. 시연 env 에서는 미설정 또는 true 고정 |
| backend_command 체크포인트 오염 | 빈/잘못된 명령이 상태 키를 안 갱신하면 이전 `intent`/`user_input` 이 재사용될 수 있음 — 2-3 에서 진입 시 턴 로컬 상태 초기화로 방어 (연속 호출 회귀 테스트 포함) |
| ⚠️ **마이크는 한 스레드만 쥔다 — `wake.interrupt_check`, 실기 미검증** | START_CONVERSATION 이 웨이크워드 대기 중에도 대화를 시작할 수 있어야 해서 `WakeWordDetector.wait_for_wake()` 에 1초 폴링 인터럽트 훅을 추가했다(2-3). 로직은 테스트로 검증했지만 **실제 `sd.InputStream` 콜백 스레드 동작은 젯슨에서 아직 확인 못 함** — V3 단계에서 반드시 실측(현관 인사 시나리오로 "보미야 없이 대화가 시작되는지" 확인) |

---

## 7. 이 스프린트에서 하지 않는 것 (기록하되 손대지 않음)

- 산책 시나리오 (FOLLOW 스텁 회신만) — 단, **도착 후 사람 접근은 범위 안**이다 (백엔드 무관)
- 백엔드 코드 수정 (불가피하면 cherry-pick 절차로만)
- `main` 잔여물 정리 (`tmp/` 332파일, `output/`, 루트 `ai-develop` 파일) — 기록만
- 구 CLAUDE.md §1~§17 의 대화 설계 개편 — 그 헌법은 보관 중이며 스프린트 후 복귀한다
- **[랭그래프 분석 P1-a]** `speech_proposal` 큐 dispatcher — 로컬 식사·수분·재질의·동의 발화가
  큐에 쌓이기만 하고 나가지 않는 상태지만, 시연 4개 시나리오는 전부 백엔드 주도/웨이크워드라
  무관. 시연 후 티켓 (원자적 claim → proactive 그래프 호출)
- **[랭그래프 분석 P1-c]** 체크포인트의 민감 ctx 무기한 누적 (평문 SQLite, "기억하지 마" 후
  잔존, SD 수명) — 시연 후 티켓 (ctx 비영속화 또는 보존 정책)
