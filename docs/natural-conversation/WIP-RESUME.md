# 작업 일시정지 지점 (2026-08-06) — 재개용 메모

> 사용량 한도로 일시정지. **이 파일은 재개 후 삭제한다** — 완료되면 존재할 이유가 없다.

## 지금 어디까지 왔나

브랜치: `ai/natural-conversation-wip` (로컬 전용, ai-develop @ eadc3bf 기준. 미푸시 — Jira 티켓 미발행)
검증 상태: **704 passed + ruff clean** (2026-08-06 실측, `-m "not integration and not manual"`)

| Phase | 상태 | 커밋 |
| --- | --- | --- |
| 감사·계획·설계 문서 3종 + CLAUDE.md/carebot 문서 최신화 | 완료 | 1번째 커밋 |
| Phase 1: 세션 FSM·speaking 수명(B1)·remainder 재큐(B2) + 세션 테스트 18건 | 완료 | 1번째 커밋 |
| Phase 2: context_slots(지역 문맥 수명·정정·참조) + 테스트 16건 | 완료 | 2번째 커밋 |
| Phase 3: 프로필 미사용 필드(conversationPreferences·chronicPainArea) 프롬프트 반영 + 주소 폴백(시나리오 C 준비) | 완료 | `2d6aeaa` |
| Phase 5-1: T4 봉인 전 인텐트 확장 + "기억하지 마"(봉인+대기 행 삭제) + 테스트 9건 | 완료 | `2d6aeaa` |
| Goal AI-1: 문서 요청 순서 + 검색 가용성/실행 결과 소비 + 문서 근거 보존 | 완료 | `26e9635` |

## 재개하면 바로 할 일 (순서대로)

1. ~~Phase 3+5 커밋~~ → 일시정지 직전에 커밋했으면 `git log --oneline -3` 으로 확인만.
2. **CLAUDE.md 재구성** (작업 목록 #5, 유일한 미완 큰 덩어리):
   - §1 에 자연스러운 연속 대화를 기획 기준으로 승격 (부가기능 아님)
   - §8 에 기억 정정·삭제 정책(구현된 1단계 + BE 취소 대기) 반영
   - §17 체크리스트에 문맥 이어짐·정정 존중·삭제 존중 항목 추가
   - §23 안티패턴에 "만료 없는 문맥 슬롯 추가", "프라이버시 요청을 인텐트 분류 뒤에서 처리" 추가
   - ~~**§30 신설**: 문맥 선택 우선순위~~ → 완료. 현재 발화→SESSION→구조화 일정
     (미구현)→현재 위치(미지원)→프로필 기본값→확인 질문 순서와 수명 규칙 반영.
   - §1~24 번호는 절대 유지 (§25 서문 규칙)
3. **문서 정합** (작업 목록 #11): PROGRESS.md §1 표+§7 이력에 이번 구현 추가, §2.10 에 "B1·B2·T4 확장은 해소됨" 반영, natural-conversation 3종의 상태 표기(P0-1·P0-5·P1-A1~A6·P1-B1 1단계·P1-B3 일부 → 구현됨), VERIFICATION.md 에 신규 테스트 실행법 추가, 이 파일 삭제.
4. 전체 스위트 재실행 후 수치 갱신 (현재 704, 이후 신규 테스트 포함해 감소 금지).
5. 남은 것 정리 보고: BE 티켓 2건(프로필 주소 필드, fact_candidate 취소 엔드포인트), 이동시간 API 미결(P1-A8), Phase 4(사건 연속성 — 의미 검색 운영 미결에 막힘), Phase 6(감정 침묵 타임아웃·리플레이 확장), 실기(젯슨) 재검증 전부 미실시.
6. 사용자에게 확인: Jira 티켓 발행 + 브랜치명 변경(`S15P11E102-<n>-ai-자연대화`) + push 여부.

## 조심할 것

- 이 브랜치는 **로컬 전용**이다. push 전에 티켓 번호로 브랜치명을 바꿔야 한다.
- 테스트 대역에 `is_done` 추가한 것(test_turn_end_to_end.py, test_echo_and_bargein.py)은 실제 SpeechPlayback 인터페이스 추종이다 — 되돌리면 안 된다.
- `test_real_interruption_cancels...` 는 `test_playback_that_already_finished_is_not_an_interruption` 으로 개명됨 (의미 변경 때문).
