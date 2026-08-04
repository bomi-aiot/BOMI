#!/usr/bin/env python3
"""BOMI MQTT 테스트 이벤트 발사기.

센서·로봇 하드웨어 없이 계약(docs/mqtt/) 형식 그대로 이벤트를 발행한다.
IoT 발행 코드의 "실행 가능한 정답지"이자, 시연 안전판이다.

사용 예:
    python publish_event.py door                          # 문 열림 → 귀가 시나리오
    python publish_event.py ambient --temp 31.5           # 온습도 (임계값 초과)
    python publish_event.py wake                          # "보미야" 호출
    python publish_event.py walk                          # 산책 요청
    python publish_event.py result --scenario <uuid> --status ARRIVED
    python publish_event.py robot-sim                     # 로봇 흉내: 명령 수신 → 자동 회신
    python publish_event.py door --dry-run                # 발행 없이 메시지만 출력

옵션 공통: --host --port --username --password (기본 localhost:1883)
의존성: pip install paho-mqtt
"""

import argparse
import json
import sys
import time
import uuid
from datetime import datetime

# ---------------------------------------------------------------------------
# 기본값 — 백엔드 설정(application.yml, seed-kim-sunja.sql)과 맞춰져 있다.
# 바꾸면 백엔드 매핑 등록도 함께 바꿔야 한다.
# ---------------------------------------------------------------------------
DEFAULT_DOOR_SENSOR = "door_sensor"          # bomi.homecoming.sensor-to-senior 등록 키
DEFAULT_AMBIENT_SENSOR = "ambient-sensor-01" # bomi.observation.ambient-sensor-to-senior 등록 필요
DEFAULT_ROBOT_ID = "bomi-AA001"              # robot.device_id (김순자 시드)

TOPIC_IOT_EVENTS = "bomi/v1/iot/{device_id}/events"
TOPIC_ROBOT_EVENTS = "bomi/v1/robot/{device_id}/events"
TOPIC_ROBOT_RESULTS = "bomi/v1/robot/{device_id}/results"
TOPIC_ROBOT_COMMANDS = "bomi/v1/robot/{device_id}/commands"

QOS = 1  # 계약: 인바운드는 QoS 1만 허용


def now_iso() -> str:
    """타임존 오프셋 포함 ISO 8601 현재 시각. 계약이 오프셋을 요구한다."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_event_id() -> str:
    """64자 이하 불투명 멱등 키."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# 메시지 빌더 — 계약의 봉투 규칙: sourceId(IoT) / robotId(Robot)는 토픽의
# deviceId와 반드시 일치해야 한다. 불일치 시 백엔드가 조용히 폐기한다.
# ---------------------------------------------------------------------------
def build_door(args):
    topic = TOPIC_IOT_EVENTS.format(device_id=args.sensor)
    body = {
        "eventId": new_event_id(),
        "type": "DOOR_OPENED",
        "occurredAt": now_iso(),
        "sourceId": args.sensor,
        "payload": {"location": "ENTRANCE"},
    }
    return topic, body


def build_ambient(args):
    topic = TOPIC_IOT_EVENTS.format(device_id=args.sensor)
    body = {
        "eventId": new_event_id(),
        "type": "AMBIENT_ENVIRONMENT_OBSERVED",
        "occurredAt": now_iso(),
        "sourceId": args.sensor,
        "payload": {
            "temperatureC": args.temp,
            "humidityPercent": args.humidity,
            "comfortAssessment": args.assessment,
            "observedAt": now_iso(),
        },
    }
    return topic, body


def build_wake(args):
    topic = TOPIC_ROBOT_EVENTS.format(device_id=args.robot)
    body = {
        "eventId": new_event_id(),
        "type": "WAKE_WORD_DETECTED",
        "occurredAt": now_iso(),
        "robotId": args.robot,
        "payload": {"confidence": args.confidence},
    }
    return topic, body


def build_walk(args):
    topic = TOPIC_ROBOT_EVENTS.format(device_id=args.robot)
    body = {
        "eventId": new_event_id(),
        "type": "WALK_REQUESTED",
        "occurredAt": now_iso(),
        "robotId": args.robot,
        "payload": {"source": args.source},
    }
    return topic, body


def build_conv_end(args):
    """대화 종료 이벤트. AI(대화 런타임)가 스텁인 동안 손으로 쏘는 용도."""
    topic = TOPIC_ROBOT_EVENTS.format(device_id=args.robot)
    body = {
        "eventId": new_event_id(),
        "type": "CONVERSATION_ENDED",
        "occurredAt": now_iso(),
        "robotId": args.robot,
        "payload": {"scenarioId": args.scenario},
    }
    return topic, body


def build_result(args):
    """로봇 결과를 수동 발행한다. scenarioId echo가 핵심 계약."""
    topic = TOPIC_ROBOT_RESULTS.format(device_id=args.robot)
    payload = {"scenarioId": args.scenario, "status": args.status}
    if args.reason:
        payload["reason"] = args.reason
    body = {
        "eventId": new_event_id(),
        "type": args.type,
        "occurredAt": now_iso(),
        "robotId": args.robot,
        "payload": payload,
    }
    return topic, body


# ---------------------------------------------------------------------------
# MQTT 연결
# ---------------------------------------------------------------------------
def make_client(args):
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        sys.exit("paho-mqtt가 없습니다: pip install paho-mqtt")
    try:  # paho 2.x
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except (AttributeError, TypeError):  # paho 1.x
        client = mqtt.Client()
    if args.username:
        client.username_pw_set(args.username, args.password or "")
    if args.tls:
        # EC2 프로덕션 브로커는 8883/TLS. --ca-certs 미지정 시 OS 신뢰 저장소 사용.
        client.tls_set(ca_certs=args.ca_certs)
        if args.tls_insecure:
            # 자체서명 인증서 임시 대응. 검증을 끄므로 테스트 용도로만.
            client.tls_insecure_set(True)
    return client


def publish_one(args, topic, body):
    text = json.dumps(body, ensure_ascii=False, indent=2)
    print(f"토픽: {topic}\n{text}")
    if args.dry_run:
        print("(dry-run: 발행 생략)")
        return
    client = make_client(args)
    client.connect(args.host, args.port)
    client.loop_start()
    info = client.publish(topic, json.dumps(body, ensure_ascii=False), qos=QOS, retain=False)
    info.wait_for_publish(timeout=5)
    client.loop_stop()
    client.disconnect()
    print("발행 완료" if info.is_published() else "발행 실패")


# ---------------------------------------------------------------------------
# robot-sim: 로봇 흉내. 명령을 구독해 자동으로 결과를 회신한다.
# 로봇 파트의 Nav2 드라이버가 완성되기 전에 백엔드 시나리오 전체 흐름
# (생성 → NAVIGATE → 도착 → 대화 → 복귀 → COMPLETED)을 검증할 수 있다.
# ---------------------------------------------------------------------------
RESULT_MAP = {
    "NAVIGATE": ("NAVIGATION_RESULT", "ARRIVED"),
    "SPEAK": ("SPEAK_RESULT", "DONE"),
    "CANCEL": ("CANCEL_RESULT", "CANCELLED"),
    "FOLLOW_START": ("FOLLOW_RESULT", "STARTED"),
    "FOLLOW_STOP": ("FOLLOW_RESULT", "STOPPED"),
}


def run_robot_sim(args):
    client = make_client(args)
    cmd_topic = TOPIC_ROBOT_COMMANDS.format(device_id=args.robot)
    res_topic = TOPIC_ROBOT_RESULTS.format(device_id=args.robot)

    def on_message(_client, _userdata, msg, *_extra):
        try:
            command = json.loads(msg.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(f"[robot-sim] JSON 파싱 실패: {msg.payload[:100]!r}")
            return
        ctype = command.get("type", "?")
        scenario_id = command.get("scenarioId")
        print(f"[robot-sim] 명령 수신: {ctype} payload={command.get('payload')} scenarioId={scenario_id}")
        mapped = RESULT_MAP.get(ctype)
        if not mapped:
            print(f"[robot-sim] 모르는 명령 무시: {ctype}")
            return
        result_type, ok_status = mapped
        status = "FAILED" if args.fail else ok_status
        if ctype == "NAVIGATE" and not args.fail:
            print(f"[robot-sim] {args.delay}초 주행 흉내...")
            time.sleep(args.delay)
        body = {
            "eventId": new_event_id(),
            "type": result_type,
            "occurredAt": now_iso(),
            "robotId": args.robot,
            "payload": {"scenarioId": scenario_id, "status": status},
        }
        client.publish(res_topic, json.dumps(body, ensure_ascii=False), qos=QOS, retain=False)
        print(f"[robot-sim] 회신: {result_type} {status}")

    def on_connect(_client, _userdata, _flags, rc, *_extra):
        # paho 1.x는 rc(int), 2.x는 ReasonCode — 문자열로 찍는다.
        print(f"[robot-sim] 브로커 연결(rc={rc}). {cmd_topic} 구독 대기 중... (Ctrl+C 종료)")
        client.subscribe(cmd_topic, qos=QOS)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[robot-sim] 종료")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    # 연결 옵션은 부모 파서로 정의해 모든 하위 명령 "뒤에" 쓸 수 있게 한다.
    # (예: publish_event.py door --host ... --tls)
    conn = argparse.ArgumentParser(add_help=False)
    conn.add_argument("--host", default="localhost")
    conn.add_argument("--port", type=int, default=1883)
    conn.add_argument("--username", default=None)
    conn.add_argument("--password", default=None)
    conn.add_argument("--tls", action="store_true", help="TLS 연결 (EC2 8883 용)")
    conn.add_argument("--ca-certs", default=None, help="CA 인증서 경로 (미지정 시 OS 기본)")
    conn.add_argument("--tls-insecure", action="store_true", help="인증서 검증 생략 (테스트 전용)")
    conn.add_argument("--dry-run", action="store_true", help="발행하지 않고 메시지만 출력")

    parser = argparse.ArgumentParser(description="BOMI MQTT 테스트 이벤트 발사기")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("door", parents=[conn], help="문 열림 → 귀가 시나리오(⑤)")
    p.add_argument("--sensor", default=DEFAULT_DOOR_SENSOR)
    p.set_defaults(builder=build_door)

    p = sub.add_parser("ambient", parents=[conn], help="온습도 관측(①)")
    p.add_argument("--sensor", default=DEFAULT_AMBIENT_SENSOR)
    p.add_argument("--temp", type=float, default=31.0, help="기본 31.0 (임계값 30 초과)")
    p.add_argument("--humidity", type=float, default=50.0)
    p.add_argument("--assessment", default="UNCOMFORTABLE",
                   choices=["COMFORTABLE", "UNCOMFORTABLE"])
    p.set_defaults(builder=build_ambient)

    p = sub.add_parser("wake", parents=[conn], help='"보미야" 호출(③)')
    p.add_argument("--robot", default=DEFAULT_ROBOT_ID)
    p.add_argument("--confidence", type=float, default=0.92)
    p.set_defaults(builder=build_wake)

    p = sub.add_parser("walk", parents=[conn], help="산책 요청(④)")
    p.add_argument("--robot", default=DEFAULT_ROBOT_ID)
    p.add_argument("--source", default="VOICE", choices=["VOICE", "APP"])
    p.set_defaults(builder=build_walk)

    p = sub.add_parser("conv-end", parents=[conn], help="대화 종료 (복귀 유도)")
    p.add_argument("--robot", default=DEFAULT_ROBOT_ID)
    p.add_argument("--scenario", required=True, help="진행 중인 scenarioId")
    p.set_defaults(builder=build_conv_end)

    p = sub.add_parser("result", parents=[conn], help="로봇 결과 수동 발행")
    p.add_argument("--robot", default=DEFAULT_ROBOT_ID)
    p.add_argument("--type", default="NAVIGATION_RESULT",
                   choices=["NAVIGATION_RESULT", "SPEAK_RESULT", "CANCEL_RESULT", "FOLLOW_RESULT"])
    p.add_argument("--scenario", required=True, help="명령에서 받은 scenarioId (echo 필수)")
    p.add_argument("--status", default="ARRIVED")
    p.add_argument("--reason", default=None)
    p.set_defaults(builder=build_result)

    p = sub.add_parser("robot-sim", parents=[conn], help="로봇 흉내: 명령 구독 → 자동 결과 회신")
    p.add_argument("--robot", default=DEFAULT_ROBOT_ID)
    p.add_argument("--delay", type=float, default=3.0, help="NAVIGATE 주행 흉내 시간(초)")
    p.add_argument("--fail", action="store_true", help="모든 명령에 FAILED 회신 (실패 경로 테스트)")

    args = parser.parse_args()
    if args.command == "robot-sim":
        run_robot_sim(args)
    else:
        topic, body = args.builder(args)
        publish_one(args, topic, body)


if __name__ == "__main__":
    main()
