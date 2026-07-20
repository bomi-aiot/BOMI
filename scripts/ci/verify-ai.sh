#!/usr/bin/env bash
set -Eeuo pipefail

readonly SOURCE_DIR="${BOMI_SOURCE_DIR:-$(git rev-parse --show-toplevel)}"
[[ -d "$SOURCE_DIR/ai" ]] || {
  echo '[verify-ai] AI project directory is not available yet: ai/' >&2
  exit 3
}

docker run --rm \
  --volume "$SOURCE_DIR/ai:/source:ro" \
  python:3.11-slim \
  sh -ec '
    cp -a /source /workspace
    cd /workspace
    python -m compileall -q .
    if [ -f pyproject.toml ]; then
      python -m venv /venv
      /venv/bin/pip install --quiet --upgrade pip
      /venv/bin/pip install --quiet -e ".[dev]"
      if [ -d tests ]; then /venv/bin/python -m pytest; fi
    elif [ -f requirements.txt ]; then
      python -m venv /venv
      /venv/bin/pip install --quiet -r requirements.txt
    fi
  '
