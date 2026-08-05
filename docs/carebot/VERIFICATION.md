# 직접 돌려보고 판정하기

> **이 문서의 목적**: 코드를 읽지 않고도 "지금 잘 되고 있는가"를 직접 확인한다.
> 각 항목마다 **실행할 명령 / 성공의 모습 / 실패의 모습**을 적었다.

## 0. 준비

> ⚠️ **백엔드 명령은 `be-develop` 체크아웃에서만 유효합니다.** 이 저장소는 라인마다
> 다른 소스를 갖습니다(CLAUDE.md §25). `ai-develop`(이 문서가 있는 라인)의 `backend/`
> 는 `HealthController` 하나만 있는 껍데기라서, `ai-develop` 체크아웃에서
> `./gradlew test` 를 돌리면 `BUILD SUCCESSFUL` 이 나오지만 **실제로는 아무것도 검증하지
> 않습니다.** 이 문서에서 **[be-develop]** 표시가 붙은 절은 `be-develop` 워크트리에서
> 실행하십시오.

```bash
# 로봇 (Python) — ai-develop
cd robot/ai_chat
python -m venv venv && ./venv/Scripts/activate    # Windows
pip install -e ".[dev]"

# 백엔드 (Java 17) — [be-develop] 에서만
cd backend
./gradlew --version
```

백엔드 테스트는 **실제 PostgreSQL 을 자동으로 띄웁니다**(Docker 불필요). 첫 실행에서 PG 바이너리를 내려받느라 1~2분 걸립니다.

---

## 0. 실기로 점검할 때는 별도 문서가 있습니다

마이크·스피커를 쓰는 점검은 문서 세 개를 함께 씁니다. 이 문서(VERIFICATION.md)는 "무엇을 실행하고 무엇을 성공으로 볼지"를 영역별로 적은 참조서입니다.

| 문서 | 성격 |
|---|---|
| [`FIELD-TEST-233.md`](FIELD-TEST-233.md) | **읽기 전용 본문.** 0~11절을 순서대로 따라갑니다 |
| [`FIELD-TEST-233-RESULT.md`](FIELD-TEST-233-RESULT.md) | **적는 곳.** 스텝별 빈칸. 이것만 커밋에 남습니다 |
| [`TRACE-MAP.md`](TRACE-MAP.md) | 발화·함수·DB·API·조절값 대조표. 예상과 실제가 다를 때 폅니다 |

거기에 상태 확인 도구가 하나 붙습니다. 발화 하나가 로컬 저장소의 무엇을 바꿨는지 보여줍니다.

```bash
cd robot/ai_chat
./venv/Scripts/python.exe tests/manual/probe.py --save    # 말하기 전
./venv/Scripts/python.exe tests/manual/probe.py --diff    # 말한 뒤
```

특히 본문의 **3절(에코)을 먼저** 하십시오. 건너뛰면 이후 모든 게이트 버그 리포트가 실제로는 에코입니다.

## 1. 가장 빠른 전체 점검 (2분)

```bash
cd robot/ai_chat && python -m pytest -m "not integration and not manual" -q && python -m ruff check src tests
```

**[be-develop]** 에서만 의미가 있습니다 — `ai-develop` 의 `backend/` 는 껍데기라
`BUILD SUCCESSFUL` 이 나와도 아무것도 검증한 것이 아닙니다(§0).

```bash
cd backend && ./gradlew test
```

| 결과 | 판정 |
|---|---|
| 로봇 `655 passed` + `All checks passed` (2026-08-06 실측, 341 반영) | ✅ |
| **[be-develop]** 백엔드 `BUILD SUCCESSFUL` | ✅ |
| 하나라도 실패 | ❌ — 아래에서 어느 영역인지 좁힌다 |

> 숫자는 티켓이 진행되며 늘어납니다. **줄어들면 누가 테스트를 지운 것**이므로 확인하십시오.

---

### 정서 표현에 대답하는지 (263)

```bash
cd robot/ai_chat && python -m pytest tests/test_emotional_handler.py tests/test_t3_consent.py -q
```

`23 passed` (`test_emotional_handler.py`, 2026-08-06 실측) 여야 합니다. 특히 다음이 이 티켓의 핵심입니다.

| 테스트 | 무엇이 깨지면 잡히는가 |
|---|---|
| `test_a_lonely_utterance_gets_an_answer` | "외로워"에 무응답. 외로움이 1번 문제인데 하필 그 표현에만 침묵하는 상태 |
| `test_the_consent_question_is_not_asked_in_the_same_turn` | 속마음을 꺼낸 직후 "가족분께 전해도 될까요"로 끊는 것. 로봇이 문장 하나로 감시 장치가 됩니다 |
| `test_the_gate_defers_a_proposal_that_is_not_due_yet` | 45분 지연이 장식이 되는 것. 게이트가 `not_before` 를 안 보면 다음 틱에 바로 나갑니다 |

> **253 이 이 흐름을 즉시-큐잉에서 누적-문턱으로 바꿨습니다** — `test_t3_consent.py` 가
> 그 변경의 완료 조건을 검증합니다("외로워" 세 번 이상 + 상위 동의 + 자연스러운 창).
> 자세한 것은 [`FIELD-TEST-233.md` §5-4](FIELD-TEST-233.md#5-4-외로워--이-제품의-1번-문제).

**실기에서 확인할 것**(233): 마이크에 "외로워"라고 말하고 대답이 나오는지, 그 대답에
가족·공유 이야기가 **한 번 말한 정도로는** 섞이지 않는지. **세 번 이상** 말했을 때
`consent_tick` 이 실제로 질문을 큐에 넣는지, 그리고 45분 뒤에야 실제로 나오는지 —
압축 시계로는 `SimClock` 을 advance 해서 볼 수 있지만, 실시간 45분은 실기에서만
확인됩니다. **상위 동의(`guardian_sharing_consent_status`)가 없는 어르신에게는
아무리 말해도 질문이 안 나가야 정상입니다** — 이걸 결함으로 오해하지 마십시오.

### 자연스러운 대화 — 세션·문맥·기억 프라이버시 (WIP 자연대화, 2026-08-06)

```bash
cd robot/ai_chat && python -m pytest tests/test_conversation_session.py tests/test_context_slots.py tests/test_memory_privacy.py -q
```

`43 passed` 여야 합니다 (18+16+9, 2026-08-06 실측). 파일별로 이것이 깨지면:

| 파일 | 무엇이 깨진 것인가 |
|---|---|
| `test_conversation_session.py` | 웨이크워드 게이트(시나리오 A), 세션 중 웨이크워드 생략(B), "이제 됐어" 종료 후 재대기(L), 무응답 종료, **정상 종료된 재생을 끼어들기로 오분류하는 결함(B1)의 재발**, 잘린 발화 나머지의 재경쟁(B2) |
| `test_context_slots.py` | "제주도 가"→"날씨 어때?" 지역 이어짐(D), "그런데" 화제 전환의 문맥 해제(E), "대전 말고 대구" 정정(H), 만료·감쇠 수명 규칙 (CLAUDE.md §30) |
| `test_memory_privacy.py` | 잡담 중 "우리끼리" 봉인, "기억하지 마"의 대기 행 삭제(K), 프로필 성향·만성 부위 프롬프트 반영, 주소 폴백(C 준비) |

**실기에서 확인할 것:** "보미야" 한 번으로 여러 질문이 이어지는지, "이제 됐어" 후
일반 발화에 무반응인지, "제주도 가" 다음 "날씨 어때?"가 제주 날씨인지. 전부
**실기 미실시** 상태입니다.

### 자연스러움 10개 항목 (212)

```bash
cd robot/ai_chat && python -m pytest tests/test_naturalness_replay.py tests/test_degradation.py -q
```

`54 passed` 여야 합니다 (2026-08-06 실측 — 341 이 자연스러움 회귀에 케이스를 추가했습니다).

시나리오는 [`tests/scenarios/naturalness_v1.json`](../../robot/ai_chat/tests/scenarios/naturalness_v1.json) 에 있습니다. **파이썬을 몰라도 케이스를 추가할 수 있습니다** — `turns` 에 어르신 발화를 넣고 `expect` 에 확인할 것을 적으면 됩니다. 파일 안에 쓸 수 있는 키 목록이 있습니다.

**⚠️ 이 세트는 실제 녹취가 아닙니다.** 사람이 작성한 시나리오입니다. 확인하는 것은 두 가지뿐입니다 — 모델에게 무엇이 주어졌는가, 그리고 출력이 규칙을 지켰는가. "따뜻한가", "자연스러운가"는 기계가 못 봅니다. 그 판단은 233 에서 사람이 듣고 합니다.

| 항목 | 여기서 재는가 |
|---|---|
| 1 짧은 턴 / 3 아는 것 재질문 / 4 반복 온기 | ✅ |
| 5 회피 목록 / 7 되묻기 / 8 표현 다양성 / 9 내부 기제 | ✅ |
| 6 말 안 할 때 | ✅ (게이트를 직접 돌립니다) |
| **2 이어짐 / 10 회상** | ❌ 의미 검색 필요 → 218 배포 후 |

가장 중요한 세 개:

| 테스트 | 깨지면 잡히는 것 |
|---|---|
| `test_every_tuning_dial_has_a_reader` | **policy.py 에 있는데 아무도 읽지 않는 상수.** 실제로 `DEGRADATION_ORDER` 가 그랬습니다 |
| `test_the_module_offers_no_way_to_weaken_safety` | 저하 모듈이 침묵 사다리·트리아지·outbox 를 약하게 만들 수 있게 되는 것 |
| `test_the_scenario_file_covers_every_criterion_or_says_why_not` | 항목이 조용히 사라지는 것. 시나리오를 지우면 커버리지가 줄어드는데 테스트는 통과합니다 |

### 성능 저하 순서를 눈으로 보기

```bash
cd robot/ai_chat && python -c "
from bomi_ai_chat import degradation, policy
for i in range(5):
    print(f'level {degradation.level()}: top_k={degradation.memory_top_k()} '
          f'docs={degradation.documents_allowed()} ambient={degradation.ambient_allowed()}')
    for _ in range(policy.DEGRADE_AFTER_SLOW_TURNS):
        degradation.note_turn_latency(policy.TURN_LATENCY_BUDGET_SEC + 1)
"
```

단계가 오를수록 `top_k` 가 줄고, 문서가 끊기고, 잡담이 끊겨야 합니다. **`probes_simplified()` 는 어느 단계에서도 True 입니다** — 프로브는 처음부터 캐시 음성이고, 그것이 네트워크가 끊긴 순간에도 생존 확인이 나가는 이유입니다.

## 2. 영역별 검증

### 2.1 주입 시계 — 하루가 10초에 흐르는가 (200)

```bash
cd robot/ai_chat && python -m pytest tests/test_clock.py -v
```

**성공**: `test_sim_clock_flows_one_day_in_ten_real_seconds` 통과
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

### 2.3 백엔드 스키마 — 빈 DB 에서 마이그레이션이 도는가 (201) **[be-develop]**

```bash
cd backend && ./gradlew test --tests "com.ssafy.bomi.migration.FlywayMigrationValidationTest"
```

이 테스트가 실제로 하는 일: **빈 PostgreSQL 을 띄우고 → V1 부터 최신 V파일까지 순서대로 실행하고 → Hibernate 로 엔티티와 대조**합니다. 정확한 파일 개수는 이 문서가 아니라 `FlywayMigrationValidationTest.migrationsApplyToEmptyDatabaseAndEntitiesValidate()` 의 `containsExactly(...)` 목록이 갖습니다 — 숫자를 여기 다시 적으면 새 V파일이 생길 때마다 이 문서가 또 낡습니다.

| 실패 메시지 | 의미 |
|---|---|
| `Schema-validation: missing column ...` | 엔티티를 바꾸고 마이그레이션 V파일을 안 만들었다 |
| `Migration checksum mismatch` | 🔴 **이미 적용된 V파일을 수정했다.** 배포가 터진다 |
| `migration N must have applied successfully` | 그 V파일의 SQL 이 잘못됐다 |

새 V파일을 추가했다면 이 테스트의 기대 목록(`containsExactly("1","2",...)`)도 늘려야 합니다. 안 늘리면 실패하는데, **그게 의도**입니다 — 파일만 만들고 검증을 잊는 것을 막습니다.

---

### 2.4 문맥 조립 API — 6종이 다 오는가 (203) **[be-develop]**

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
  "availability": { "semanticSearch": false, "documentCorpus": false, "notes": [...] },
  "retrieval": {
    "semanticRequested": true,
    "semanticUsed": false,
    "fallbackReason": "embedding_disabled",
    "hitCount": 0,
    "latencyMs": 7
  }
}
```

`retrieval`은 BE 계약 확장 전까지 없을 수 있습니다. 그때 로봇은 값을 `false`로
지어내지 않고 "모름"으로 둡니다. BE 확장 뒤에는 `availability`가 기능 가용성,
`retrieval`이 이번 요청의 실제 실행 결과인지 반드시 따로 확인합니다.

| 확인 항목 | 성공 | 실패 |
|---|---|---|
| `memories` 개수 | 요청한 `memoryTopK` 이하 | 20개씩 오면 과적재 방지가 깨진 것 |
| `availability.semanticSearch` | 지금은 `false` **가 정상** (218 은 이미 완료됐지만 임베딩 과금 때문에 `EMBEDDING_ENABLED` 기본값이 off) | `true` 인데 명시적으로 켠 적이 없으면 거짓 보고 |
| `retrieval.semanticRequested/semanticUsed` | 요청·실행 여부가 실제 폴백과 일치 | 임베딩 실패인데 `semanticUsed=true`, 또는 필드 없이 성공으로 간주 |
| `retrieval.fallbackReason` | `semanticUsed=false`이면 운영자가 이해할 수 있는 사유 | 빈 값이라 폴백 원인을 추적할 수 없음 |
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
cd robot/ai_chat && python -m pytest tests/test_graph_build.py tests/test_turn_end_to_end.py tests/test_prompt_builder.py -v
```

`test_information_turn_requests_documents_and_preserves_retrieval_evidence`가 다음을 한 번에
검증합니다: `classify_intent → includeDocuments=true → 문서 출처·버전·청크·인용 →
retrieval_status → 최종 프롬프트`. 실제 Spring Boot·Qdrant까지 포함하는 검증은 BE
브랜치의 교차 모듈 E2E가 생기기 전까지 `UNVERIFIED`입니다.

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
- **인사가 실기에서 검증되지 않았습니다.** 판정 로직(226)은 만들어졌지만, `backend_command` 경로로 실제 인사가 나가는 것은 아직 실기로 확인되지 않았습니다(PROGRESS.md §2.1)

### 2.8 계약 주도형 대화 — 온보딩·재질의 (209, 227)

```bash
cd robot/ai_chat && python -m pytest tests/test_contract_dialogue.py -v
```

아래는 **[be-develop]** 에서만 돌릴 수 있습니다:

```bash
cd backend && ./gradlew test --tests "*RobotOnboarding*" --tests "*RobotClarification*"
```

**성공/실패의 기준은 "무엇이 확인으로 인정되는가"입니다.** 이것만 직접 확인해 보십시오.

```python
from bomi_ai_chat.graph import contract_dialogue as cd
cd.read_affirmation("네")                 # True  — 확인
cd.read_affirmation("아니요")             # False — 거절
cd.read_affirmation("글쎄")               # None  — 다시 묻기
cd.read_affirmation("오늘 날씨가 좋네")    # None  ← "네"가 걸리면 안 됩니다
cd.read_affirmation("그래서 어제 병원에 갔는데 의사가 그러더라")  # None
```

| 결과 | 뜻 | 틀렸다면 |
|---|---|---|
| `True` | 확정한다 | 오탐이면 **동의한 적 없는 동의가 기록됩니다** |
| `False` | 거절로 기록 | 오탐이면 딸린 질문이 영영 안 나옵니다 |
| `None` | 다시 묻는다 | 이것이 애매할 때의 정답입니다 |

**동의 판정에 LLM 이 쓰이면 실패입니다.** 대역 LLM 의 호출 횟수가 0 이어야 합니다 — `test_consent_is_never_decided_by_the_model` 이 그것을 봅니다.

서버 쪽에서 확인할 것:

| 상황 | 성공 | 실패했다면 |
|---|---|---|
| 건강정보 동의 전 `next` 호출 | 동의 질문이 먼저 내려옴 | 복약 질문이 내려오면 **계약 위반** |
| 동의 거절 후 | 딸린 질문이 안 내려오고 세션 COMPLETED | 되물으면 거절을 무시한 것 |
| 활성 후보 3건 | `active` 가 1건 | 여러 건이면 어르신이 연달아 심문받습니다 |
| 복약 3필드 누락 | 응답 `missingFields` 1개, DB `missing_fields` 3개 | DB 도 1개면 나머지가 빈 채로 확정됩니다 |
| 확인 없는 민감 답변 | `verification_status=UNVERIFIED`, `confirmed_at` **NULL** | 시각이 있으면 "동의했다"는 근거가 됩니다 |

**실패의 모습 — 조용한 것들**:

- 로봇이 `"GRANTED"` 나 `"{}"` 를 말한다 → 내부 값이 TTS 로 샜습니다(둘 다 회귀 테스트로 고정)
- 필드명(`dose`)을 소리내어 읽는다 → 돌봄 로봇이 아니라 서식입니다
- 백엔드가 죽었는데 온보딩이 진행된다 → **계약 없이 민감정보를 묻고 있습니다**

### 2.9 안전 트리아지 (210)

```bash
cd robot/ai_chat && python -m pytest tests/test_safety_triage.py -v
```

**성공/실패의 기준은 "무엇을 부르고 무엇을 넘기는가"입니다.**

```python
from bomi_ai_chat.graph import triage
triage.safety_triage({"senior_id": "s1", "user_input": "무릎이 아파"})["safety_level"]
```

| 발화 | 기대 | 틀렸다면 |
|---|---|---|
| `"무릎이 아파"` | `none` | `confirm` 이면 **가장 흔한 말마다 보호자를 부릅니다** |
| `"가슴이 아파"` | `confirm` | `none` 이면 놓칩니다 |
| `"안 아파"` | `none` | `confirm` 이면 괜찮다는 사람 때문에 보호자가 호출됩니다 |
| `"어제 가슴이 아팠어"` | `none` | — |
| `"어제부터 가슴이 아파"` | `confirm` | `none` 이면 이틀째 아픈 분이 걸러집니다 |
| `"넘어졌어요"` | `confirm` | `none` 이면 시제 어미로 억제한 것입니다 |
| `"아들한테 전화해줘"` | `T1` | 확인 질문을 하면 이미 확인한 것을 또 묻는 것입니다 |
| `"이제 그만 살고 싶어"` | `T1` | — |
| `"더워 죽겠네"` | `none` | `T1` 이면 강조 표현을 자해로 읽은 것입니다 |

확인 질문 이후:

| 어르신의 답 | 기대 |
|---|---|
| `"아니야 괜찮아"` | `none` — 취소 |
| `"글쎄"`, `"몰라"`, 다른 이야기 | **`T1`** — 애매하면 부릅니다 |
| (무응답 90초) | **`T1`** — `silence_tick` 이 부릅니다 |

outbox 에서 확인할 것:

```python
from bomi_ai_chat.localstore import outbox
outbox.pending_count()      # T1 적재 직후 1
```

| 확인 | 성공 |
|---|---|
| 네트워크 차단 중 flush | 대기 건수가 **줄지 않음** (버려지지 않는다) |
| payload | `occupancy`·`rest_state` 포함, **발화 원문 없음** |
| 어르신에게 간 말 | 진단·티어 이름 없음 |

**정상인 경고 하나**: `self-harm marker list has not been human-reviewed yet` — 판별기는 동작하며, 목록 검토가 남았다는 뜻입니다(PROGRESS §2.2).

---

## 3. 지금 일부러 실패하는 것들 (정상)

혼동하지 않도록 적어둡니다. **이건 버그가 아니라 아직 안 만든 것입니다.**

| 시도 | 지금 결과 | 언제 고쳐지나 |
|---|---|---|
| "약 먹었어" 라고 말하기 | **정상 처리됨** (206) | — |
| "가슴이 아파" 라고 말하기 | **정상 처리됨** (210) | — |
| 어제 얘기 참조 기대 | 잘 안 됨 (키워드 매칭뿐 — 의미 검색은 218 에서 만들어졌지만 임베딩 과금 때문에 기본값이 꺼짐) | `EMBEDDING_ENABLED`·`EMBEDDING_SYNC_ENABLED` 를 켜면 (§2.4) |
| 보호자 알림 | **백엔드로 전달됨** (211). 화면 표시는 웹 대시보드 | — |
| `memory`/`care_record` 최종 반영 | 후보가 CONFIRMED 에 머묾 | 별도 티켓 |

> **"외로워"(263), 능동 발화 스케줄러 배선(232), 현관 인사 판정(226), 온보딩·재질의 계약
> API(227) 는 이 표에서 빠졌습니다.** 전부 머지되어 더 이상 "아직 안 만든 것"이 아닙니다 —
> 최신 머지 상태는 PROGRESS.md §1 을 보십시오. "외로워"는 이 문서 §1 의 정서 표현 절에서
> 검증합니다. 나머지는 코드는 있으나 실기 검증이 남은 상태이고, 그것은 "아직 안 만든
> 것"과 다른 위험이라 이 표(**의도적 미구현**)가 아니라 PROGRESS.md 의 위험 목록에서
> 다룹니다.

로그에서 이런 경고가 보이면 **정상**입니다:

```
self-harm marker list has not been human-reviewed yet (docs/carebot/PROGRESS.md §2.2)
guardian notification not delivered (no channel configured)
semantic search unavailable; memories ranked by keyword overlap...
```

---

## 4. 무언가 이상할 때 먼저 볼 것

| 증상 | 먼저 확인 |
|---|---|
| 로봇이 아무 말도 안 함 | 로그에 `turn failed` 가 있는지. 미구현 핸들러일 가능성 |
| 로봇이 자기 말에 멈춤 | `ECHO_GUARD_SEC`·`ECHO_VAD_THRESHOLD_MULTIPLIER` (실기 실측 필요) |
| 기억을 못 함 | `availability.semanticSearch` 가 `false` 인지 (218 은 완료됐지만 `EMBEDDING_ENABLED` 기본값이 꺼짐이면 정상) |
| 복약을 잘못 말함 | 🔴 즉시 확인. `careRecords` 가 정확 조회로 왔는지, 의미 검색이 섞이지 않았는지 |
| 보호자에게 알림이 안 감 | `outbox` 테이블의 `status`·`last_error`. 채널이 아직 없으면 로그만 |
| 새벽에 말을 검 | `app_user.quiet_hours_start/end` 와 게이트 (206) |
| 침묵 사다리가 안 돎 | `runtime_state.last_user_interaction_at` 이 0 인지. **0 이면 그래프가 내구 저장소에 안 쓰고 있는 것** (208 에서 고친 결함, CONCEPTS §6.1) |
| 문 이벤트가 안 옴 | `MQTT_ENABLED`, `MQTT_BROKER_URL`. 비활성이면 시작 시 경고가 나옵니다 |
| `occupancy` 가 계속 `UNKNOWN` | 정상일 수 있습니다. `AWAY`/`HOME` 은 백엔드 확정값과 발화만 만듭니다. 226 은 완료됐지만 인사가 실기로 검증된 적은 없습니다(§2.7) |
| 문 이벤트 시각이 이상함 | `door node clock is off by ...` 경고. 라즈베리파이 RTC 문제이고 동작은 안전합니다 |
