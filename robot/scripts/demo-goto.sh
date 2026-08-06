#!/usr/bin/env bash
# 개발 PC(WSL)에서 실행 — 시연 2단계. 현관까지 자율주행.
#
#   robot/scripts/demo-goto.sh [지도이름]
#
# 지도 이름을 생략하면 1단계가 남긴 이름을 쓴다. 목표를 보내기 전에 경로
# 존재를 확인하므로, 로봇이 벽에 붙어 있으면 주행하지 않고 이유를 알려준다.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$HERE/lib/remote.sh"

bomi_deploy
echo "▶ 2단계 시작"
bomi_ssh_interactive "$BOMI_REMOTE_SCRIPTS/bomi_goto.sh ${1:-}"
