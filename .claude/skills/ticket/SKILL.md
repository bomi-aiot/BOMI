---
name: ticket
description: Jira 티켓 하나를 자체 브랜치에서 끝까지 구현한다 — 브랜치 점검, 구현, 테스트, 린트, 문서, 커밋, push, MR 본문까지. 사용자가 "티켓 NNN 구현해줘", "이거 작업해줘", "티켓 처리해", "S15P11E102-252 해줘" 같은 말을 하면 쓴다. 티켓을 설명만 해달라는 요청에는 explain-ticket 을 쓰고 이 스킬은 쓰지 않는다.
---

# 티켓 하나 = 브랜치 하나 = MR 하나

이 순서가 이 저장소에서 티켓이 엉키지 않고 들어간 이유다. **직렬화를 깨지 않는다.**
사용자가 명시적으로 병렬을 요청하면 `parallel-tickets` 를 쓴다.

---

## 1단계 — 착수 전 점검 (건너뛰지 않는다)

`branch-preflight` 를 먼저 실행한다. 요약하면:

```bash
git fetch --all --prune
git log --oneline --all --grep="S15P11E102-<번호>"   # 이미 머지됐나
git rev-parse --abbrev-ref HEAD                       # 지금 어느 라인인가
```

- **이미 머지된 티켓이면 중단하고 보고한다.** 계획하지 않는다.
- **대상 경로가 현재 브랜치 라인 소속이 아니면 구현하지 않는다.** 티켓만 남긴다.
  (AI 라인에서 `backend/` 를 고치지 않는다. 그 반대도 마찬가지다.)

## 2단계 — 티켓 읽기

`getJiraIssue` (cloudId `ssafy.atlassian.net`). 한국어가 `\uXXXX` 로 깨져 보이면
**먼저 고치고 before/after 를 보여준다** (`jira-safe-edit`).

`description` 이 `null` 이면 그 사실을 사용자에게 알린다. 이 저장소에는 본문이 빈
티켓이 흔하고, 그때 "왜"는 재구성해야 한다. 재구성한 부분은 `[추론]` 로 표시한다.

## 3단계 — 브랜치 하나

```bash
git checkout <line>-develop && git pull
git checkout -b "S15P11E102-<번호>-<line>-<한글슬러그>"
```

- `<line>` 은 `ai` / `be` / `fe`, 로봇은 `robot/feat/S15P11E102-<번호>-<slug>` 형식
- 지배적 관행은 `S15P11E102-233-ai-실기-점검` 형태다 (`CONTRIBUTING.md` 의
  `feat/*` 설명은 실제와 다르다 — 실제 브랜치를 따른다)
- **worktree 를 만들지 않는다.** 두 번째 티켓 브랜치를 동시에 시작하지 않는다.
  사용자의 명시적 승인 없이는.

## 4단계 — 구현

- `CLAUDE.md` 의 해당 §를 먼저 읽는다. 특히 **§21(주석은 산출물, 한국어로)**,
  **§20(모듈 경계)**, **§23(안티패턴)**.
- 모든 튜닝 숫자는 `policy.py` 에. 환경변수는 `config.py` 에. 둘을 섞지 않는다.
- `clock.py` 밖에서 `time.time()` / `datetime.now()` 를 쓰지 않는다.
- **시간 의존 테스트는 주입된 시계를 쓴다.** 실제 시계를 쓰면 테스트가 간헐적으로 깨진다.
- 테스트를 코드와 **같이** 쓴다. 나중에 붙이지 않는다.

## 5단계 — 게이트 (둘 다 초록일 때까지)

```bash
cd robot/ai_chat
venv/Scripts/ruff.exe check src tests
venv/Scripts/pytest.exe -q -m "not integration and not manual"
```

> **건드린 파일의 기존 린트 실패도 내 문제다.** "원래 있던 부채"로 합리화하지 않는다.
> 정말 무관하고 범위가 크면 **고치지 말고 멈추고 사용자에게 보고한다.**

빨간 상태로 4단계로 돌아가거나 push 로 넘어가지 않는다. `.claude/hooks/pre-push-gate.sh`
가 push 를 막지만, 막힌 뒤에 아는 것보다 먼저 돌리는 것이 빠르다.

## 6단계 — 문서

`CLAUDE.md §22a` 가 요구하는 갱신이다. **완료의 일부이며 나중 서류작업이 아니다.**

| 문서 | 갱신 시점 |
| --- | --- |
| `docs/carebot/PROGRESS.md` | **모든 티켓 push** — 행 이동 + 완료 조건 결과 |
| `docs/carebot/VERIFICATION.md` | 확인 방법이 새로 생겼거나 성공 기준이 바뀔 때 |
| `docs/carebot/READING-ORDER.md` | 새 모듈이 들어올 때 |
| `docs/carebot/CONCEPTS.md` | 독자가 역공학해야 할 설계 판단이 생겼을 때 |

**구현만 된 것을 완료로 쓰지 않는다.** "로직 검증, 실기 미검증"이 이 작업 대부분의
정직한 형태다.

## 7단계 — 커밋

```text
[영역](카테고리) S15P11E102-<번호> 제목 — 부제
```
영역 `AI`/`BE`/`AI+BE`/`ROBOT`/`HW`, 카테고리 `infra` `api` `jobs` `rag` `schema`
`dialogue` `prompt` `memory` `test` 중 소문자 한 단어. 본문은 자유 서술.

## 8단계 — push + MR

```bash
git push -u origin "<브랜치명>"
git ls-remote --heads origin "<브랜치명>"    # 링크 주기 전 필수 확인
```

MR 본문은 `mr-body` 스킬의 6개 절을 그대로 쓴다. 머지 대상은 `<line>-develop`.

## 9단계 — 보고

`verify-evidence` 형식으로 검증 표를 낸다. 그리고 **다음 티켓으로 넘어갈지 묻는다.**
한 번에 몰아치지 않는다.

---

## 멈춰야 할 때

아래 중 하나라도 해당하면 **구현을 계속하지 않고 사용자에게 묻는다.**

- 티켓이 이미 머지되어 있다
- 대상 경로가 현재 브랜치 라인이 아니다
- 게이트가 빨갛고 원인이 이 티켓 범위를 넘는다
- 티켓이 새 서비스·서버·프레임워크 도입을 요구하는 것처럼 읽힌다 (제안 먼저)
- 티켓 본문이 비어 있고 목적을 추론할 근거도 없다

## 안티패턴

- 브랜치 점검 없이 착수한다
- 한 브랜치에 두 티켓을 넣는다
- 빨간 게이트로 push 한다
- `PROGRESS.md` 갱신을 "나중에"로 미룬다
- 구현만 된 것을 "완료"로 문서에 쓴다
- 확인하지 않은 MR 링크를 준다
- 요청하지 않은 새 서비스·프레임워크를 도입한다
- 파일·디렉터리가 없다고 단정하기 전에 Grep/Glob 으로 저장소와 worktree 를 찾지 않는다
