#!/usr/bin/env bash
# 백엔드가 보내는 것과 같은 NAVIGATE 명령을 브로커로 발행한다.
#
#   robot/scripts/send_navigate.sh [ENTRANCE|LIVING_ROOM|DEFAULT] [브로커호스트]
#
# 기본값은 ENTRANCE, localhost 다.
#
# 왜 스크립트로 두는가: 계약이 요구하는 occurredAt/expiresAt 은 발행 시각을
# 기준으로 해야 한다. 예시 JSON 을 복사해 쓰면 시간이 지난 뒤에는 그대로
# 만료되어 브릿지가 COMMAND_EXPIRED 로 회신한다(2026-08-07 실제로 겪음).
# 여기서 매번 현재 시각으로 만들면 그 함정이 사라진다.
#
# commandId 도 매번 새로 만든다. 같은 commandId 를 다시 보내면 계약상
# 중복 실행하지 않고 이전 결과를 유지하므로, 로봇이 움직이지 않는다.
set -euo pipefail

TARGET=${1:-ENTRANCE}
BROKER=${2:-localhost}
ROBOT_ID=${ROBOT_ID:-robot-01}
EXPIRES_IN=${EXPIRES_IN:-2 minutes}

case "$TARGET" in
    ENTRANCE|LIVING_ROOM|DEFAULT) ;;
    *)
        echo "❌ target 은 ENTRANCE|LIVING_ROOM|DEFAULT 중 하나여야 합니다: $TARGET" >&2
        exit 2
        ;;
esac

TOPIC="bomi/v1/robot/${ROBOT_ID}/commands"
COMMAND_ID="cmd-$(date +%s)"
OCCURRED_AT=$(date -Iseconds)
EXPIRES_AT=$(date -Iseconds -d "+${EXPIRES_IN}")

read -r -d '' PAYLOAD <<EOF || true
{"commandId":"${COMMAND_ID}",
 "scenarioId":"11111111-1111-1111-1111-111111111111",
 "robotId":"${ROBOT_ID}",
 "type":"NAVIGATE",
 "occurredAt":"${OCCURRED_AT}",
 "expiresAt":"${EXPIRES_AT}",
 "payload":{"target":"${TARGET}"}}
EOF

echo "▶ ${TOPIC}"
echo "  target=${TARGET}  commandId=${COMMAND_ID}"
echo "  occurredAt=${OCCURRED_AT}  expiresAt=${EXPIRES_AT}"

# QoS 1 필수. QoS 0 은 백엔드 계약에서 폐기 대상이다(CLAUDE.md 2절).
mosquitto_pub -h "$BROKER" -q 1 -t "$TOPIC" -m "$PAYLOAD"

echo "  발행 완료 — 결과는 bomi/v1/robot/${ROBOT_ID}/results 에서 확인하세요"
