#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$#" -eq 0 ]]; then
  printf '[changes] ERROR: at least one path is required\n' >&2
  exit 2
fi

case "${FORCE_DEPLOY:-false}" in
  true|TRUE|1|yes|YES)
    printf '[changes] FORCE_DEPLOY is enabled; deployment is required\n'
    exit 0
    ;;
esac

readonly current_commit="$(git rev-parse HEAD)"
readonly previous_commit="${GIT_PREVIOUS_SUCCESSFUL_COMMIT:-}"

if [[ -z "$previous_commit" ]] \
  || ! git cat-file -e "${previous_commit}^{commit}" 2>/dev/null; then
  printf '[changes] No usable previous successful commit; deployment is required\n'
  exit 0
fi

set +e
git diff --quiet "$previous_commit" "$current_commit" -- "$@"
readonly diff_status="$?"
set -e

case "$diff_status" in
  0)
    printf '[changes] No relevant changes; deployment will be skipped\n'
    exit 1
    ;;
  1)
    printf '[changes] Relevant changes detected:\n'
    git diff --name-only "$previous_commit" "$current_commit" -- "$@"
    exit 0
    ;;
  *)
    printf '[changes] ERROR: git diff failed with status %s\n' "$diff_status" >&2
    exit "$diff_status"
    ;;
esac
