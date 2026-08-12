#!/usr/bin/env bash
# 시연 1단계 — 지도를 그리고 현관·출발 좌표를 기록한다. (로봇에서 실행)
#
#   bomi_map.sh [지도이름] [launch 인자...]     기본값 bomi_demo
#
# 사람이 할 일은 조이스틱 운전과 Enter 두 번뿐이다. 정리·저장·좌표기록은
# 전부 이 스크립트가 한다.
#
# 지도 이름 뒤의 인자는 ros2 launch 로 그대로 넘어간다. SLAM 설정을
# 바꿔가며 비교할 때 파일을 고치고 colcon build 를 다시 하지 않아도 된다.
#
#   bomi_map.sh bomi_demo do_loop_closing:=false
#   bomi_map.sh bomi_demo use_scan_matching:=false
#   bomi_map.sh bomi_demo use_rviz:=false
set -o pipefail

MAP=${1:-bomi_demo}
shift 2>/dev/null || true
LAUNCH_EXTRA=("$@")

# LiDAR의 base_link 기준 장착 위치(m). joystick_slam_robot.launch.py 기본값은
# 아직 0이므로 이 스크립트가 실측값을 넘겨 준다 — 즉 **이 값이 곧 실기 기준이다.**
# 환경변수는 재보는 중일 때만 쓰고, 확정되면 여기 기본값을 고친다. 기억해서
# 넘겨야만 지도가 맞는 스크립트는 언젠가 반드시 잊는다.
#
# 왜 x가 중요한가: LiDAR가 회전 중심에서 앞으로 나와 있으면, 제자리 회전에서
# 스캔 원점은 반지름 0.135 m의 원을 그린다. TF가 0이라고 하면 그 이동분이
# 통째로 지도 오차가 되어, 회전할 때마다 방이 조금씩 돌아간 채 겹쳐 쌓인다.
# 2026-08-07 오전 실기의 증상이 정확히 이것이었다. 같은 날 새벽에 깨끗한
# 지도가 나온 실행은 이 값을 손으로 넘기고 있었다(bash history 1529행 등).
#
# 왜 z가 중요한가: 2D 주행 계산에는 z가 거의 쓰이지 않는다(스캔은 XY로 투영되고
# AMCL도 x, y, yaw만 맞춘다). 진짜 문제는 **지도가 이 높이의 단면**이라는 것이다.
# 24cm에서 그린 지도는 소파 하단·의자 다리를 담고, 46.6cm에서 그린 지도는 좌석과
# 좌탁 상판을 담는다. 둘은 같은 방인데도 실루엣이 달라 서로 매칭되지 않는다.
# 그래서 이 값을 바꾸면 **반드시 다시 그려야 하고**, 다시 그렸으면 여기와
# bomi_navigation_real.launch.py 의 laser_z 기본값이 같아야 한다. 어긋나면
# "그릴 때와 다른 높이로 주행"이 되어 AMCL이 조용히 위치를 놓친다.
#
# 2026-08-10: LiDAR 마운트를 높여 z가 0.240 -> 0.466 이 되었다.
# ★ x, y는 아직 2026-08-07 실측값 그대로다. 마운트가 바뀌었으므로 줄자로 다시
#   재서 여기를 고칠 것 — 특히 x는 위 이유로 지도 품질에 직결된다.
LASER_X=${BOMI_LASER_X:-0.135}
LASER_Y=${BOMI_LASER_Y:-0.0}
LASER_Z=${BOMI_LASER_Z:-0.466}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WS=$(cd "$HERE/../ros2_ws" && pwd)
WAYPOINTS=$WS/src/core/config/room_waypoints.yaml
STATE=$HOME/.bomi_demo_state
LOG=/tmp/bomi_map.log

# shellcheck source=lib/cleanup.sh
source "$HERE/lib/cleanup.sh"
# shellcheck source=lib/health.sh
source "$HERE/lib/health.sh"
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
[ ${#LAUNCH_EXTRA[@]} -gt 0 ] && echo "  추가 launch 인자: ${LAUNCH_EXTRA[*]}"
echo "  LiDAR 장착 위치 x=$LASER_X y=$LASER_Y z=$LASER_Z"
setsid ros2 launch core joystick_slam_robot.launch.py \
    pico_port:=/dev/ttyACM0 lidar_port:=/dev/ttyUSB0 \
    laser_x:="$LASER_X" laser_y:="$LASER_Y" laser_z:="$LASER_Z" \
    ${LAUNCH_EXTRA[@]+"${LAUNCH_EXTRA[@]}"} > "$LOG" 2>&1 &
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

# slam_toolbox 만 보고 진행하면, 모터 드라이버가 죽어도 안내문이 그대로
# 나가서 사람이 안 움직이는 조이스틱을 붙들게 된다. 운전을 시키기 전에
# 확인한다.
bomi_require_pico "$LOG" || exit 1

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
    r"(?:[ ]*#[^\n]*\n)*[ ]*- name: entrance\n(?:[ ]+\w+: [-0-9.]+\n)+",
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

# 현관과 출발이 너무 가까우면 되묻는다. 2026-08-10 실기에서 로봇을 옮기지 않고
# Enter 를 눌러 둘이 0.555m 로 찍혔고, 그대로 시연에 들어가 Nav2 가 팽창 영역
# 안에서 출발하느라 경로 생성부터 실패했다. 조용히 지나가는 것이 문제였다.
# 하한 1.0m 은 지그재그 min_distance_m 과 같은 값이다 — 이보다 가까우면
# 현관 지그재그도 자동으로 꺼진다.
MIN_START_GAP_M=1.0
while :; do
    START=$(timeout 40 python3 "$HERE/lib/read_pose.py") || {
        echo "❌ 좌표를 읽지 못했습니다"; exit 1; }
    read -r SX SY SYAW <<<"$START"

    GAP=$(python3 -c 'import math,sys; print("%.3f" % math.hypot(
        float(sys.argv[1])-float(sys.argv[3]),
        float(sys.argv[2])-float(sys.argv[4])))' "$SX" "$SY" "$EX" "$EY")

    if python3 -c 'import sys; sys.exit(0 if float(sys.argv[1]) >= float(sys.argv[2]) else 1)' \
        "$GAP" "$MIN_START_GAP_M"; then
        echo "  출발: $START  (현관까지 ${GAP}m)"
        break
    fi

    echo "  ⚠ 현관에서 ${GAP}m 뿐입니다 (최소 ${MIN_START_GAP_M}m)."
    echo "    로봇을 실제로 옮기지 않았을 가능성이 큽니다."
    read -rp "  옮기고 Enter (이대로 쓰려면 s 입력) > " ANSWER
    if [ "$ANSWER" = "s" ]; then
        echo "  ⚠ 경고를 무시하고 ${GAP}m 로 진행합니다"
        echo "  출발: $START"
        break
    fi
done

# 출발 좌표를 sofa(=LIVING_ROOM)와 charging(=DEFAULT)에도 넣는다.
#
# 이 값들을 손으로 관리하면 재매핑 때 갱신을 잊는다 — 2026-08-07 에 실제로
# 그래서 sofa 가 새 지도의 좌표계 밖(y 범위 -1.71~+0.64 인데 1.722)에 남았고,
# LIVING_ROOM 을 쓰는 세 시나리오(보미야 호출·복약 알림·온습도 안부)가 모두
# "지도 밖" 으로 실패할 상태였다. 현관 좌표와 같은 절차로 함께 갱신한다.
#
# 출발 지점을 쓰는 이유: 로봇이 실제로 서 있던 자리라 도달 가능성이 이미
# 증명돼 있는 유일한 지점이다. 시연 대본에서도 어르신 옆 대기 자리이자
# 대화가 끝난 뒤 돌아갈 자리라 셋의 의미가 같다.
python3 - "$WAYPOINTS" "$SX" "$SY" "$SYAW" <<'PY' || exit 1
import re
import sys

path, x, y, yaw = sys.argv[1:5]
text = open(path, encoding="utf-8").read()

# 이름 -> 그 웨이포인트가 무엇을 가리키는지 한 줄 설명.
TARGETS = {
    "sofa": "LIVING_ROOM(보미야 호출·복약·온습도)이 가리키는 지점",
    "charging": "DEFAULT(대기 위치 복귀)가 가리키는 지점",
}

for name, purpose in TARGETS.items():
    block = (
        "  # 실측 좌표. bomi_map.sh 가 출발 좌표를 기록할 때 함께 갱신한다.\n"
        f"  # {purpose}이며, 재매핑하면 무효가 된다.\n"
        f"  - name: {name}\n    x: {x}\n    y: {y}\n    yaw: {yaw}\n"
    )
    # 앞에 붙은 주석 줄까지 함께 갈아끼운다. 남겨두면 옛 근거가 새 좌표
    # 위에 붙어 다음 사람이 잘못된 설명을 읽는다.
    updated = re.sub(
        r"(?:[ ]*#[^\n]*\n)*[ ]*- name: " + name
        + r"\n(?:[ ]+\w+: [-0-9.]+\n)+",
        block,
        text,
        count=1,
    )

    if updated == text:
        print(f"  ❌ room_waypoints.yaml 의 {name} 항목을 찾지 못했습니다")
        sys.exit(1)

    text = updated

open(path, "w", encoding="utf-8").write(text)
print("  sofa(LIVING_ROOM)·charging(DEFAULT) 좌표도 출발 지점으로 갱신했습니다")
PY
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
