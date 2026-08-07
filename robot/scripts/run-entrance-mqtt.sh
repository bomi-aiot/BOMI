#!/usr/bin/env bash
# EC2 MQTT 명령을 받아 ENTRANCE 등 백엔드 목적지로 이동한다.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/navigation_runtime.sh
source "$HERE/lib/navigation_runtime.sh"

: "${MQTT_PASSWORD:?먼저 MQTT_PASSWORD 환경변수를 설정하세요.}"

trap 'echo; echo "종료하며 로봇을 정지합니다."; bomi_navigation_finish' EXIT
trap 'exit 130' INT TERM HUP

bomi_navigation_start

echo "문 센서 MQTT 자동 이동 대기 중 (종료: Ctrl+C)"
ros2 launch bridge mqtt_bridge.launch.py \
    driver_type:=nav2 \
    robot_id:="${ROBOT_ID:-bomi-AA001}" \
    broker_host:="${MQTT_BROKER_HOST:-i15e102.p.ssafy.io}" \
    broker_port:="${MQTT_BROKER_PORT:-8883}" \
    use_tls:=true \
    ca_certs:="${MQTT_CA_CERTS:-/etc/ssl/certs/ca-certificates.crt}" \
    username:="${MQTT_USERNAME:-bomi-jetson}" \
    password:="$MQTT_PASSWORD" \
    waypoint_file:="$BOMI_WAYPOINTS" \
    approach_enabled:=false
