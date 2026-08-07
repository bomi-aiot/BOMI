#!/usr/bin/env bash
# 개발 PC(WSL)에서 로봇에 접속·배포하는 공용 함수.
#
# 환경변수로 바꿀 수 있다:
#   BOMI_HOST     기본 ssafy@192.168.30.30 (강의장 와이파이 기준)
#   BOMI_REMOTE   로봇 쪽 저장소 경로. 기본 ~/S15P11E102

BOMI_HOST=${BOMI_HOST:-ssafy@192.168.30.30}
BOMI_REMOTE=${BOMI_REMOTE:-\~/S15P11E102}
BOMI_REMOTE_SCRIPTS=$BOMI_REMOTE/robot/scripts

_HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# 인자에서 접속 대상을 뽑아내고, 나머지를 BOMI_ARGS 에 남긴다.
# 네트워크가 바뀌면 IP 도 바뀌므로(강의장 ↔ 집) 파일을 고치지 않고
# 실행할 때 지정할 수 있어야 한다.
#
#   --host 192.168.30.30    사용자명 생략 시 ssafy 를 붙인다
#   --host pi@192.168.0.5   사용자명을 직접 줄 수도 있다
#   --host=192.168.30.30    = 형태도 받는다
#
# 환경변수 BOMI_HOST 보다 이 옵션이 우선한다.
bomi_parse_host() {
    BOMI_ARGS=()
    while [ $# -gt 0 ]; do
        case "$1" in
            --host)
                [ $# -ge 2 ] || { echo "--host 뒤에 IP 가 없습니다" >&2; exit 2; }
                BOMI_HOST=$2
                shift 2
                ;;
            --host=*)
                BOMI_HOST=${1#--host=}
                shift
                ;;
            *)
                BOMI_ARGS+=("$1")
                shift
                ;;
        esac
    done
    # 사용자명이 없으면 로봇 계정을 붙인다.
    case "$BOMI_HOST" in
        *@*) ;;
        *) BOMI_HOST=ssafy@$BOMI_HOST ;;
    esac
}

# 저장소의 스크립트를 로봇으로 복사한다. 로봇에 남은 옛 사본을 쓰다가
# 저장소와 동작이 달라지는 일을 막는다.
bomi_deploy() {
    echo "▶ 스크립트 배포 → $BOMI_HOST:$BOMI_REMOTE_SCRIPTS"
    ssh -o ConnectTimeout=10 "$BOMI_HOST" "mkdir -p $BOMI_REMOTE_SCRIPTS/lib"
    scp -q -o ConnectTimeout=10 \
        "$_HERE"/bomi_map.sh "$_HERE"/bomi_goto.sh \
        "$BOMI_HOST:$BOMI_REMOTE_SCRIPTS/"
    # lib 아래 .sh 를 통째로 보낸다. 파일을 새로 만들 때마다 이 목록에
    # 추가하는 걸 잊으면, 로봇에서 source 가 실패해 스크립트가 첫 줄부터 죽는다.
    scp -q -o ConnectTimeout=10 \
        "$_HERE"/lib/*.py "$_HERE"/lib/*.sh \
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
