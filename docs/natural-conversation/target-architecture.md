# 자연스러운 대화 — 목표 아키텍처 (target-architecture)

작성일: 2026-08-06 · 전제: [current-state-audit.md](current-state-audit.md), [implementation-plan.md](implementation-plan.md)

> **구현 반영 (2026-08-06):** §2 의 `context_candidates` 와 §3(ContextCandidate·수명 규칙·
> 선택 우선순위)은 구현되어 CLAUDE.md §30 으로 승격됐다 — 이제 §30 이 권위다. §4 세션
> FSM 도 구현됐다(`conversation_control.SessionState`). `session_state` 스냅샷 필드와
> `pending_tool_action` 은 계획대로 **도입하지 않았다**(쓰는 곳이 생길 때 추가 — 미사용
> 필드 금지 원칙). 감사 §0 해소 현황 참고.

설계 원칙: **새 서비스·새 프레임워크·새 테이블을 만들지 않는다.** 요청서의 책임 목록을 기존 모듈에 사상(mapping)하고, 없는 것만 기존 자리에 추가한다. 기존 그래프 구조(§6)·게이트(§7)·기억 경계(§8)·ERD 어휘(§4)는 그대로 유지된다.

---

## 1. 책임 사상표 — 요청서 이름 → 실제 모듈

| 요청서 책임 | 사상 | 상태 |
| --- | --- | --- |
| WakewordGate | `audio_io/wakeword.py` + `bootstrap.run_conversation_loop`의 블로킹 대기 | **기존 유지** (변경 없음, 테스트만 추가) |
| ConversationSessionManager | `conversation_control.py`(규칙·전이 함수) + `bootstrap._run_graph_conversation`(구동) | **Phase 1에서 명시화** — 새 모듈 만들지 않음 |
| ConversationState | LangGraph `ConvState`(`state.py`) 확장 | **기존 확장** — 아래 §2 |
| ContextResolver | `graph/ingress.py`(후보 수명) + `graph/context.py`(조회 파라미터 해석) | **Phase 2 신규 로직, 기존 노드 안에** |
| UserProfileProvider | `backend_client/context_client.py` + `localstore/context_cache` | **기존 유지** — 미사용 필드 활용만 추가 |
| MemoryService | `backend_client/` (문맥조립·fact_client) + `localstore/extraction` | **기존 유지** |
| MemoryPolicy | `graph/build.py:_enqueue_extraction`의 스킵 조건 7종 + `policy.py` | **기존 유지** — 봉인 검사 범위만 확장(Phase 5) |
| ReferenceResolver | `graph/context.py`의 조회 파라미터 해석 한정 (문장 복원은 LLM+recentMessages 유지) | **Phase 2 신규(제한적)** |
| IntentAndEmotionAnalyzer | `graph/context.py:classify_intent` + `llm/router.py` | **기존 유지** |
| ResponsePolicy | `graph/output.py:response_shaper` + `prompts/templates/` | **기존 유지** — 리플레이 판정만 확장 |
| ToolExecutionPolicy | `graph/context.py:_gather_lookup_documents`(읽기 도구) + `pending_tool_action`(행동 도구, 미래) | **Phase 2/6** |
| ConversationOrchestrator | `graph/build.py`(배선) + `graph/turn.py`(구동) | **기존 유지** |
| ConversationEventRecorder | `graph/build.py:_record_turn` + (신규) 구조화 이벤트 로거 | **Phase 7** |

새 클래스 이름을 위해 파일을 만들지 않는 이유: 이 저장소는 "핸들러는 I/O 금지, backend_client만 서버 접근, localstore만 SQLite 접근"(§20)이라는 책임 경계가 이미 서 있고, 요청서의 책임들은 그 경계와 1:1로 겹친다. 이름을 더 얹으면 어휘만 늘어난다(§4의 교훈).

---

## 2. ConversationState — `ConvState` 확장안

기존 41개 필드는 그대로 두고 다음만 추가한다 (`state.py`):

```python
# 추가 필드 (전부 total=False, 구 체크포인트와 호환되게 .get() + 기본값으로만 읽는다)
session_state: str            # IDLE/LISTENING/PROCESSING/RESPONDING/ENDING — 관측용 스냅샷.
                              # 권위는 bootstrap 루프. 그래프는 기록만 한다.
context_candidates: list[ContextCandidate]   # 아래 §3. 유일한 신규 "문맥" 저장소.
retrieval_status: RetrievalStatus            # 기능 가용성과 이번 요청의 실제 검색·폴백을 분리.
                                              # 계약 고정(666ae0d + BE 0436b71 머지). 구버전
                                              # 응답에는 필드가 없을 수 있고 그때는 '모름' 유지.
pending_tool_action: dict | None             # 행동형 도구 확인 대기. 현재 도구는 읽기 전용이라
                                             # Phase 6 전까지 항상 None.
```

요청서의 `current_topic`/`current_location`/`current_people`/`current_event` 를 **개별 필드로 만들지 않는다.** 전부 `context_candidates`의 `type`으로 표현한다. 이유:

1. LastValue 채널의 상태 누수(감사 E1 — 실제 사고 3건)는 필드 수에 비례해 늘어난다. 수명 관리 코드를 한 곳(`note_interaction`)에 모으려면 저장소도 하나여야 한다.
2. `recent_turns`는 이미 서버 `recentMessages`가 담당한다. 로봇 복제본을 만들면 §5의 "사실은 백엔드 권위" 원칙과 충돌한다.
3. `current_intent`/`current_emotion`은 기존 `intent` 필드와 감정 신호 카운터가 이미 있다.
4. `current_time_reference` — 현재 날짜·시각은 이미 매 요청 `[현재 정보]` 블록으로 주입된다(`llm/client.py:85`). "내일"류 상대 표현의 문장 해석은 이 주입+LLM으로 충분하고, **조회 파라미터로서의 날짜**(내일 날씨 등)는 EVENT 후보의 시각 필드로 다룬다. 별도 TIME 타입을 만들지 않는다.
5. `last_robot_action` — 직전 로봇 발화는 이미 두 곳에 있다: 추출용 `preceding_robot_utterance`(`build.py:215-227`)와 서버 `recentMessages`의 마지막 ROBOT 행. 시나리오 I("목소리라도 들을까?" → 그때 제안)의 "로봇이 방금 무엇을 제안했는가"가 필요해지는 Phase 6에서 `pending_tool_action`에 제안 이력을 담는 것으로 충분하며, 별도 필드를 추가하지 않는다.

### 수명 규칙 (결정론, `note_interaction`에서 매 턴 실행)

```text
1. 만료: clock.now() > expires_at → 제거      (§15 — clock.py 경유 필수)
2. 감쇠: 관련 없는 발화가 이어지면 confidence *= DECAY  (다이얼은 policy.py)
3. 정정: 같은 type의 명시 후보 등장 → 기존 후보 교체 (시나리오 H)
4. 리셋: 세션 종료(ENDING) → scope=SESSION 후보 전체 제거.
         scope=SCHEDULED_EVENT는 일정 시각까지 유지 (시나리오 F·J).
```

## 3. ContextCandidate

```python
ContextCandidate = TypedDict("ContextCandidate", {
    "type": str,          # LOCATION / PERSON / EVENT / TOPIC
    "value": str,         # "제주도"
    "source": str,        # USER_EXPLICIT / SCHEDULE / PROFILE_DEFAULT / INFERRED
    "related_topic": str, # "주말 여행" — 감쇠 판정의 근거
    "confidence": float,  # USER_EXPLICIT=1.0, INFERRED<1.0
    "scope": str,         # SESSION / SCHEDULED_EVENT / STANDING(프로필 기본값)
    "created_at": float,  # clock.now()
    "expires_at": float,  # scope별 기본 TTL — policy.py 다이얼
    "last_used_at": float,
}, total=False)
```

### 문맥 선택 우선순위 (요청서 순서를 그대로 채택, 구현 지점 명시)

```text
1. 현재 발화의 명시 정보          extract_city 등 — 항상 최우선, 후보 갱신도 여기서
2. 활성 SESSION 후보 (미만료·임계 이상)
3. SCHEDULED_EVENT 후보           careRecords에서 파생 (Phase 3, BE 협의)
4. (현재 체류지 — 신호원 없음: 미지원으로 명시. GPS·일정 외 체류 정보가 생기면 추가)
5. STANDING 후보 = app_user 주소   BE 계약 확장 후 (Phase 3)
6. 확인 질문                       후보 없음 → 현행 유지("어느 지역이요?")
```

**안전 제한**: 건강·안전·금전 관련 실행은 confidence < 1.0(비명시) 후보로 수행하지 않는다. 의료 조회의 기존 확인 게이트(`medical_flow.py:246-297` — 부분 일치·자모 보정 시 되묻기)가 이 원칙의 선례이며 그대로 유지한다.

---

## 4. 세션 상태 머신 (Phase 1)

```text
IDLE ── 웨이크워드 ──> LISTENING ── 발화 확정 ──> PROCESSING ── emit ──> RESPONDING
 ^                        │  onset 15s 초과                                  │ 재생 완료
 │                        v                                                  v
 └── ENDING <── 작별 문구 ┴──────────────────────────────── LISTENING (루프)
```

- 전이 함수는 `conversation_control.py`에 **순수 함수**로 둔다(오디오 없이 테스트 가능 — §15의 clock 주입과 같은 동기).
- 권위는 여전히 `bootstrap` 루프다. enum은 루프의 위치를 이름으로 바꾼 것이지 새 제어 흐름이 아니다.
- LangGraph 체크포인터에는 스냅샷(`session_state`)만 남긴다 — 관측·디버깅용. 세션 자체를 서버·체크포인트에 "복원"하지 않는다(재부팅 후 대화를 이어가는 것은 오히려 부자연스럽고, 웨이크워드 재요구가 옳다).
- 감정 대화의 침묵(시나리오 M): 직전 인텐트가 emotional이면 LISTENING onset 타임아웃을 `policy.EMOTIONAL_IDLE_TIMEOUT_SEC`(신설 다이얼)로 연장.

---

## 5. 기억 분리 — 기존 구조 사상 (새 테이블 없음)

| 요청서 범위 | 실제 자리 | 비고 |
| --- | --- | --- |
| SESSION | `ConvState.context_candidates` (체크포인터) + 서버 `recentMessages` | 세션 종료 시 소멸 |
| SHORT_TERM_EVENT | 서버 `conversation_summary` + `care_record` 관찰 + fact_candidate(factType 확장) | Phase 4. 후속 확인은 proposal로 |
| LONG_TERM_PROFILE | `app_user` + `memory` (ERD §8 push/pull 경계 그대로) | 변경 없음 |
| RELATIONSHIP_MEMORY | `memory` (PERSONAL_RELATIONSHIP) | 이미 추출 어휘에 존재 (`fact_contract.py:41-47`) |
| SENSITIVE_MEMORY | `fact_candidate`(SENSITIVE) + `memory.visibility` + T4 봉인 | visibility "robot only" 값은 §24 미결 — BE 확인 필요 |

요청서의 기억 속성(`importance`/`confidence`/`source`/`expires_at`/`consent_scope`/`status`)은 ERD의 `memory.importance`, `fact_candidate`의 확인 상태, 동의 플래그가 이미 담당한다. **중복 테이블을 만들지 않는다** — 요청서 자신도 이를 요구한다.

## 6. 정책 계층 분리 (요청서 "응답 생성 정책" 대응)

| 계층 | 자리 | 예 |
| --- | --- | --- |
| 결정론 애플리케이션 규칙 | 그래프 노드 + `policy.py` | 웨이크워드, 세션 전이, 문맥 수명, T1~T4, 추출 스킵, 봉인 |
| 구조화된 문맥 | `build_prompt` 9단계 (`prompts/builder.py`) | 프로필·기억·최근 대화·조회 결과 |
| LLM 응답 스타일 | `prompts/templates/*.md` | 길이·호칭·감정 단정 금지·기계 언급 금지 |
| 도구 실행 허용 | `context.py` 조회 자격 + (미래) `pending_tool_action` 확인 흐름 | 의료 확인 게이트가 선례 |
| 기억 저장·삭제 | `_enqueue_extraction` 스킵 조건 + T4 봉인 + (Phase 5) 삭제 발화 처리 | LLM 재량 밖 |

### 6.1 요청서 응답 정책 15개 항목 — 현재 담보 위치

| 정책 | 현재 상태 → 담보 |
| --- | --- |
| 세션 문맥 사용 (마지막 발화만 보지 않기) | 부분 — `recentMessages` 블록. Phase 2에서 `context_candidates`로 조회까지 확장 |
| 기본정보 자연 사용·출처 과시 금지 | 구현 — `system.md` "내부 동작 언급 금지" + 리플레이 §17.9 판정 |
| 현재 발화 > 저장 정보 | Phase 2 — 문맥 선택 1순위(§3)로 결정론 보장 |
| 감정 단정 금지 / 해결책 서두르지 않기 | 구현 — `emotional_stance.md` + `test_emotional_handler.py` 19건 |
| 행동 의사 확인 후 실행 | 부분 — 의료 확인 게이트만. Phase 6 `pending_tool_action`으로 일반화 |
| 짧은 질문엔 짧은 답 / 수치 나열 금지 | 프롬프트 유도(`output_constraints.md`) + 문장 수 절단. 항목 단위 코드 강제는 두지 않음(과잉 절단 위험) — 리플레이 판정으로 감시 |
| 호칭 반복 금지 / 질문 종결 금지 | 프롬프트만 — Phase 6에서 리플레이 판정 기준 추가(P1-C2) |
| 기억 낭독 금지 | 구현 — 기억에 날짜를 붙이되 "기억하고 있는 것"으로 제시(`builder.py:138-149`) + §17.9 |
| 오인식 시 자연스러운 정정 | 부분 — shaper 뼈대 제거 + 되묻기. 시나리오 H 정정은 Phase 2 |
| 중단 즉시 존중 | 부분 — 바지인 메커니즘 존재하나 반이중으로 비활성(실기 검증 필요) |
| 원치 않는 기억 미사용 | 부분 — T4 봉인(정서 턴 한정). Phase 5에서 전 인텐트 확장 + 삭제 처리 |
| 의존 유도 금지 | 프롬프트(`emotional_stance.md` 계열) — 리플레이 판정 후보 |

## 7. 관측 이벤트 (Phase 7)

요청서 이벤트 목록 중 현재 대응물이 있는 것부터 구조화한다: `WAKEWORD_DETECTED`(wakeword.py 로그), `SESSION_STARTED/ENDED`(bootstrap), `CONTEXT_RESOLVED/OVERRIDDEN`(신규 — 후보 선택 지점), `PROFILE_DEFAULT_USED`, `MEMORY_*`(추출 큐), `TOOL_*`, `USER_INTERRUPTED`/`RESPONSE_CANCELLED`(ingress 바지인). 구현은 `logging` `extra=` + JSON 포맷터로 충분하며 새 인프라를 들이지 않는다. **원문 로깅 금지 원칙을 이때 K1(발화 전문 INFO 로그)·K2(stdout 원문)에도 소급 적용한다.**

공통 메타데이터(요청서 목록 채택): `session_id`(세션 FSM이 부여— Phase 1의 부산물), `senior_id`(로컬 로그는 식별자 그대로, 외부 반출 시 비식별), `event_type`, `timestamp`(clock.py 경유), `source_module`, `context_type`/`confidence`(문맥 이벤트만), `latency`(turn_timer 연동), `result`. 발화 원문은 어떤 이벤트에도 싣지 않는다 — 보호자 알림 payload에 이미 걸려 있는 테스트 보증(`test_safety_triage.py:372`)을 로그 이벤트에도 같은 방식으로 고정한다.

## 8. 이 설계가 바꾸지 않는 것 (명시)

- 그래프 노드 구성과 3개 조기 종료 엣지(침묵·맞장구·현관) — 그대로
- 턴당 생성 LLM 1회 예산(§16) — 문맥 해석은 전부 결정론이므로 추가 호출 0
- push/pull 기억 경계(§8), fact_candidate 계약, T1~T4(§9) — 그대로
- 레거시 `pipeline.py` — 손대지 않음 (`--legacy` 전용)
- MQTT·현관·침묵 사다리 — 이 계획의 범위 밖
