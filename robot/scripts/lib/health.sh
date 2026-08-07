#!/usr/bin/env bash
# 스택이 "떴는지"가 아니라 "움직일 수 있는지"를 확인한다.
#
# 왜 필요한가: 2026-08-07 리허설에서 pico_driver 가 기동 중 죽었는데
# (부팅 직후 Pico 가 'S' 핸드셰이크에 응답하지 못함) 스크립트는
# slam_toolbox 만 보고 "조이스틱으로 지도를 그리세요"를 출력했다.
# 조이스틱 → teleop → /cmd_vel 까지는 멀쩡했고 그걸 받아 모터로 보낼
# 노드만 없었으므로, 화면상 아무 이상이 없는데 로봇만 안 움직였다.
# 프로세스 유무만 보면 이 상태를 놓치므로 구독자 수까지 확인한다.

PICO_PATTERN="core/lib/core/pico_driver"

# 모터 드라이버가 살아 있고 /cmd_vel 이 실제로 이어졌는지 확인한다.
# 실패하면 로그에서 원인 줄만 뽑아 보여주고 1을 돌려준다.
#   $1  런치 출력 로그 경로
bomi_require_pico() {
    local log=$1
    local waited=0

    while [ "$waited" -lt 20 ]; do
        pgrep -f "$PICO_PATTERN" >/dev/null && break
        sleep 1
        waited=$((waited + 1))
    done

    if ! pgrep -f "$PICO_PATTERN" >/dev/null; then
        echo "❌ pico_driver 가 떠 있지 않습니다 — 조이스틱도 자율주행도 안 움직입니다."
        _bomi_pico_reason "$log"
        return 1
    fi

    # 프로세스가 살아 있어도 구독자가 0이면 명령이 아무 데도 가지 않는다.
    # 드라이버가 늦게 붙을 수 있어 몇 초 기다렸다가 판정한다.
    local subs=0
    for _ in 1 2 3 4 5 6; do
        subs=$(timeout 10 ros2 topic info /cmd_vel 2>/dev/null \
            | sed -n 's/^Subscription count: //p')
        [ -n "$subs" ] && [ "$subs" -gt 0 ] 2>/dev/null && break
        sleep 2
    done

    if ! { [ -n "$subs" ] && [ "$subs" -gt 0 ] 2>/dev/null; }; then
        echo "❌ /cmd_vel 구독자가 0입니다 — 조이스틱 명령을 받는 노드가 없습니다."
        _bomi_pico_reason "$log"
        return 1
    fi

    echo "  pico_driver OK (/cmd_vel 구독자 $subs)"
    return 0
}

# 런치 로그에서 pico_driver 가 죽은 이유만 뽑아 보여준다.
# 로그 전체를 읽게 하면 LiDAR·SLAM 잡음에 원인 줄이 묻힌다.
_bomi_pico_reason() {
    local log=$1

    echo
    echo "── 원인 (로그: $log) ──"
    if [ -r "$log" ]; then
        grep -E "pico_driver" "$log" \
            | grep -vE "^\[pico_driver-[0-9]+\] \[INFO\]" \
            | tail -15
    else
        echo "  로그를 읽을 수 없습니다: $log"
    fi
    cat <<'HINT'

자주 겪는 원인:
  · 부팅 직후 첫 실행 — Pico 가 'S' 명령에 아직 응답하지 못한다.
    → 10초 뒤 이 스크립트를 다시 실행하면 대개 붙는다.
  · Pico USB 케이블이 빠졌거나 /dev/ttyACM0 이 다른 프로세스에 잡혀 있다.
    → ls -l /dev/ttyACM0 그리고 pgrep -af ttyACM0 로 확인.
HINT
}
