#!/usr/bin/env bash
# 시연 1단계 — 지도를 그리고 현관·출발 좌표를 기록한다. (로봇에서 실행)
#
#   bomi_map.sh [지도이름]        기본값 bomi_demo
#
# 사람이 할 일은 조이스틱 운전과 Enter 두 번뿐이다. 정리·저장·좌표기록은
# 전부 이 스크립트가 한다.
set -o pipefail

MAP=${1:-bomi_demo}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WS=$(cd "$HERE/../ros2_ws" && pwd)
WAYPOINTS=$WS/src/core/config/room_waypoints.yaml
STATE=$HOME/.bomi_demo_state
LOG=/tmp/bomi_map.log

# shellcheck source=lib/cleanup.sh
source "$HERE/lib/cleanup.sh"
source /opt/ros/humble/setup.bash
source "$WS/install/setup.bash"
cd "$WS" || exit 1

LAUNCH_PGID=""
finish() {
    if [ -n "$LAUNCH_PGID" ]; then
        kill -INT -- "-$LAUNCH_PGID" 2>/dev/null
        sleep 3
        kill -9 -- "-$LAUNCH_PGID" 2>/dev/null
    fi
    bomi_cleanup
}
# ssh 가 끊겨도(HUP) 원격 프로세스가 고아로 남지 않게 한다.
trap 'echo; echo "중단 — 정리합니다"; finish; exit 130' INT TERM HUP
trap finish EXIT

echo "▶ 0/4 기존 프로세스 정리"
bomi_cleanup
LEFT=$(bomi_leftovers)
if [ -n "$LEFT" ]; then
    echo "❌ 정리되지 않은 프로세스가 있습니다. 수동 확인이 필요합니다:"
    echo "$LEFT"
    exit 1
fi
echo "  깨끗함"

if [ -z "$DISPLAY" ]; then
    echo "⚠ DISPLAY 가 비어 있어 RViz 가 뜨지 않습니다."
    echo "  지도를 보면서 그리려면 WSL 터미널에서 실행하세요:"
    echo "    DISPLAY=:0 ssh -Y ssafy@<로봇IP> '~/…/bomi_map.sh'"
    echo "  (그대로 진행하지만 화면 없이 그리게 됩니다)"
fi

echo "▶ 1/4 매핑 스택 실행 — 로그 $LOG"
setsid ros2 launch core joystick_slam_robot.launch.py \
    pico_port:=/dev/ttyACM0 lidar_port:=/dev/ttyUSB0 > "$LOG" 2>&1 &
LAUNCH_PGID=$!

for _ in $(seq 1 40); do
    pgrep -f slam_toolbox >/dev/null && break
    sleep 2
done
if ! pgrep -f slam_toolbox >/dev/null; then
    echo "❌ slam_toolbox 가 뜨지 않았습니다. $LOG 를 확인하세요."
    exit 1
fi
sleep 6

SCAN=$(timeout 10 ros2 topic hz /scan 2>&1 | grep -m1 -o 'average rate: [0-9.]*')
echo "  scan_sanitizer $(pgrep -f scan_sanitizer >/dev/null && echo OK || echo 없음) / ${SCAN:-스캔 없음}"
pgrep -f rviz2 >/dev/null && echo "  RViz 실행됨" || echo "  ⚠ RViz 없음 (화면 없이 진행)"

cat <<'GUIDE'

════════════════════════════════════════════════════════════
 조이스틱으로 지도를 그리세요.
   · 천천히 — 빠르면 벽선이 두 겹으로 찍힙니다
   · 지나갈 통로는 왕복하며 좌우로 스캔
   · 다 그렸으면 로봇을 현관 앞에 세우세요
     (벽에서 40cm 이상 띄우고, 현관을 바라보게)
════════════════════════════════════════════════════════════
GUIDE
read -rp "현관에 세웠으면 Enter > " _

echo "▶ 2/4 현관 좌표 기록"
ENTRANCE=$(timeout 40 python3 "$HERE/lib/read_pose.py") || {
    echo "❌ 좌표를 읽지 못했습니다"; exit 1; }
read -r EX EY EYAW <<<"$ENTRANCE"
echo "  현관: x=$EX y=$EY yaw=$EYAW"

python3 - "$WAYPOINTS" "$EX" "$EY" "$EYAW" <<'PY' || exit 1
import re
import sys
path, x, y, yaw = sys.argv[1:5]
text = open(path, encoding="utf-8").read()
block = ("  # 실측 좌표. 재매핑하면 지도 좌표계가 바뀌어 무효가 된다.\n"
         "  - name: entrance\n    x: %s\n    y: %s\n    yaw: %s\n" % (x, y, yaw))
updated = re.sub(
    r"(?:  #[^\n]*\n)*  - name: entrance\n(?:    \w+: [-0-9.]+\n)+",
    block, text, count=1)
if updated == text:
    print("  ❌ room_waypoints.yaml 의 entrance 항목을 찾지 못했습니다")
    sys.exit(1)
open(path, "w", encoding="utf-8").write(updated)
print("  room_waypoints.yaml 갱신 완료")
PY

timeout 150 ros2 run nav2_map_server map_saver_cli -f "src/mapping/maps/$MAP" \
    --ros-args -p save_map_timeout:=90.0 2>&1 | grep -E "Received|successfully" \
    || { echo "❌ 지도 저장 실패"; exit 1; }

cat <<'GUIDE'

════════════════════════════════════════════════════════════
 이제 로봇을 출발 지점으로 옮기세요.
   · 현관에서 1.5~2m 떨어진 곳
   · 벽·가구에서 40cm 이상 띄우기 ← 가장 흔한 실패 원인
════════════════════════════════════════════════════════════
GUIDE
read -rp "옮겼으면 Enter > " _

echo "▶ 3/4 출발 좌표 기록"
START=$(timeout 40 python3 "$HERE/lib/read_pose.py") || {
    echo "❌ 좌표를 읽지 못했습니다"; exit 1; }
echo "  출발: $START"
timeout 150 ros2 run nav2_map_server map_saver_cli -f "src/mapping/maps/$MAP" \
    --ros-args -p save_map_timeout:=90.0 2>&1 | grep -E "successfully"

printf 'MAP=%s\nSTART="%s"\n' "$MAP" "$START" > "$STATE"

echo "▶ 4/4 매핑 종료"
finish
trap - EXIT

cat <<EOF

✅ 1단계 완료
   지도      : src/mapping/maps/$MAP
   현관 좌표 : $EX $EY $EYAW
   출발 좌표 : $START
   상태 파일 : $STATE

   다음: bomi_goto.sh
EOF
