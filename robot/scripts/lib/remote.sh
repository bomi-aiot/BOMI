#!/usr/bin/env bash
# 개발 PC(WSL)에서 로봇에 접속·배포하는 공용 함수.
#
# 접속 대상은 세 곳에서 온다. 뒤로 갈수록 우선한다.
#   1. 저장소 기본값 (아래 ssafy@192.168.30.30 — 강의장 와이파이 기준)
#   2. robot/scripts/demo_host.local.sh  (개인 설정, 저장소에 안 들어간다)
#   3. 환경변수 BOMI_HOST
#   4. --host 옵션
#
# 2번이 있는 이유: 로봇 IP 는 네트워크마다 바뀌는데(강의장 ↔ 집 ↔ DHCP 재할당)
# 저장소 기본값은 누군가에게는 항상 틀린 값이다. 매번 --host 를 붙이는 대신
# 한 번 적어두고 쓴다. 개인 환경 값이라 커밋하지 않는다.
#
#   echo 'BOMI_HOST=home' > robot/scripts/demo_host.local.sh
#
# IP 대신 별칭을 쓸 수 있다(아래 _bomi_resolve_alias). 네트워크가 바뀔 때
# 외워야 할 것이 주소가 아니라 장소 이름이면 된다.
#
#   demo-map.sh --host home bomi_real_20
#
#   BOMI_REMOTE   로봇 쪽 저장소 경로. 기본 ~/S15P11E102

_HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

# 네트워크별 로봇 주소. 새 장소가 생기면 여기 한 줄 추가한다.
#
# 별칭 해석은 계정명을 붙이기 '전'에 해야 한다 — 별칭 ssafy 와 계정명 ssafy 가
# 같은 글자라, 순서가 바뀌면 ssafy 가 ssafy@ssafy 로 풀린다.
_bomi_resolve_alias() {
    case "$1" in
        ssafy)     echo 192.168.30.30 ;;   # 강의장 와이파이
        home)      echo 192.168.0.12 ;;    # 집
        dkhotspot) echo 10.113.168.103 ;;  # 핫스팟
        *)         echo "$1" ;;            # 별칭이 아니면 그대로 (IP·호스트명)
    esac
}

_BOMI_HOST_DEFAULT=ssafy
# 로컬 파일은 BOMI_HOST 에 그냥 대입한다. 그래서 환경변수를 먼저 챙겨두지
# 않으면 파일이 그것을 덮어써 우선순위가 뒤집힌다.
_BOMI_HOST_ENV=${BOMI_HOST:-}
if [ -f "$_HERE/demo_host.local.sh" ]; then
    # shellcheck source=/dev/null
    source "$_HERE/demo_host.local.sh"
fi

BOMI_HOST=${_BOMI_HOST_ENV:-${BOMI_HOST:-$_BOMI_HOST_DEFAULT}}
BOMI_REMOTE=${BOMI_REMOTE:-\~/S15P11E102}
BOMI_REMOTE_SCRIPTS=$BOMI_REMOTE/robot/scripts

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
    # 별칭 -> 주소. 계정명이 붙어 있으면 주소 부분만 바꾼다.
    local user="" addr="$BOMI_HOST"
    case "$BOMI_HOST" in
        *@*) user=${BOMI_HOST%@*}; addr=${BOMI_HOST#*@} ;;
    esac
    addr=$(_bomi_resolve_alias "$addr")
    BOMI_HOST="${user:-ssafy}@$addr"
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
