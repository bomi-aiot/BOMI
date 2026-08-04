#!/usr/bin/env bash
# PreToolUse(Bash, if: git push) — 게이트가 빨간 상태의 push 를 막는다.
#
# 왜 존재하는가
#   2026-08 리포트의 최대 마찰이 "검증되지 않은 성공 주장"이었다. 티켓 200 이
#   실패하는 ruff 게이트와 함께 push 됐고, 그것을 "원래 있던 부채"라고 합리화했다.
#   사람의 규율에 의존하는 규칙은 반드시 언젠가 깨진다. 기계가 막아야 한다.
#
# 무엇을 하는가
#   1. push 될 커밋들이 robot/ai_chat 의 파이썬을 건드렸는지 본다.
#   2. 건드렸으면 ruff + pytest 를 돌린다. 하나라도 빨가면 push 를 거부한다.
#   3. 안 건드렸으면 통과시킨다 — 문서만 고친 push 를 14초 기다리게 하지 않는다.
#
# 왜 scripts/ci/verify-ai.sh 를 쓰지 않는가
#   그 스크립트는 존재하지 않는 `ai/` 디렉터리를 가리켜 exit 3 으로 죽는다(런타임은
#   robot/ai_chat/ 이다, CLAUDE.md §20). 도커로 pip install 까지 하므로 분 단위이기도 하다.
#   push 직전 게이트는 초 단위여야 한다.
#
# 출력  통과 → exit 0 (조용히). 거부 → exit 2 + stderr.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AI_DIR="$REPO_ROOT/robot/ai_chat"
RUFF="$AI_DIR/venv/Scripts/ruff.exe"; [[ -x "$RUFF" ]] || RUFF="$AI_DIR/venv/bin/ruff"
PYTEST="$AI_DIR/venv/Scripts/pytest.exe"; [[ -x "$PYTEST" ]] || PYTEST="$AI_DIR/venv/bin/pytest"

cd "$REPO_ROOT" || exit 0

# push 될 커밋 범위의 기준(base)을 정한다.
#
# ★ 왜 upstream 하나로 끝내지 않는가
#   새 브랜치의 '첫' push 는 항상 upstream 이 없다. 그것을 "모르니까 무조건 검사"로
#   처리하면, 모든 팀원이 브랜치를 새로 딸 때마다 게이트를 밟는다. venv 를 만들지
#   않은 사람은 그 시점에 push 가 막히고, 원인을 알 수 없는 실패로 보인다.
#   그래서 upstream 이 없으면 브랜치 이름에서 라인을 뽑아 origin/<line>-develop 을
#   기준으로 삼는다. 그것도 못 정하면 그때는 검사한다 — 모르는 것을 통과시키지 않는다.
resolve_base() {
  local up branch line=""

  # 1) upstream 이 있으면 가장 정확하다
  if up="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)"; then
    printf '%s' "$up"
    return 0
  fi

  # 2) 브랜치 이름에서 라인을 파생한다 (CLAUDE.md §25 의 두 서식)
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  case "$branch" in
    */*)          line="${branch%%/*}" ;;                              # robot/feat/... , be/chore/...
    S15P11E102-*) line="$(printf '%s' "$branch" | cut -d- -f3)" ;;     # S15P11E102-233-ai-실기-점검
  esac

  case "$line" in
    ai|be|fe|robot)
      if git rev-parse --verify --quiet "origin/${line}-develop" >/dev/null 2>&1; then
        printf 'origin/%s-develop' "$line"
        return 0
      fi
      ;;
  esac

  return 1
}

# 세 점(base...HEAD)을 쓴다. merge-base 기준이므로 base 가 앞서 나가 있어도
# "이 브랜치가 '더한' 것"만 잡힌다. 두 점을 쓰면 남의 커밋까지 내 변경으로 센다.
if BASE="$(resolve_base)"; then
  CHANGED="$(git diff --name-only "$BASE...HEAD" 2>/dev/null)"
  RANGE_DESC="$BASE...HEAD"
else
  CHANGED=""            # 비워두면 아래에서 무조건 검사로 떨어진다
  RANGE_DESC="(base unresolved — checking unconditionally)"
fi

NEEDS_GATE=0
if [[ "${BOMI_FORCE_GATE:-0}" == "1" ]]; then
  # 검증용 스위치. 게이트 자체가 도는지 확인하려면 범위와 무관하게 강제한다 —
  # 파이썬 변경이 없는 상태에서는 빠른 통과 경로만 검증되고, 정작 막아야 할
  # 경로는 한 번도 실행되지 않은 채 "테스트했다"가 되기 때문이다.
  NEEDS_GATE=1
  RANGE_DESC="$RANGE_DESC (forced via BOMI_FORCE_GATE)"
elif [[ "$RANGE_DESC" == "(base unresolved"* ]]; then
  NEEDS_GATE=1
elif grep -qE '^robot/ai_chat/.*\.py$' <<<"$CHANGED"; then
  NEEDS_GATE=1
fi

if [[ $NEEDS_GATE -eq 0 ]]; then
  exit 0   # 파이썬 변경 없음 → 통과
fi

[[ -x "$RUFF" && -x "$PYTEST" ]] || {
  echo "[pre-push-gate] venv tooling missing under $AI_DIR/venv; cannot verify. Run the gates manually before pushing." >&2
  exit 2
}

FAILED=""

RUFF_OUT="$("$RUFF" check "$AI_DIR/src" "$AI_DIR/tests" 2>&1)" || FAILED="ruff"

# manual/integration 은 하드웨어·외부 API·자격증명이 필요하다. 게이트에서 제외하는 것은
# 편의가 아니라 정확성이다 — 노트북에 마이크가 없다는 사실이 push 를 막아서는 안 된다.
#
# 이 -m 플래그 자체가 지금 거르는 테스트는 0건이다(`tests/` 안에 integration/manual
# 마커가 붙은 테스트가 아직 없다 — `pytest --collect-only -m "integration or manual"` 로
# 확인 가능). 실제 격리는 두 가지가 한다: pyproject.toml 의 `norecursedirs = ["manual"]`
# 이 하드웨어 스모크 스크립트가 있는 tests/manual/ 을 아예 수집에서 뺀다. 그리고
# tests/conftest.py 의 autouse fixture `block_external_http` 가, integration/manual 로
# 표시되지 않은 테스트가 실제 HTTP 요청을 보내면 즉시 실패시킨다. -m 플래그는 앞으로
# 마커가 붙은 pytest 통합 테스트가 생길 때를 위한 관례로 남겨 둔다.
PYTEST_OUT="$(cd "$AI_DIR" && "$PYTEST" -q -m "not integration and not manual" 2>&1)" \
  || FAILED="${FAILED:+$FAILED + }pytest"

[[ -z "$FAILED" ]] && exit 0

{
  echo "BLOCKED: git push refused — $FAILED is red (range: $RANGE_DESC)"
  echo
  if [[ "$FAILED" == *ruff* ]]; then
    echo "--- ruff check ---"; echo "$RUFF_OUT" | tail -30; echo
  fi
  if [[ "$FAILED" == *pytest* ]]; then
    echo "--- pytest ---"; echo "$PYTEST_OUT" | tail -30; echo
  fi
  echo "Do not push. Fix the failures, or report them to the user and ask —"
  echo "never rationalize a red gate as pre-existing debt (CLAUDE.md §26)."
} >&2
exit 2
