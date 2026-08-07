---
name: verify-evidence
description: 방금 한 변경·배포·수정에 대해 실제 명령 출력을 근거로 붙인 검증 표를 만든다. 사용자가 "검증해줘", "진짜 되는지 확인", "증거 보여줘", "테스트 결과 붙여줘", "배포 확인", "정말 고쳐졌어?" 같은 말을 하거나, 작업을 완료 보고하기 직전에 쓴다. HTTP 상태 코드나 "완료했습니다" 같은 약한 신호로 성공을 주장하는 것을 막는 용도다.
---

# 검증 표 — 주장이 아니라 증거

완료를 보고할 때 **주장 하나당 명령 하나와 그 실제 출력 하나**를 붙인다.
붙일 수 없으면 그 항목은 `UNVERIFIED` 다.

## 왜 존재하는가

2026-08 리포트에서 "결함 있는 코드"가 가장 큰 마찰 범주(11건)였고, 그 대부분은
코드가 아니라 **검증이 없었던 것**이다.

| 실제 사고 | 약한 신호 | 있어야 했던 증거 |
| --- | --- | --- |
| 문서 배포 "성공" | HTTP 200 | 응답 **본문** — 200 은 SPA 폴백이었다 |
| 티켓 200 push | "원래 있던 부채" | `ruff check` 출력 |
| 218 프로덕션 장애 | compose 파일 수정함 | 컨테이너 **안에서** 해석된 env 값 |
| nginx 설정 반영 | 파일 고쳤음 | 리로드 여부 + 리로드 후 동작 |

## 출력 서식

| 주장 | 실행한 명령 | 실제 출력 | 판정 |
| --- | --- | --- | --- |
| 테스트 통과 | `venv/Scripts/pytest.exe -q -m "not integration and not manual"` | `504 passed in 14.38s` | ✅ |
| 린트 통과 | `venv/Scripts/ruff.exe check src tests` | `All checks passed!` | ✅ |
| 실기 동작 | — | — | ⚠️ UNVERIFIED (하드웨어 없음) |

**추측한 값을 출력 칸에 적지 않는다.** 안 돌렸으면 `—` 와 `UNVERIFIED` 다.

## 유형별 최소 증거

**테스트·린트** — 실제 수치. `504 passed`. "로컬 테스트 완료"는 증거가 아니다.

```bash
cd robot/ai_chat
venv/Scripts/pytest.exe -q -m "not integration and not manual"
venv/Scripts/ruff.exe check src tests
```

**HTTP** — 상태 코드가 아니라 본문과 content-type. **SPA 폴백이 아님을 명시적으로
확인한다.**

```bash
curl -sS -D- -o /tmp/body "$URL" | head -20
head -c 300 /tmp/body          # index.html 이 아닌지 눈으로 본다
```

**env / compose** — 파일이 아니라 **실행 중인 컨테이너 안**의 값.

```bash
docker exec <container> printenv | grep -E 'EMBEDDING|QDRANT'
```
호스트의 `.env` 가 맞아도 컨테이너에 전달되지 않는 경우가 이 저장소에서 실제로
있었다(218). 파일은 증거가 아니다.

**nginx** — 어느 설정 파일을 *실제로* 마운트했는지부터 확인한다. 호스트 경로를
추측하지 않는다.

```bash
docker inspect <container> --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
docker exec <container> nginx -t
```

**브랜치·MR 링크** — 링크를 주기 전에 원격에 실제로 있는지 확인한다.

```bash
git ls-remote --heads origin "<브랜치명>"
```

## 규칙

- **검증하지 않은 것을 검증한 것처럼 쓰지 않는다.** 이 항목 하나가 이 스킬의 전부다.
- 출력은 **잘라서** 붙인다(`tail -30`). 전체 로그를 도배하지 않는다.
- 실패를 숨기지 않는다. 실패한 항목이 있으면 표 맨 위에 올린다.
- "미검증"은 부끄러운 상태가 아니다. **미검증을 검증됨으로 적는 것**이 사고다.
- 하드웨어·외부 API가 필요한 항목은 `integration`/`manual` 마커로 분리되어 있다.
  게이트에서 제외하는 것은 정확성이다 — 마이크가 없다는 사실이 push 를 막아서는 안 된다.

## 안티패턴

- 상태 코드만 보고 배포 성공을 주장한다
- 린트 실패를 "원래 있던 부채"로 넘긴다
- 표 없이 산문으로 "모두 정상 동작합니다"라고 쓴다
- 명령은 적고 출력은 생략한다
- 파일을 고친 것을 반영된 것으로 취급한다
