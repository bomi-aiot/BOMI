#!/usr/bin/env bash
# 개발 PC(WSL)에서 실행 — 시연 1단계. 지도 그리고 현관·출발 좌표 기록.
#
#   robot/scripts/demo-map.sh [--host IP] [지도이름] [launch 인자...]
#
# 로봇 IP 는 네트워크마다 다르므로 --host 로 준다. 생략하면 강의장
# 와이파이 기준값(192.168.30.30)을 쓴다.
#
# 지도 이름 뒤의 인자는 ros2 launch 로 그대로 넘어간다. SLAM 설정을
# 바꿔가며 비교할 때 로봇에 들어가 파일을 고칠 필요가 없다.
#
#   robot/scripts/demo-map.sh bomi_demo do_loop_closing:=false
#
# 최신 스크립트를 로봇에 배포한 뒤 실행하므로, 저장소가 항상 단일 출처다.
# RViz 는 WSLg 로 이 PC 화면에 뜬다(-Y 와 DISPLAY=:0).
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$HERE/lib/remote.sh"

bomi_parse_host "$@"
set -- ${BOMI_ARGS[@]+"${BOMI_ARGS[@]}"}

bomi_deploy
echo "▶ 1단계 시작 (Ctrl+C 로 언제든 중단 — 로봇 프로세스도 함께 정리됩니다)"
bomi_ssh_interactive "$BOMI_REMOTE_SCRIPTS/bomi_map.sh ${1:-bomi_demo} ${*:2}"
