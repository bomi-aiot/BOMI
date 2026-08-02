# 직접 돌려보고 판정하기

> **이 문서의 목적**: 코드를 읽지 않고도 "지금 잘 되고 있는가"를 직접 확인한다.
> 각 항목마다 **실행할 명령 / 성공의 모습 / 실패의 모습**을 적었다.

## 0. 준비

```bash
# 로봇 (Python)
cd robot/ai_chat
python -m venv venv && ./venv/Scripts/activate    # Windows
pip install -e ".[dev]"

# 백엔드 (Java 17)
cd backend
./gradlew --version
```

백엔드 테스트는 **실제 PostgreSQL 을 자동으로 띄웁니다**(Docker 불필요). 첫 실행에서 PG 바이너리를 내려받느라 1~2분 걸립니다.

---

## 1. 가장 빠른 전체 점검 (2분)

```bash
cd robot/ai_chat && python -m pytest -m "not integration and not manual" -q && python -m ruff check src tests
```

```bash
cd backend && ./gradlew test
```

| 결과 | 판정 |
|---|---|
| 로봇 `228 passed` + `All checks passed` | ✅ |
| 백엔드 `BUILD SUCCESSFUL` | ✅ |
| 하나라도 실패 | ❌ — 아래에서 어느 영역인지 좁힌다 |

> 숫자는 티켓이 진행되며 늘어납니다. **줄어들면 누가 테스트를 지운 것**이므로 확인하십시오.

---

## 2. 영역별 검증

### 2.1 주입 시계 — 하루가 10초에 흐르는가 (200)

```bash
cd robot/ai_chat && python -m pytest tests/test_clock.py -v
```

**성공**: `test_sim_clock_compresses_a_day_into_ten_seconds` 통과
**실패의 의미**: 압축 시계가 깨졌다는 뜻이고, 침묵 사다리(207)와 일일 요약(211)을 **검증할 방법이 사라집니다.** 실시간으로 기다리면 테스트 한 번에 하루가 걸립니다.

시계 규칙이 지켜지는지 직접 확인:

```bash
cd robot/ai_chat && grep -rn "time.time()" src
```

**성공**: `clock.py` 의 줄만 나온다
**실패**: 다른 파일이 나오면 그 파일은 압축 시계를 무시하므로, 시연에서 그 부분만 실시간으로 흐릅니다

---

### 2.2 로컬 저장소 — 재시작해도 살아남는가 (202)

```bash
cd robot/ai_chat && python -m pytest tests/test_localstore.py tests/test_outbox.py -v
```

**직접 눈으로 보고 싶다면** — 실제 SQLite 파일을 만들어 들여다봅니다.

```bash
cd robot/ai_chat && LOCALSTORE_DIR=./var/demo python -c "
from bomi_ai_chat.localstore import runtime, outbox, proposals
runtime.save('senior-1', silence_level=2, occupancy='HOME')
proposals.enqueue('senior-1', {'intent':'schedule','priority':'medium','seed':'약 드셨어요?'})
outbox.enqueue('T1', {'reason':'no_response'})
print('생성 완료')
"
```

이제 파일이 두 개 생겼는지 봅니다.

```bash
ls robot/ai_chat/var/demo
```

**성공**: `runtime.sqlite` 와 `outbox.sqlite` 가 **둘 다** 있다
**실패**: 하나만 있으면 "발신 큐만 동기 쓰기" 설계가 깨진 것입니다(§CONCEPTS 참고)

내용 확인:

```bash
cd robot/ai_chat/var/demo && python -c "
import sqlite3
for db, q in [('runtime.sqlite','SELECT senior_id,silence_level,occupancy FROM runtime_state'),
              ('runtime.sqlite','SELECT intent,priority,seed FROM speech_proposal'),
              ('outbox.sqlite','SELECT tier,status,attempt_count FROM outbox')]:
    c = sqlite3.connect(db); print(db, '->', c.execute(q).fetchall()); c.close()
"
```

**성공 예시**:

```
runtime.sqlite -> [('senior-1', 2, 'HOME')]
runtime.sqlite -> [('schedule', 'medium', '약 드셨어요?')]
outbox.sqlite -> [('T1', 'PENDING', 0)]
```

| 보이는 것 | 의미 |
|---|---|
| `outbox` 에 `status='PENDING'` | 정상. 아직 못 보냈고 큐가 들고 있다 |
| `outbox` 에 `status='SENT'` | 전송됨 |
| `outbox` 에 `status='GAVE_UP'` **이고 tier='T1'** | 🔴 **버그.** T1 은 포기하지 않아야 한다 |
| `runtime_state` 에 `occupancy='HOME'` 인데 현관 소식이 없었다 | 🔴 기본값이 잘못됐다. UNKNOWN 이어야 한다 |

정리:

```bash
rm -rf robot/ai_chat/var/demo
```

---

### 2.3 백엔드 스키마 — 빈 DB 에서 마이그레이션이 도는가 (201)

```bash
cd backend && ./gradlew test --tests "com.ssafy.bomi.migration.FlywayMigrationValidationTest"
```

이 테스트가 실제로 하는 일: **빈 PostgreSQL 을 띄우고 → V1~V5 를 순서대로 실행하고 → Hibernate 로 엔티티와 대조**합니다.

| 실패 메시지 | 의미 |
|---|---|
| `Schema-validation: missing column ...` | 엔티티를 바꾸고 마이그레이션 V파일을 안 만들었다 |
| `Migration checksum mismatch` | 🔴 **이미 적용된 V파일을 수정했다.** 배포가 터진다 |
| `migration N must have applied successfully` | 그 V파일의 SQL 이 잘못됐다 |

새 V파일을 추가했다면 이 테스트의 기대 목록(`containsExactly("1","2",...)`)도 늘려야 합니다. 안 늘리면 실패하는데, **그게 의도**입니다 — 파일만 만들고 검증을 잊는 것을 막습니다.

---

### 2.4 문맥 조립 API — 6종이 다 오는가 (203)

```bash
cd backend && ./gradlew test --tests "com.ssafy.bomi.context.ConversationContextServiceTest"
```

**실제로 호출해 보려면** 백엔드를 띄워야 하고 PostgreSQL 이 필요합니다.

```bash
docker compose up -d postgres      # WSL2 에서
cd backend && ./gradlew bootRun
```

```bash
curl -X POST http://localhost:8080/api/v1/seniors/{어르신UUID}/conversation-context \
  -H "Content-Type: application/json" \
  -d '{"query":"무릎이 아파","memoryTopK":6,"includeDocuments":false}'
```

**성공의 모습** — 응답에 이 키들이 있습니다:

```json
{
  "profile": { "preferredName": "...", "avoidTopics": [...] },
  "todayState": { ... },
  "recentMessages": [ ... ],
  "conversationSummary": "...",
  "relevantSummaries": [ ... ],
  "memories": [ { "content": "...", "score": 0.42 } ],
  "careRecords": [ ... ],
  "availability": { "semanticSearch": false, "documentCorpus": false, "notes": [...] }
}
```

| 확인 항목 | 성공 | 실패 |
|---|---|---|
| `memories` 개수 | 요청한 `memoryTopK` 이하 | 20개씩 오면 과적재 방지가 깨진 것 |
| `availability.semanticSearch` | 지금은 `false` **가 정상** (218 전) | `true` 인데 218 이 안 끝났으면 거짓 보고 |
| `profile.avoidTopics` | 회피 주제가 실려 온다 | 비어 있으면 프롬프트가 금지문을 못 만든다 |
| **`memories` 에 `visibility=PRIVATE` 인 기억** | 로봇 호출(guardian 미지정)에서는 **와야 정상** | 보호자 지정 호출에서 오면 🔴 **프라이버시 사고** |

DB 로 직접 확인:

```sql
-- 이 어르신에게 보이면 안 되는 기억이 응답에 섞였는지
SELECT id, visibility, lifecycle_status, verification_status, content
FROM memory WHERE senior_id = '...';
```

**응답에 나온 memory id 중 `lifecycle_status <> 'ACTIVE'` 이거나 `verification_status = 'REJECTED'` 인 것이 있으면 🔴 선필터가 깨진 것입니다.**

---

### 2.5 반응형 1왕복 — 한 턴이 끝까지 도는가 (204)

```bash
cd robot/ai_chat && python -m pytest tests/test_turn_end_to_end.py tests/test_prompt_builder.py -v
```

**프롬프트를 눈으로 보고 싶다면** (LLM 호출 없이, 순수 함수라 가능):

```bash
cd robot/ai_chat && python -c "
from bomi_ai_chat.prompts import build_prompt
ctx = {
  'profile': {'preferredName':'순자님','avoidTopics':['남편 사망']},
  'memories': [{'content':'작년부터 무릎이 아프시다','lastConfirmedAt':'2026-06-01T09:00:00Z'}],
  'careRecords': [{'recordType':'MEDICATION','details':{'name':'혈압약'}}],
}
print(build_prompt(ctx, 'companion', '무릎이 아파'))
"
```

**성공의 모습** — 출력에서 이걸 확인하십시오:

| 확인 | 성공 | 실패 |
|---|---|---|
| `## 말하지 않을 주제` 섹션 | **금지문**으로 표현됨 ("먼저 꺼내지 않습니다") | "배우자가 돌아가셨습니다" 처럼 **사실로** 적혀 있으면 🔴 모델이 화제로 씁니다 |
| 출력 제약 위치 | **맨 마지막**에 있음 | 위에만 있으면 긴 문맥에 묻힙니다 |
| 기억의 날짜 | `(2026-06-01)` 처럼 붙어 있음 | 없으면 모델이 여섯 달 전 일을 오늘 일처럼 말합니다 |
| 반복 횟수 | **없어야 함** | "9번 물었음" 같은 게 있으면 🔴 어조에 새어나갑니다 |

**턴 지연을 보고 싶다면** — 로그 레벨을 INFO 로 올리면 매 턴 찍힙니다.

```
turn latency 1.235s (senior=... intent=companion) | graph=1.230s
```

**실패의 모습**: `WARNING ... exceeded budget 2.0s` — 2초를 넘긴 것이고, 단계별 내역에서 범인을 찾습니다. 대개 네트워크(문맥 조회·생성·TTS)입니다.

---

### 2.6 에코·barge-in (205)

```bash
cd robot/ai_chat && python -m pytest tests/test_echo_and_bargein.py -v
```

이 테스트가 고정하는 것은 **"에코라고 판정했을 때 올바르게 행동하는가"** 입니다.
**"무엇을 에코로 볼 것인가"의 임계치는 실기에서만 정해집니다.**

🔴 **실기 검증 절차는 별도 문서에 있습니다**: [`docs/hardware/audio-echo-bargein-verification.md`](../hardware/audio-echo-bargein-verification.md)

특히 확인할 것:

| 상황 | 성공 | 실패 |
|---|---|---|
| 로봇이 말하는 중, 아무도 말 안 함 | VAD 가 발화로 판정 안 함 | 판정하면 로봇이 자기 말에 멈춥니다 |
| 로봇이 말하는 중, 어르신이 "응" | 로봇이 **계속** 말함 | 멈추면 문장 하나를 못 끝냅니다 |
| 로봇이 말하는 중, 어르신이 진짜 끼어듦 | 즉시 멈추고 나머지가 큐로 감 | 안 멈추면 양보 정책이 죽은 것 |
| 생존 확인 프로브 중 끼어듦 | 나머지를 **버림** | 재개하면 방금 대답한 사람에게 "괜찮으세요?"를 또 묻습니다 |

---

### 2.7 현관·재실 (208)

```bash
cd robot/ai_chat && python -m pytest tests/test_door_occupancy.py -v
```

44건입니다. **성공/실패의 기준은 "재실 상태가 어떤 값이 되는가"** 입니다. 직접 확인하려면 압축 시계로 돌립니다.

```python
# 문이 열렸다. 로봇은 방향을 모른다.
from bomi_ai_chat.contracts.door import parse_door_event
from bomi_ai_chat.door import intake
from bomi_ai_chat.localstore import runtime as rt

intake.ingest("senior-1", parse_door_event(
    {"eventId": "e1", "type": "DOOR_OPENED", "sourceId": "door-01", "payload": {}}))
print(rt.load("senior-1"))
```

| 확인할 값 | 성공 | 실패했다면 |
|---|---|---|
| `occupancy` | `UNKNOWN` | `HOME` 이면 빈 집에 사다리가 돕니다. `AWAY` 면 집에 있는 사람의 감시가 꺼집니다 |
| `door_open_since` | 0 이 아닌 값 | 0 이면 문 방치를 감지하지 못합니다 |
| `door_heartbeat_at` | 방금 시각 | 0 이면 5분 뒤 "파이가 죽었다"고 오판합니다 |
| `away_since` | 0 | 0 이 아니면 미귀가 시계가 잘못 시작된 것입니다 |

**`AWAY` 는 백엔드만 만듭니다.** 로봇이 스스로 `AWAY` 를 쓰는 코드가 있으면 그것이 버그입니다.

```python
# 백엔드가 방향을 판정해 확정값을 내려준 상황
from bomi_ai_chat.door import occupancy as occ
occ.apply_backend_occupancy("senior-1", "AWAY", observed_at=<외출 시각>)
```

| 확인할 값 | 성공 |
|---|---|
| `occupancy` | `AWAY` |
| `away_since` | 외출 시각 (**다시 AWAY 를 관측해도 갱신되지 않아야 한다**) |

**현관 감시 틱** — outbox 에 무엇이 쌓이는지로 판정합니다.

| 상황 | outbox 에 들어와야 하는 것 | 안 들어오면 |
|---|---|---|
| 문이 20분 넘게 열림 | T2 `door_left_open` | 안전·보안 신호를 놓칩니다 |
| 하트비트 5분 중단 | T2 `door_node_offline` + `occupancy=UNKNOWN` | **현관 감시가 꺼진 것을 아무도 모릅니다** |
| 6시간 미귀가 | T2 `long_absence` | — |
| 12시간 미귀가 | **T1** `not_returned` | 밤을 넘긴 미귀가는 명백한 이상입니다 |
| 야간(23~05시) 외출 | T2 `night_exit` | 배회는 침묵 사다리로 원리적으로 안 잡힙니다 |
| 같은 상황이 계속됨 | **추가 알림 없음** | 매 분 쌓이면 보호자가 알림을 읽지 않게 됩니다 |

**실패의 모습 — 조용한 것들**:

- `occupancy` 가 `AWAY` 에 머무는데 `away_since` 가 0 → 부재 시간을 잴 수 없습니다. 경고 로그가 나옵니다
- 하트비트가 한 번도 안 옴 → 알림은 안 가고 프로세스당 한 번 경고만 나옵니다. `MQTT_ENABLED` 와 라즈베리파이를 확인하십시오
- **인사가 안 나갑니다.** 이건 정상입니다 — 판정하는 쪽(226)이 아직 없습니다

---

## 3. 지금 일부러 실패하는 것들 (정상)

혼동하지 않도록 적어둡니다. **이건 버그가 아니라 아직 안 만든 것입니다.**

| 시도 | 지금 결과 | 언제 고쳐지나 |
|---|---|---|
| "약 먹었어" 라고 말하기 | **정상 처리됨** (206) | — |
| "외로워" 라고 말하기 | 대답 없음 (`handle_emotional` 미구현) | 별도 티켓 |
| "가슴이 아파" 라고 말하기 | **에스컬레이션 안 함** | 210 |
| 어제 얘기 참조 기대 | 잘 안 됨 (키워드 매칭뿐) | 218 |
| 보호자 알림 | 로그만 남음 (채널 미구현) | 211 |
| 능동 발화 (로봇이 먼저 말 걸기) | 안 함 — `build_scheduler()` 를 부트스트랩이 호출하지 않음 | 실기 배선 |
| 현관 인사 (배웅·환영) | **안 함** — 판정하는 쪽이 없음 | 226 |
| 온보딩·재질의 | 안 함 — 백엔드 API 가 없음 | 227 → 209 |

로그에서 이런 경고가 보이면 **정상**입니다:

```
safety triage detector 'self_harm' is NOT IMPLEMENTED (S15P11E102-210)
guardian notification not delivered (no channel configured)
semantic search unavailable; memories ranked by keyword overlap...
```

---

## 4. 무언가 이상할 때 먼저 볼 것

| 증상 | 먼저 확인 |
|---|---|
| 로봇이 아무 말도 안 함 | 로그에 `turn failed` 가 있는지. 미구현 핸들러일 가능성 |
| 로봇이 자기 말에 멈춤 | `ECHO_GUARD_SEC`·`ECHO_VAD_THRESHOLD_MULTIPLIER` (실기 실측 필요) |
| 기억을 못 함 | `availability.semanticSearch` 가 `false` 인지 (218 전이면 정상) |
| 복약을 잘못 말함 | 🔴 즉시 확인. `careRecords` 가 정확 조회로 왔는지, 의미 검색이 섞이지 않았는지 |
| 보호자에게 알림이 안 감 | `outbox` 테이블의 `status`·`last_error`. 채널이 아직 없으면 로그만 |
| 새벽에 말을 검 | `app_user.quiet_hours_start/end` 와 게이트 (206) |
| 침묵 사다리가 안 돎 | `runtime_state.last_user_interaction_at` 이 0 인지. **0 이면 그래프가 내구 저장소에 안 쓰고 있는 것** (208 에서 고친 결함, CONCEPTS §6.1) |
| 문 이벤트가 안 옴 | `MQTT_ENABLED`, `MQTT_BROKER_URL`. 비활성이면 시작 시 경고가 나옵니다 |
| `occupancy` 가 계속 `UNKNOWN` | 정상일 수 있습니다. `AWAY`/`HOME` 은 백엔드 확정값과 발화만 만듭니다 (226 전이면 발화뿐) |
| 문 이벤트 시각이 이상함 | `door node clock is off by ...` 경고. 라즈베리파이 RTC 문제이고 동작은 안전합니다 |
