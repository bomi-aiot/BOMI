# 코드 읽는 순서

> **이 문서의 목적**: 어디부터 읽을지, 각 파일에서 **무엇을 봐야 하는지** 알려준다.
> 전부 읽을 필요는 없다. 목적별 경로를 §5 에 두었다.

읽기 전에 [CONCEPTS.md](CONCEPTS.md) 의 §1(용어)만 훑으면 훨씬 수월합니다.

---

## 1. 30분 코스 — 전체 구조를 잡는다

이 순서로 읽으면 "무엇이 어디에 있는지"가 잡힙니다.

| 순서 | 파일 | 여기서 볼 것 |
|---|---|---|
| 1 | `CLAUDE.md` §1, §5, §6 | 무엇을 만드는지, 누가 무엇을 소유하는지, 노드 그림 |
| 2 | `robot/ai_chat/src/bomi_ai_chat/state.py` | **한 턴에 흐르는 값 전부.** 이 파일이 곧 목차다 |
| 3 | `.../graph/build.py` | 노드 배선. 로직 없음. 그림(§6)과 대조하며 읽는다 |
| 4 | `.../policy.py` | 로봇의 '성격'. 숫자만 읽어도 행동을 예측할 수 있다 |
| 5 | `docs/carebot/PROGRESS.md` | 지금 무엇이 되고 무엇이 안 되는지 |

**2번이 핵심입니다.** 노드들은 서로를 import 하지 않고 오직 `ConvState` 의 키 이름에만 합의합니다. 그래서 이 파일을 읽으면 노드 간 계약을 전부 본 셈이 됩니다.

---

## 2. 대화 한 턴을 따라가기

어르신이 "무릎이 아파" 라고 말했을 때 무슨 일이 일어나는지, 실행 순서대로:

| 순서 | 파일 | 하는 일 |
|---|---|---|
| 1 | `graph/turn.py` | STT 텍스트를 받아 그래프를 호출. 지연 측정 시작 |
| 2 | `graph/ingress.py` `note_interaction` | 사다리 리셋, occupancy=HOME, **barge-in 판단** |
| 3 | `graph/triage.py` `safety_triage` | 안전 분류 (**지금 미구현 — 항상 통과**) |
| 4 | `graph/context.py` `context_read` | 백엔드에서 문맥 조회, 실패 시 캐시 |
| 5 | `graph/context.py` `classify_intent` | 로컬 규칙으로 인텐트 결정 (LLM 안 씀) |
| 6 | `graph/handlers.py` `_generate` | **이 턴의 유일한 LLM 호출** |
| 7 | `prompts/builder.py` `build_prompt` | 프롬프트 조립 (순수 함수) |
| 8 | `graph/output.py` `response_shaper` | 문장 분할, 개수 제한 |
| 9 | `graph/output.py` `emit` | 재생 시작 (**블로킹하지 않음**) |
| 10 | `audio/playback.py` | 문장을 하나씩 합성·재생 |

각 파일의 모듈 docstring 첫 문단이 "이 파일이 어디에 위치하는가"를 설명합니다.

### 2.1 문이 열렸을 때 (208)

대화 턴과 **완전히 다른 경로**입니다. 어디서 끝나는지를 보십시오.

| 순서 | 파일 | 하는 일 |
|---|---|---|
| 1 | `door/mqtt.py` `handle_payload` | 브로커에서 bytes 하나를 받는다 |
| 2 | `contracts/door.py` `parse_door_event` | 봉투 검증, **시각을 도착 시각으로 정규화** |
| 3 | `door/intake.py` `ingest` | 하트비트, 문 개폐, 보수적 재실, 백엔드 전달 |
| 4 | `door/occupancy.py` `set_occupancy` | **낡은 관측을 버린다.** `away_since` 유지 |
| 5 | `graph/ingress.py` `door_event` | checkpoint 에도 반영하고 **END** |

**5번에서 끝납니다.** 인사 제안이 없습니다 — 판정은 백엔드(226)이고, 그 결과는 `backend_command` 로 다시 들어옵니다.

주기 감시는 별도입니다: `jobs/ticks.py` `door_watch_tick` — 하트비트, 문 방치, 미귀가, 야간 배회.

---

## 3. 서버 쪽 (백엔드)

| 순서 | 파일 | 여기서 볼 것 |
|---|---|---|
| 1 | `docs/database/mvp-erd.md` §9 | 문맥 조립 레시피. **이것이 계약이다** |
| 2 | `context/api/ConversationContextResponse.java` | 로봇이 받는 것 전부. 응답 모양이 곧 명세 |
| 3 | `context/application/ConversationContextService.java` | 조립 로직. **§5 선필터가 핵심** |
| 4 | `memory/repository/MemoryRepository.java` | `findRetrievable` — 프라이버시 통제가 이 쿼리다 |
| 5 | `backend/src/main/resources/db/migration/V2~V5` | 로봇 런타임이 쓰는 컬럼들 |

**4번을 반드시 보십시오.** 이 쿼리 하나가 "누가 어떤 기억을 볼 수 있는가"를 결정합니다. 여기가 틀리면 보호자에게 어르신의 속마음이 새어 나갑니다.

---

## 4. 파일별 한 줄 안내

### 로봇 (`robot/ai_chat/src/bomi_ai_chat/`)

| 파일 | 한 줄 |
|---|---|
| `clock.py` | 시간을 읽는 **유일한** 곳. 압축 시계로 하루를 10초에 |
| `policy.py` | 제품 판단 상수. `config.py`(환경변수)와 성격이 다르다 |
| `config.py` | 환경변수. 배포마다 바뀌는 값 |
| `state.py` | 한 턴의 상태 스키마 + `SpeechProposal` |
| `turn_timer.py` | 턴 지연 실측. `clock` 이 아니라 `monotonic` 을 쓰는 이유가 적혀 있다 |
| `graph/build.py` | 배선만 |
| `graph/ingress.py` | 진입 **4경로** + barge-in. `door_event` 가 왜 END 로 끝나는지 여기 |
| `graph/gate.py` | 능동 발화 게이트 (**206 에서 채움**) |
| `graph/triage.py` | 안전 분류 (**210 에서 채움**) |
| `graph/context.py` | 문맥 조회 + 인텐트 분류 |
| `graph/handlers.py` | 7개 핸들러 (**6개 구현됨**, `handle_emotional` 만 남음) |
| `graph/output.py` | 정제 + 재생 시작 |
| `graph/turn.py` | 반응형 한 턴 실행 |
| `prompts/builder.py` | 프롬프트 조립 (순수 함수) |
| `prompts/templates/*.md` | 실제 프롬프트 문구. **여기를 고치면 로봇 말투가 바뀐다** |
| `graph/contract_dialogue.py` | **무엇을 LLM 에게 맡기지 않는가.** 확인 판정의 규칙 |
| `backend_client/contract_client.py` | 온보딩·재질의 API. **실패하면 예외** (문맥 조회와 반대) |
| `contracts/door.py` | 기기 경계를 넘는 메시지 형태. **여기를 고치는 것은 호환성 결정** |
| `door/occupancy.py` | 재실 규칙. **"발화가 센서를 이긴다"가 여기서 시각 비교로 표현된다** |
| `door/intake.py` | 문 이벤트 하나의 처리. 저장소가 두 개인 이유가 여기 적혀 있다 |
| `door/mqtt.py` | 브로커 구독. 판정 로직이 없어서 브로커 없이 테스트된다 |
| `backend_client/` | 어르신의 사실·기억으로 가는 유일한 길 |
| `localstore/db.py` | **DB 파일이 왜 두 개인지**가 여기 적혀 있다 |
| `localstore/outbox.py` | 보호자 알림 큐. 전송보다 저장이 먼저 |
| `localstore/runtime.py` | 재부팅을 넘는 운영 상태. **틱이 읽는 쪽** |
| `localstore/schema.py` | 표 정의 + 뒤늦게 추가한 컬럼의 멱등 마이그레이션 |
| `localstore/proposals.py` | 게이트가 심판할 대기 목록 |
| `audio/echo_guard.py` | 자기 목소리를 걸러내는 판정 |
| `audio/playback.py` | **진행 상황의 권위.** 동기화 버그가 가장 나기 쉬운 곳 |
| `notify/base.py` | 보호자 채널 어댑터 인터페이스 |
| `jobs/ticks.py` | 주기 작업. `daily_summary_job` 만 미구현(→ 211, 백엔드로 이동) |

### 이미 있던 것 (재구현하지 않음)

| 파일 | 역할 |
|---|---|
| `llm/client.py` | Gemini 호출 |
| `llm/router.py` | 의료 질의 판정 (**로컬** 임베딩) |
| `stt/`, `tts/` | 외부 API 클라이언트 |
| `weather/`, `db/` | 날씨, 의료 참조 조회 |
| `audio_io/` | 장치 입출력. `audio/`(판단)와 다르다 |
| `pipeline.py` | 입력 루프 드라이버. **아직 그래프에 연결 안 됨** |

---

## 5. 목적별 경로

| 알고 싶은 것 | 읽을 것 |
|---|---|
| 로봇이 언제 말하는가 | `CLAUDE.md` §7 → `policy.py` 우선순위 표 → `graph/gate.py` |
| 로봇이 왜 이렇게 말하는가 | `prompts/templates/system.md` → `prompts/builder.py` |
| 무엇을 기억하는가 | `CLAUDE.md` §8 → `MemoryRepository.findRetrievable` → `ConversationContextService` |
| 언제 보호자를 부르는가 | `CLAUDE.md` §9 → `localstore/outbox.py` → `graph/triage.py` |
| 어르신이 끼어들면 | `CLAUDE.md` §13 → `audio/playback.py` → `graph/ingress.py` |
| 오프라인이면 | `backend_client/context_client.py` → `localstore/context_cache.py` |
| 왜 이 숫자인가 | `policy.py` — 모든 상수에 "올리면/내리면"이 적혀 있다 |

---

## 6. 읽을 때 알아두면 좋은 것

**주석이 코드보다 많은 파일이 있습니다.** 의도적입니다. CLAUDE.md §2 가 "팀 대부분이 LangChain·RAG 경험이 없다"고 전제하고, 주석을 산출물로 규정합니다. 특히 `왜 존재하는가` / `주의사항` 절이 설계 판단을 담고 있습니다.

**"이게 없으면 무엇이 깨지는가"가 자주 적혀 있습니다.** 그 문장이 그 코드의 존재 이유입니다. 예:

> 이 컬럼이 없으면 "아무도 움직이지 않았다"와 "라즈베리파이가 죽었다"를 구분할 수 없다.

**한글 주석 / 영문 식별자**가 규칙입니다(§21). 백엔드 Java 는 영문 Javadoc 이 기존 관례라 그쪽을 따릅니다.
