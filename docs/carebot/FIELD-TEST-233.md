# 실기 점검 — S15P11E102-233

> **책상에서 채워 넣는 종이입니다.** 읽는 문서가 아니라 쓰는 문서입니다.
>
> 위에서 아래로 순서대로 합니다. 각 단계에 **① 실행할 명령 ② 말할 문장 ③ 볼 곳 ④ 적을 칸**이 있습니다.

## 목차

| 절 | 무엇 | 대략 | 마이크 |
| --- | --- | --- | --- |
| [0. 준비](#0-준비) | 코드·환경·장치·에코 | 30분 | 일부 |
| [1. 어디를 봐야 하나](#1-어디를-봐야-하나--창-4개) | **창 4개 배치 + 저장 위치 지도** | 10분 | ✕ |
| [A. 기본 왕복](#a-기본-왕복-204205) | 마이크→스피커 한 바퀴 | 30분 | ✓ |
| [B. 에코·barge-in](#b-에코와-barge-in-205) | 임계치 실측 | 40분 | ✓ |
| [C. 게이트·사다리](#c-게이트와-침묵-사다리-206207) | 능동 발화 | 40분 | ✓ |
| [D. 트리아지](#d-트리아지-210) | 안전 판정 | 30분 | ✓ |
| [E. 계약 대화](#e-계약-대화-209227) | 온보딩·동의 | 30분 | ✓ |
| [F. 현관](#f-현관-208226) | MQTT | 20분 | ✕ |
| [G. 의미 검색](#g-의미-검색-218) | 이어짐·회상 | 30분 | ✓ |
| [정리](#발견한-것을-세-갈래로-나눕니다) | 분류·되돌리기 | 20분 | ✕ |

## 이 점검의 목적은 실패를 찾는 것입니다

전부 잘 돌아갔다는 결과가 나오면 **충분히 안 해본 것**입니다. 자동 테스트 499건이 이미 그 범위를 덮고 있습니다.

| 자동 테스트가 보는 것 | 실기에서만 보이는 것 |
| --- | --- |
| "에코라고 판정했을 때 올바르게 행동하는가" | **무엇을 에코로 볼 것인가**(임계치) |
| 프롬프트에 회피 목록이 들어갔는가 | 실제 모델이 그것을 지키는가 |
| 문장 분할이 맞는가 | 그 문장이 **소리로** 자연스러운가 |
| 사다리가 3시간에 올라가는가 | 3시간이 **적절한 값인가** |
| ASR 텍스트가 들어오면 | **어르신 발음을 ASR 이 어떻게 망가뜨리는가** |

마지막이 가장 큽니다. 지금 **모든 판정**(트리아지 표현 목록, 동의 판정, 지남력 표지, 맞장구)이 **깨끗한 텍스트를 전제**하고 있습니다.

---

# 0. 준비

## 0.1 코드가 최신인가

```bash
cd C:/Users/workspaces/S15P11E102 && git log --oneline -1
```

- [ ] `232`(런타임 배선)가 들어간 `ai-develop` 이거나 그 위입니다
- [ ] 가능하면 `218`(AI) → `263` → `212` → `233` 이 쌓인 브랜치를 씁니다

> **232 없이는 시작할 수 없습니다.** 232 전의 `main.py` 는 옛 `ConversationPipeline` 을 띄웁니다. 마이크에 말해도 그래프·게이트·사다리·트리아지가 **하나도 돌지 않습니다.**

## 0.2 자동 테스트가 먼저 초록인가

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe -m pytest -m "not integration and not manual" -q
```

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe -m ruff check src tests
```

- [ ] `499 passed`  - [ ] `All checks passed`

> 빨간 것이 있으면 실기로 가지 않습니다. 실기 발견이 코드 문제인지 환경 문제인지 구분할 수 없게 됩니다.

## 0.3 `.env` 채우기

`robot/ai_chat/.env` 입니다. 없으면 `.env.example` 을 복사합니다.

| 변수 | 값 | 없으면 | 확인 |
| --- | --- | --- | --- |
| `RTZR_CLIENT_ID` / `_SECRET` | (발급값) | STT 불가 | [ ] |
| `GEMINI_API_KEY` | (발급값) | 생성 불가 | [ ] |
| `TYPECAST_API_KEY` | (발급값) | TTS 불가 | [ ] |
| `SENIOR_ID` | `10000000-0000-4000-8000-000000000001` | **기동 거부** | [ ] |
| `BACKEND_BASE_URL` | `http://localhost:8080` 또는 EC2 | 문맥이 캐시로만 | [ ] |
| `AUDIO_MODE` | `laptop` | 장치 인덱스를 요구함 | [ ] |
| `LOCALSTORE_DIR` | `var/localstore` (기본) | — | [ ] |

`SENIOR_ID` 는 `app_user` 의 **실제 UUID** 여야 합니다. 위 값은 `seed-kim-sunja.sql` 의 김순자입니다. 임의 값으로 시작하면 그 값으로 상태가 쌓이고, 나중에 바꾸는 순간 사다리와 재실 기록이 통째로 사라집니다.

`USE_GRAPH_RUNTIME` 은 **건드리지 않습니다**(기본 `true`).

## 0.4 장치와 외부 API

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe tests/list_audio_devices.py
```

- [ ] 마이크가 있고 `in>0` → 인덱스 `____`  - [ ] 스피커가 있고 `out>0` → 인덱스 `____`

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe tests/manual/audio_smoke.py
```

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe tests/manual/stt_smoke.py
```

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe tests/manual/tts_smoke.py
```

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe tests/manual/llm_smoke.py
```

- [ ] 녹음·재생 OK  - [ ] STT OK  - [ ] TTS OK  - [ ] LLM OK

**STT 스모크에서 말할 것** — 세 번 실행합니다.

| # | 말할 문장 | ASR 이 받아쓴 것 |
| --- | --- | --- |
| 1 | "오늘 날씨가 참 좋네요" (또박또박) | |
| 2 | 같은 문장 (빠르게, 흘리듯) | |
| 3 | 같은 문장 (사투리 / 낮은 목소리) | |

> 3번이 중요합니다. 78세 어르신의 발음은 1번보다 3번에 가깝습니다.

## 0.5 백엔드와 Qdrant가 살아 있는가

```bash
curl -s http://localhost:8080/actuator/health
```

EC2 를 쓴다면:

```bash
ssh bomi "docker ps --format '{{.Names}}\t{{.Status}}'"
```

- [ ] `bomi-backend` `healthy`  - [ ] `bomi-qdrant` `healthy`  - [ ] `bomi-postgres` `healthy`

컬렉션 확인 (호스트 포트를 열지 않았으므로 컨테이너 안에서):

```bash
ssh bomi "docker exec bomi-qdrant bash -c \"exec 3<>/dev/tcp/127.0.0.1/6333 && printf 'GET /collections HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n' >&3 && cat <&3\""
```

- [ ] `memory` 와 `conversation_summary` 두 컬렉션이 보입니다

> 백엔드가 처음 뜰 때 만듭니다. 없으면 백엔드 env 의 `QDRANT_HOST` 를 확인합니다.

## 0.6 ★ 에코를 먼저 잡습니다 — 건너뛰면 안 됩니다

`docs/hardware/audio-echo-bargein-verification.md` 를 함께 엽니다.

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe -m bomi_ai_chat --once -v
```

**말할 것**: "안녕하세요" 한 마디. 그 뒤 로봇이 말하는 동안 **아무 말도 하지 않습니다.**

- [ ] 로봇이 자기 말에 멈추지 않습니다

멈춘다면 → 스피커와 마이크를 떼어 놓고 다시. 그래도 멈추면 `policy.ECHO_GUARD_SEC` 또는 `ECHO_VAD_THRESHOLD_MULTIPLIER` 를 올립니다.

```
스피커-마이크 거리:        cm      볼륨:        %
ECHO_GUARD_SEC 최종:                   (기본값에서 바뀜: Y / N)
ECHO_VAD_THRESHOLD_MULTIPLIER 최종:
```

> **이 셋이 안 맞으면 이후 A~G 의 모든 관찰이 오염됩니다.** "게이트가 이상하다"의 정체가 에코인 경우가 대부분입니다.

---

# 1. 어디를 봐야 하나 — 창 4개

점검 내내 **터미널 4개**를 띄워 둡니다.

## 창 1 — 로봇 (여기서 말합니다)

```bash
cd C:/Users/workspaces/S15P11E102/robot/ai_chat && ./venv/Scripts/python.exe -m bomi_ai_chat -v
```

여기서 볼 것:

```
14:03:21 INFO    bomi_ai_chat.main: logging to var\localstore\logs\ai_chat.log
14:03:22 INFO    bomi_ai_chat.jobs.scheduler: scheduler built: silence/door=60s outbox=30s
14:03:22 INFO    bomi_ai_chat.bootstrap: conversation runtime ready (senior=1000...)
14:03:40 INFO    bomi_ai_chat.door.occupancy: occupancy UNKNOWN -> HOME (source=speech)
14:03:41 INFO    bomi_ai_chat.turn_timer: turn latency 1.832s (senior=... intent=companion) | stt=0.410s graph=1.422s
```

> **로그가 하나도 안 보이면** 233 이전 코드입니다. `main.py` 의 `logging.basicConfig` 가 주석 처리돼 있어서 INFO 가 통째로 버려지고 있었습니다. 이 브랜치에서 고쳤습니다.

## 창 2 — 로그 파일 실시간

```bash
cd C:/Users/workspaces/S15P11E102/robot/ai_chat; Get-Content var/localstore/logs/ai_chat.log -Wait -Tail 40
```

창 1은 INFO 이상, **이 파일은 항상 DEBUG** 입니다. 판정 이유를 볼 때 여기를 봅니다.

관심 있는 것만:

```bash
cd C:/Users/workspaces/S15P11E102/robot/ai_chat; Get-Content var/localstore/logs/ai_chat.log -Wait | Select-String "latency|gate|ladder|triage|degrad|occupancy"
```

## 창 3 — 로컬 상태 (SQLite)

로봇의 판단 결과가 여기 쌓입니다. 아래를 `watch_state.ps1` 로 저장해 두면 편합니다.

```bash
cd C:/Users/workspaces/S15P11E102/robot/ai_chat; while ($true) { Clear-Host; ./venv/Scripts/python.exe -c "
import sqlite3
r = sqlite3.connect('var/localstore/runtime.sqlite'); r.row_factory = sqlite3.Row
print('=== runtime_state ===')
for row in r.execute('SELECT * FROM runtime_state'):
    d = dict(row)
    print(f\"  occupancy={d['occupancy']}  silence_level={d['silence_level']}  rest={d['rest_state']}\")
    print(f\"  last_user_interaction_at={d['last_user_interaction_at']}  last_spoke_at={d['last_spoke_at']}\")
print()
print('=== speech_proposal (대기 중인 제안) ===')
for row in r.execute('SELECT intent, priority, seed FROM speech_proposal'):
    print('  ', dict(row))
print()
print('=== outbox (보호자 알림 큐) ===')
o = sqlite3.connect('var/localstore/outbox.sqlite'); o.row_factory = sqlite3.Row
for row in o.execute('SELECT tier, status, attempts FROM outbox ORDER BY rowid DESC LIMIT 5'):
    print('  ', dict(row))
"; Start-Sleep 20 }
```

### 로컬에 무엇이 어디 저장되는가

`robot/ai_chat/var/localstore/` (= `LOCALSTORE_DIR`)

| 파일 → 표 | 무엇이 들어가나 | 언제 바뀌나 |
| --- | --- | --- |
| `runtime.sqlite` → `runtime_state` | 재실, **침묵 사다리 칸**, 마지막 발화 시각, 휴식 상태 | 매 턴 · 매 틱 |
| `runtime.sqlite` → `speech_proposal` | 말하겠다는 **제안**(아직 발화 아님) | 스케줄러·사다리·현관·T3 동의 |
| `runtime.sqlite` → `context_cache` | 백엔드 문맥의 읽기 캐시 | 문맥 조회 성공 시 |
| `runtime.sqlite` → `completed_slot` | "약 먹었어"로 완료된 복약 슬롯 | schedule 핸들러 |
| `runtime.sqlite` → `door_alert` | 현관 노드 무응답 알림 이력 | 현관 감시 틱 |
| `runtime.sqlite` → `cached_audio` | 캐시된 TTS 파일 목록 | 프로브 최초 생성 |
| **`outbox.sqlite` → `outbox`** | **보호자 알림 발신 큐 (T1/T2/T3)** | 에스컬레이션 |
| `audio_cache/` | 캐시된 음성 파일 | 위와 같음 |
| `logs/ai_chat.log` | 전체 DEBUG (20MB × 5 회전) | 항상 |
| `checkpoint.sqlite` | LangGraph 대화 상태 (`thread_id` = `SENIOR_ID`) | 매 턴 |

> `runtime_state` 와 checkpoint 는 **다른 저장소**입니다. 그래프 노드는 checkpoint 를, 배경 틱은 `runtime_state` 를 읽습니다. **안전 감시(사다리)는 항상 `runtime_state` 를 봅니다.**

## 창 4 — 백엔드

```bash
ssh bomi "docker logs -f --tail 40 bomi-backend"
```

### 서버에 무엇이 어디 저장되는가

| 로봇이 부르는 것 | 서버 표 | 무엇이 |
| --- | --- | --- |
| `POST /api/v1/robot/conversation-events` | `conversation`, `conversation_message` | **모든 발화** (어르신·로봇 각 1행) |
| `POST /api/v1/robot/guardian-alerts` | `care_record` (`GUARDIAN_ALERT`) | T1/T2/T3 알림 |
| `POST /api/v1/seniors/{id}/conversation-context` | (읽기 전용) | 프로필·기억·복약·요약 |
| `POST /api/v1/seniors/{id}/door-events` | `occupancy_event`, `robot.occupancy_status` | 현관 통과 |
| `POST /api/v1/robot/onboarding/...` | `onboarding_session`, `onboarding_answer` | 온보딩 답변 |
| `POST /api/v1/robot/clarifications/{id}/answer` | `fact_candidate` | 재질의 답변 |

대화가 실제로 쌓이는지:

```bash
ssh bomi "docker exec bomi-postgres psql -U bomi -d bomi -c \"SELECT role, left(content,40) AS content, occurred_at FROM conversation_message ORDER BY occurred_at DESC LIMIT 10;\""
```

보호자 알림이 도착했는지:

```bash
ssh bomi "docker exec bomi-postgres psql -U bomi -d bomi -c \"SELECT notification_tier, occurred_at, details->>'reason' AS reason FROM care_record WHERE record_type='GUARDIAN_ALERT' ORDER BY occurred_at DESC LIMIT 10;\""
```

임베딩 진행 상황:

```bash
ssh bomi "docker exec bomi-postgres psql -U bomi -d bomi -c \"SELECT embedding_status, count(*) FROM memory GROUP BY embedding_status;\""
```

---

# A. 기본 왕복 (204·205)

```bash
cd C:/Users/workspaces/S15P11E102/robot/ai_chat && ./venv/Scripts/python.exe -m bomi_ai_chat -v
```

## A-1. 한 바퀴 도는가

**말할 것**: "안녕하세요"

- [ ] 로봇이 대답합니다
- [ ] 창 1에 `turn latency` 가 찍힙니다
- [ ] 창 3의 `occupancy` 가 `HOME` 으로 바뀝니다 (발화 = 재실 증거)
- [ ] 창 4에 `conversation-events` 가 도착합니다

## A-2. 지연이 예산 안인가

같은 말을 5번 하고 `turn latency` 를 적습니다.

```
1회:      s   2회:      s   3회:      s   4회:      s   5회:      s
가장 느린 단계 (stt= / graph= 중):
```

- [ ] 5회 중 4회 이상이 **2.0초 이내**입니다

넘으면 창 2에서 단계별 내역을 봅니다. 대개 네트워크(문맥 조회·생성·TTS)이고 로컬 계산이 아닙니다.

## A-3. ★★ ASR 이 무엇을 망가뜨리는가 — 이 절의 진짜 목적

창 2를 이렇게 걸어 두고:

```bash
cd C:/Users/workspaces/S15P11E102/robot/ai_chat; Get-Content var/localstore/logs/ai_chat.log -Wait | Select-String "transcribe|intent|safety_level"
```

한 줄씩 **소리 내어 말하고** 결과를 적습니다.

| # | 말할 문장 | ASR 결과 | 판정 | 기대 | OK? |
| --- | --- | --- | --- | --- | --- |
| 1 | 오늘 며칠이야 | | | info | |
| 2 | **무릎이 아파** | | | **평범한 턴** | |
| 3 | 가슴이 아파 | | | **확인 질문** | |
| 4 | 외로워 | | | emotional | |
| 5 | 약 먹었어 | | | schedule | |
| 6 | 심심해 | | | companion | |
| 7 | 어제 배가 아팠어 | | | 과거 → 평범 | |
| 8 | 안 아파 | | | 부정 → 평범 | |
| 9 | 외로운데 오늘 며칠이야 | | | emotional | |
| 10 | 그 저기 그거 뭐였지 | | | **되묻는가** | |
| 11 | (사투리로 아무 문장) | | | | |

> **2번이 가장 중요합니다.** 여기서 확인 질문이 나오면 실사용이 불가능합니다 — 만성 무릎 통증이 있는 어르신에게 매번 "괜찮으세요?"를 묻게 됩니다.

## A-4. 맞장구 목록 채우기

`policy.BACKCHANNELS` 는 지금 **상상으로 만든 8개**입니다.

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe -c "from bomi_ai_chat import policy; print(policy.BACKCHANNELS)"
```

**말할 것**: 로봇이 길게 말하는 동안 자연스럽게 추임새를 넣습니다.

```
실제로 나온 맞장구 표현 (목록에 없던 것):
```

---

# B. 에코와 barge-in (205)

| # | 무엇을 하나 | 기대 | 결과 |
| --- | --- | --- | --- |
| 1 | 로봇이 말하는 중 **"응"** | 계속 말한다 | |
| 2 | 로봇이 말하는 중 **"잠깐만"** | 즉시 멈춘다 | |
| 3 | 2번 뒤 잠시 대기 | 못 한 말이 이어진다 | |
| 4 | **프로브 중** 아무 말 | **사다리 리셋**, 프로브 재개 안 함 | |

4번이 헷갈리기 쉽습니다. 프로브에서는 **끼어든 것 자체가 대답**입니다 — 살아 계시다는 뜻이므로 재개하지 않습니다.

```bash
cd C:/Users/workspaces/S15P11E102/robot/ai_chat; Get-Content var/localstore/logs/ai_chat.log -Wait | Select-String "barge|echo|remaining|ladder"
```

`docs/hardware/audio-echo-bargein-verification.md` 7개 항목:

- [ ] 1 임계치 실측  - [ ] 2 AEC 결정  - [ ] 3 원거리 마이크  - [ ] 4 VAD·웨이크워드
- [ ] 5 중단 체감 지연  - [ ] 6 맞장구(A-4로 대체)  - [ ] 7 `pipeline.py` 연결

---

# C. 게이트와 침묵 사다리 (206·207)

## C-1. 스케줄러가 도는가

창 1 기동 로그에 `scheduler built: silence/door=..s outbox=..s` 가 있습니다.

- [ ] 있습니다

## C-2. 사다리 — 3시간을 기다리지 않는 방법

**방법 1 (권장, 코드 수정 없음).** 로봇을 끄고 별도 창에서:

```bash
cd C:/Users/workspaces/S15P11E102/robot/ai_chat && ./venv/Scripts/python.exe -c "
import time
from bomi_ai_chat.clock import SimClock, install_clock
from bomi_ai_chat.jobs.scheduler import run_all_ticks_once
from bomi_ai_chat.localstore import proposals, runtime

SENIOR = '10000000-0000-4000-8000-000000000001'
install_clock(SimClock(start=time.time(), speed=0.0))
from bomi_ai_chat.clock import clock
for hour in range(6):
    clock.advance(3600)
    run_all_ticks_once(SENIOR)
    state = runtime.load(SENIOR)
    seeds = [p.get('seed') for p in proposals.pending(SENIOR)]
    print(f'{hour+1}시간  사다리={state[\"silence_level\"]}  대기제안={seeds}')
"
```

- [ ] 1칸: 가벼운 안부 → 문장 `                                        `
- [ ] 2칸: 직접 질문 → 문장 `                                        `
- [ ] 3칸: 마지막 시도 → 문장 `                                        `
- [ ] 3칸 뒤 `outbox` 에 T1 이 들어갑니다 (창 3)

**방법 2 (실시간으로 듣고 싶을 때).** `policy.SILENCE_LADDER_SEC` 를 `[60, 30, 20]` 으로 바꿉니다. **환경변수로는 못 바꿉니다.**

- [ ] **`policy.py` 를 되돌렸습니다** ← 잊으면 실사용에서 1분마다 프로브가 나갑니다

## C-3. T1 이 백엔드까지 가는가

- [ ] 창 3의 `outbox` 에 `tier=T1` 이 보입니다
- [ ] 창 4에 `guardian-alerts` 가 도착합니다
- [ ] `care_record` 에 `GUARDIAN_ALERT` 행이 생깁니다

## C-4. ★ 3시간이 적절한 값인가 — 이 절의 진짜 질문

```
실제로 조용해도 이상하지 않은 시간대:
낮잠 습관 (몇 시부터 몇 시간):
권장 조정값:  1칸 ____h   2칸 ____m   3칸 ____m
```

## C-5. quiet hours

- [ ] `app_user.quiet_hours_start/end` 를 지금 시각이 포함되도록 임시 변경 → 잡담이 안 나갑니다
- [ ] 되돌렸습니다

---

# D. 트리아지 (210)

A-3 에서 판정은 확인했습니다. 여기서는 **에스컬레이션 경로**입니다.

**말할 것**: "가슴이 아파" → 확인 질문을 들음 → **아무 대답도 하지 않고 90초 기다립니다.**

- [ ] 90초 뒤 T1 이 `outbox` 에 들어갑니다 (창 3)
- [ ] 창 4에 `guardian-alerts` 가 도착합니다

```
확인 질문 문장:
실제로 T1 이 나간 시각 (몇 초 뒤):
```

## D-2. ★ 자해 표현 목록 검토 (마이크 불필요, 병행 가능)

지금 기동할 때마다 경고가 찍힙니다: `self-harm marker list has not been human-reviewed yet`.

```bash
cd robot/ai_chat && ./venv/Scripts/python.exe -c "
from bomi_ai_chat import policy
for m in policy.SELF_HARM_MARKERS: print(' -', m)
print('reviewed =', policy.SELF_HARM_MARKERS_REVIEWED)
"
```

- [ ] 한 줄씩 읽었습니다
- [ ] 오탐이 날 표현을 걸러냈습니다 (예: `살고 싶` 은 단독으로 반대 의미입니다)
- [ ] 빠진 표현을 추가했습니다
- [ ] `policy.SELF_HARM_MARKERS_REVIEWED = True` 로 바꿨습니다
- [ ] 커밋 메시지에 검토 사실을 남겼습니다

---

# E. 계약 대화 (209·227)

온보딩이 시작되려면 서버에 활성 세션이 있어야 합니다. `ROBOT_ID` 를 `.env` 에 넣거나 아래에 직접 넣습니다.

```bash
curl -s -X POST http://localhost:8080/api/v1/robot/onboarding/sessions -H "Content-Type: application/json" -d '{"seniorId":"10000000-0000-4000-8000-000000000001","robotId":"<ROBOT_ID>"}'
```

**말할 것** (순서대로)

| # | 말할 것 | 기대 |
| --- | --- | --- |
| 1 | (질문을 듣고) 정확한 답 | 다음 질문으로 |
| 2 | "글쎄" | **다시 묻는다** |
| 3 | (아무 말 안 함) | **동의로 처리 안 함** |
| 4 | "네" | 기록 |

- [ ] 음성만으로 완주할 수 있습니다
- [ ] **동의 문구가 소리로 들었을 때 이해됩니다** ← 화면으로 읽는 것과 다릅니다
- [ ] 민감한 값을 전체 복창해 확인합니다

```
이해되지 않았던 동의 문구:
얼버무림에 대한 실제 반응:
```

창 4에서 `onboarding_answer` 에 행이 쌓이는지 봅니다.

---

# F. 현관 (208·226)

센서가 없으면 MQTT 로 직접 발행합니다. `.env` 에 `MQTT_ENABLED=true` 와 브로커 정보를 넣고 로봇을 재시작합니다.

```bash
ssh bomi "docker exec bomi-mosquitto mosquitto_pub -h localhost -p 1883 -u '<USER>' -P '<PASS>' -t 'bomi/v1/iot/door_sensor/events' -m '{\"eventId\":\"e1\",\"type\":\"DOOR_OPENED\",\"occurredAt\":\"2026-08-03T14:00:00Z\",\"sourceId\":\"door_sensor\",\"payload\":{}}'"
```

3초 뒤 모션을 발행하면 **귀가(IN)** 입니다.

```bash
ssh bomi "docker exec bomi-mosquitto mosquitto_pub -h localhost -p 1883 -u '<USER>' -P '<PASS>' -t 'bomi/v1/iot/motion_sensor/events' -m '{\"eventId\":\"e2\",\"type\":\"MOTION\",\"occurredAt\":\"2026-08-03T14:00:03Z\",\"sourceId\":\"motion_sensor\",\"payload\":{}}'"
```

순서를 바꾸면(모션 먼저) **외출(OUT)** 입니다.

- [ ] 창 3의 `occupancy` 가 바뀝니다
- [ ] 창 4에 `door-events` 가 도착하고 `occupancy_event` 에 행이 생깁니다
- [ ] 인사가 나가고 **하나만** 나갑니다
- [ ] 빠른 IN-OUT 쌍(배달)에 인사가 나가지 않습니다

```
문에서 거실까지 실제로 걸린 시간:      s   (천천히:      s)
상관 창 15초 권장 조정값:
```

> **이동은 확인할 수 없습니다.** 로봇 본체 미연결이므로 문 앞으로 가는 동작은 범위 밖입니다.

---

# G. 의미 검색 (218)

Qdrant 가 올라갔으므로 §17 의 2번(이어짐)·10번(회상)을 **처음으로** 잴 수 있습니다.

## G-1. 켜기 — ★ 과금 주의

백엔드 env 에:

```
EMBEDDING_ENABLED=true
EMBEDDING_SYNC_ENABLED=true      # ★ 점검 중에만
EMBEDDING_SYNC_BATCH_SIZE=10     # 한 번에 10건까지만 과금
```

- [ ] 켰습니다
- [ ] **끝나면 `EMBEDDING_SYNC_ENABLED=false` 로 되돌릴 것을 기억합니다**

## G-2. 색인이 도는가

```bash
ssh bomi "docker exec bomi-postgres psql -U bomi -d bomi -c \"SELECT embedding_status, count(*) FROM memory GROUP BY embedding_status;\""
```

- [ ] `PENDING` 이 줄고 `SYNCED` 가 늡니다
- [ ] 창 4에 `embedding sync: N memories ... (N billed calls, cap 10)` 이 보입니다

```
시작 PENDING:        →  10분 뒤:          누적 과금 호출:
```

## G-3. 이어짐 (§17.2) — 이 절의 목적

| # | 말할 것 | 기대 |
| --- | --- | --- |
| 1 | "요즘 무릎이 자주 아파요" | 공감 |
| — | (색인이 돌 때까지 대기, G-2로 확인) | |
| 2 | "오늘은 좀 어때요?" 라고 로봇이 물으면 | **무릎을 언급하는가** |
| 3 | **"다리가 시큰거려"** | **"무릎"과 연결되는가** |

3번이 핵심입니다. 키워드 겹침만으로는 "다리"와 "무릎"이 매칭되지 않습니다.

```
2번 실제 응답:
3번 실제 응답:
연결됐나: Y / N
```

## G-4. 응답이 의미 검색이 켜졌다고 말하는가

```bash
curl -s -X POST http://localhost:8080/api/v1/seniors/10000000-0000-4000-8000-000000000001/conversation-context -H "Content-Type: application/json" -d '{"query":"무릎"}'
```

- [ ] `availability.semanticSearch` 가 `true` 입니다

> `false` 면 백엔드에 `UPSTAGE_API_KEY` 또는 `QDRANT_HOST` 가 없습니다.

---

# 발견한 것을 세 갈래로 나눕니다

| 갈래 | 무엇 | 어디로 |
| --- | --- | --- |
| **즉시 수정** | 오탈자, 임계치 한 칸, 문구 | 이 브랜치에서 고칩니다 |
| **별도 티켓** | 설계를 건드려야 하는 것 | Jira 신설 |
| **하드웨어 한계** | 소프트웨어로 못 고치는 것 | `PROGRESS.md` 에 "못 고침"으로 |

### 즉시 수정

| # | 무엇 | 어디 | 완료 |
| --- | --- | --- | --- |
| 1 | | | [ ] |
| 2 | | | [ ] |
| 3 | | | [ ] |

### 별도 티켓

| # | 무엇 | 왜 설계 변경인가 | 티켓 |
| --- | --- | --- | --- |
| 1 | | | |

### 하드웨어 한계

| # | 무엇 | 왜 못 고치는가 |
| --- | --- | --- |
| 1 | | |

---

# 완료 조건

- [ ] A~G 를 실기로 한 번씩 통과했습니다
- [ ] 발견한 것이 전부 세 갈래 중 하나로 분류됐습니다
- [ ] `PROGRESS.md` §2.1 "실기에서 한 번도 돌려본 적이 없습니다" 를 지웠습니다
- [ ] 하드웨어 문서의 7개 항목이 소모됐습니다
- [ ] 추정치였던 임계치가 실측값으로 바뀌었습니다 — **또는 왜 못 바꿨는지가 적혀 있습니다**
- [ ] **녹취가 남았습니다** (A-3, A-4, C-2, G-3 칸이 채워졌습니다)
- [ ] `SELF_HARM_MARKERS_REVIEWED = True` 입니다

# 끝내기 전 되돌릴 것

하나라도 남으면 실사용에서 이상하게 동작합니다.

- [ ] `policy.SILENCE_LADDER_SEC` (C-2 방법 2를 썼다면)
- [ ] `app_user.quiet_hours_start/end` (C-5)
- [ ] **`EMBEDDING_SYNC_ENABLED=false`** (G-1) ← 잔액 보호
- [ ] `policy.ECHO_GUARD_SEC` 등은 **되돌리지 않습니다** — 실측값이므로 그대로 커밋합니다

# 미리 알고 시작하는 제약

실패가 아니라 **범위 밖**입니다.

| 제약 | 결과 |
| --- | --- |
| 로봇 본체 미연결 | 문 앞으로 이동하는 동작을 확인할 수 없습니다 |
| 임베딩 API 잔액 | 시연까지 아껴야 합니다. 배치를 작게 두고, 끝나면 끕니다 |
| **실제 어르신 아님** | 발음·리듬·사투리가 실제 사용자와 다릅니다 |

마지막이 중요합니다. **개발자 목소리로 맞춘 임계치는 78세 어르신에게 맞지 않을 수 있습니다.** 여기서 모은 녹취는 첫 근사이고, 진짜 사용자 테스트는 별도 항목으로 세워야 합니다. 그 사실을 `PROGRESS.md` 에 남기십시오.
