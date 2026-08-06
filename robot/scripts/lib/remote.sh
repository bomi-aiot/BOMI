#!/usr/bin/env bash
# 개발 PC(WSL)에서 로봇에 접속·배포하는 공용 함수.
#
# 환경변수로 바꿀 수 있다:
#   BOMI_HOST     기본 ssafy@192.168.0.27
#   BOMI_REMOTE   로봇 쪽 저장소 경로. 기본 ~/S15P11E102

BOMI_HOST=${BOMI_HOST:-ssafy@192.168.0.27}
BOMI_REMOTE=${BOMI_REMOTE:-\~/S15P11E102}
BOMI_REMOTE_SCRIPTS=$BOMI_REMOTE/robot/scripts

_HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# 저장소의 스크립트를 로봇으로 복사한다. 로봇에 남은 옛 사본을 쓰다가
# 저장소와 동작이 달라지는 일을 막는다.
bomi_deploy() {
    echo "▶ 스크립트 배포 → $BOMI_HOST:$BOMI_REMOTE_SCRIPTS"
    ssh -o ConnectTimeout=10 "$BOMI_HOST" "mkdir -p $BOMI_REMOTE_SCRIPTS/lib"
    scp -q -o ConnectTimeout=10 \
        "$_HERE"/bomi_map.sh "$_HERE"/bomi_goto.sh \
        "$BOMI_HOST:$BOMI_REMOTE_SCRIPTS/"
    scp -q -o ConnectTimeout=10 \
        "$_HERE"/lib/*.py "$_HERE"/lib/cleanup.sh \
        "$BOMI_HOST:$BOMI_REMOTE_SCRIPTS/lib/"
    ssh -o ConnectTimeout=10 "$BOMI_HOST" \
        "chmod +x $BOMI_REMOTE_SCRIPTS/*.sh"
    echo "  완료"
}

# RViz 를 이 PC 화면에 띄우면서, 원격 스크립트의 Enter 입력을 받는다.
#   -t : 원격에 tty 를 준다(read 로 Enter 를 받기 위해 필수)
#   -Y : X11 전달. WSLg 가 X 서버 역할을 한다
bomi_ssh_interactive() {
    DISPLAY=${DISPLAY:-:0} ssh -Y -t \
        -o ServerAliveInterval=30 -o ConnectTimeout=10 \
        "$BOMI_HOST" "bash -lc '$1'"
}
