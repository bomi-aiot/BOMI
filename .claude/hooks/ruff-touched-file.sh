#!/usr/bin/env bash
# PostToolUse(Edit|Write) — 방금 고친 파이썬 파일에 ruff 를 돌린다.
#
# 왜 존재하는가
#   린트를 "기억해서 돌리는 일"에서 "저절로 일어나는 일"로 바꾼다. 2026-08 리포트에서
#   빨간 ruff 게이트가 그대로 push 된 사고가 있었고, 그 근본 원인은 편집과 검사 사이의
#   시간 간격이었다. 편집 직후에 알려주면 고칠 사람이 아직 그 파일을 보고 있다.
#
# 입력  stdin 으로 훅 JSON. .tool_input.file_path (Edit) 또는 .tool_response.filePath (Write).
# 출력  깨끗하면 조용히 exit 0. 문제가 있으면 exit 2 + stderr → 모델에게 되돌아간다.
#
# ★ jq 를 쓰지 않는 이유
#   이 팀의 Git Bash 에는 jq 가 없다(2026-08-04 확인). 인사이트 리포트가 제안한
#   jq 기반 훅을 그대로 넣었다면 훅이 조용히 아무 일도 하지 않았을 것이다. 파서는
#   저장소가 이미 갖고 있는 venv 파이썬을 쓴다 — 새 의존성을 만들지 않는다.
#
# 주의  exit 2 는 PostToolUse 에서 "차단"이 아니라 "되돌려 알림"이다. 턴은 계속된다.
#       그래서 편집을 되돌리지 않고, 다음 행동으로 수정을 유도한다.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AI_DIR="$REPO_ROOT/robot/ai_chat"

PY="$AI_DIR/venv/Scripts/python.exe"
[[ -x "$PY" ]] || PY="$AI_DIR/venv/bin/python"          # 리눅스/젯슨
[[ -x "$PY" ]] || PY="$(command -v python3 || true)"     # 최후 수단

RUFF="$AI_DIR/venv/Scripts/ruff.exe"
[[ -x "$RUFF" ]] || RUFF="$AI_DIR/venv/bin/ruff"

# 훅이 고장난 것과 린트가 통과한 것은 다른 사실이다. 둘 다 조용한 exit 0 이면
# 구분할 수 없으므로, 도구가 없을 때는 반드시 이유를 남긴다.
[[ -n "$PY" && -x "$PY" ]] || { echo "[ruff-hook] no python available to parse hook input" >&2; exit 0; }
[[ -x "$RUFF" ]] || { echo "[ruff-hook] ruff not installed at $RUFF (pip install -e '.[dev]')" >&2; exit 0; }

FILE="$("$PY" -c 'import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
i = d.get("tool_input") or {}
r = d.get("tool_response") or {}
print(i.get("file_path") or r.get("filePath") or "")' 2>/dev/null)"

[[ -n "$FILE" ]] || exit 0

# ★ 경로 구분자를 정규화한다.
#   Windows 에서는 file_path 가 `C:\...\robot\ai_chat\x.py` 로 올 수 있고, 그러면
#   슬래시 패턴이 매칭되지 않아 훅이 '조용히' 아무 일도 하지 않는다. 훅이 안 도는
#   것과 린트가 통과한 것을 구분할 수 없게 되는 바로 그 실패다.
NORM="${FILE//\\//}"

# 이 훅은 로봇 런타임 파이썬만 본다. 백엔드 자바·문서·설정은 대상이 아니다.
case "$NORM" in
  *robot/ai_chat/*.py) ;;
  *) exit 0 ;;
esac

OUT="$("$RUFF" check "$FILE" 2>&1)" && exit 0

# CLAUDE.md §23 은 빨간 게이트로 push 하는 것을 안티패턴으로 규정한다.
# 여기서 알려주면 push 직전 게이트(pre-push-gate.sh)까지 갈 일이 없다.
{
  echo "ruff check failed on the file just edited:"
  echo "$OUT"
  echo
  echo "Fix these now. A pre-existing failure in a file you touched is yours (CLAUDE.md §26)."
} >&2
exit 2
