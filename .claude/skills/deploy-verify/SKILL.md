---
name: deploy-verify
description: 배포 전후를 실제로 검증한다 — 코드가 읽는 env 변수와 compose/CI 정의를 3방향 대조하고, 실행 중인 컨테이너가 마운트한 nginx 설정을 찾아내고, 상태 코드가 아니라 응답 본문으로 엔드포인트를 확인한다. 사용자가 "배포됐는지 확인", "env 변수 점검", "배포 스크립트 만들어줘", "nginx 반영됐나", "왜 배포가 안 먹지", "compose 변수 확인" 같은 말을 하면 쓴다.
---

# 배포 검증 — 200 은 증거가 아니다

## 왜 존재하는가

두 개의 실제 사고에서 나왔다.

| 사고 | 무엇을 믿었나 | 진실 |
| --- | --- | --- |
| 문서 배포 "성공" | HTTP 200 | **SPA 폴백**이 index.html 을 200 으로 주고 있었다 |
| 218 프로덕션 장애 | `.env` 에 값을 적었다 | **컨테이너에 전달되지 않았다** — compose 에 pass-through 두 줄이 없었다 |

두 사고의 공통점: **파일을 고친 것을 반영된 것으로 취급했다.**

이 저장소에는 그 교훈이 이미 주석으로 남아 있다 —
`infra/compose.prod.yml` 의 `EMBEDDING_ENABLED` 위에 "이 두 줄이 없으면
production.env 에 true 를 적어도 기본값이 읽힌다"고 적혀 있다.

---

## 1단계 — 가정하지 말고 현실을 감사한다

### env 변수 3방향 대조

```bash
# 코드가 실제로 읽는 변수
grep -rnoE '(os\.environ(\.get)?\(|getenv\(|System\.getenv\()[^)]*' \
  --include=*.py --include=*.java . | sort -u
grep -rnoE '\$\{[A-Z_]+' --include=*.yml --include=*.yaml . | sort -u

# compose / .env 템플릿 / CI 가 정의하는 변수
grep -rnoE '^[[:space:]]*[A-Z_]+:' infra/*.yml docker-compose.yml 2>/dev/null
grep -rnoE '^[A-Z_]+=' infra/*.env* 2>/dev/null
```

표로 낸다.

| 변수 | 코드가 읽음 | compose 정의 | .env 템플릿 | 판정 |
| --- | --- | --- | --- | --- |

- **참조되지만 정의 없음** → 프로덕션을 깨뜨린다. 최우선.
- **정의되었지만 사용 안 함** → 죽은 설정. 혼란의 원인.
- **이름 불일치** → 가장 찾기 어려운 종류. 오타 하나로 기본값이 조용히 쓰인다.

### ★ Spring 의 함정 — 컨테이너 env 와 `application.yml` 은 다른 층이다

`application.yml` 에 `${EMBEDDING_ENABLED:false}` 가 있으면, **compose 가 그 이름을
컨테이너에 넘겨주지 않는 한** 호스트 `.env` 에 뭘 적어도 `false` 가 읽힌다.
`.env` → compose `environment:` → 컨테이너 → `application.yml` 네 층을 전부 확인한다.

### nginx — 추측하지 않고 마운트를 본다

```bash
docker inspect <container> --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
docker exec <container> nginx -t
```
호스트 디렉터리를 추측하다가 엉뚱한 곳을 고친 적이 있다. **실행 중인 컨테이너가
무엇을 마운트했는지가 유일한 진실**이다. 명령 출력을 근거로 붙인다.

---

## 2단계 — 게이트를 만든다

`scripts/` 는 이 저장소에 이미 있다. 다만 **`scripts/ci/verify-ai.sh` 는 죽어 있다** —
존재하지 않는 `ai/` 디렉터리를 가리켜 exit 3 으로 끝난다(런타임은 `robot/ai_chat/`,
`CLAUDE.md §20`). 새 게이트를 그 위에 얹지 말고, 고칠지 대체할지 먼저 결정한다.

게이트가 반드시 실패시켜야 하는 것:

- 참조되지만 정의되지 않은 env 변수
- `nginx -t` 실패
- **SPA 폴백 응답** — 200 이어도 index.html 이면 FAIL

```bash
# 스모크 테스트의 핵심 한 줄: 200 이 아니라 '무엇이' 왔는지 본다
body="$(curl -sS "$URL")"
case "$body" in
  *"<div id=\"root\""*|*"<title>Vite"*) echo "FAIL: SPA fallback"; exit 1 ;;
esac
grep -q "<기대하는 고유 문자열>" <<<"$body" || { echo "FAIL: unexpected body"; exit 1; }
```

- nginx 설정 변경 뒤 **실제 리로드가 일어났는지**, 그리고 **반영됐는지** 둘 다 확인한다.
  파일 수정 ≠ 리로드, 리로드 ≠ 반영.

---

## 3단계 — 게이트가 동작함을 증명한다

**게이트를 만든 것과 게이트가 잡는 것은 다른 사실이다.**

1. 스크래치 사본에서 env 변수 하나와 nginx 지시어 하나를 **일부러 깨뜨린다**
2. 게이트를 돌려 **둘 다 잡는지** 확인하고 출력을 보여준다
3. 되돌린다
4. 그다음 필수 CI 스테이지로 추가한다

이 증명을 생략하면 "게이트가 있다"는 착각만 남는다. 실제로 이 프로젝트의
`verify-ai.sh` 가 그 상태다 — 존재하지만 항상 exit 3 이다.

---

## 출력

`verify-evidence` 형식의 표. 산문이 아니라 명령과 출력. 설명은 짧게.

## 안티패턴

- 상태 코드로 배포 성공을 판정한다
- 호스트 파일을 확인하고 컨테이너 안을 확인하지 않는다
- nginx 설정 경로를 추측한다
- 게이트를 만들고 "잡는지" 시험하지 않는다
- 죽은 `verify-ai.sh` 위에 새 게이트를 얹어 두 개가 다 안 도는 상태를 만든다
