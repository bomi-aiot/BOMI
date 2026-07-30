"""번역기 실행 진입점이다.

config(device.yaml)를 읽어 paho-mqtt 로 Pi 로컬 브로커에 접속하고,
Zigbee2MQTT 토픽을 구독해 들어온 메시지를 Translator 로 넘긴다. Translator 가
계약 이벤트를 낼 때는 같은 브로커의 bomi/v1/iot/... 로 발행한다.

사용:

    python main.py [config_path]

기본 config_path 는 ../config/device.yaml (없으면 device.example.yaml).
"""

from __future__ import annotations

import logging
import os
import sys

import paho.mqtt.client as mqtt
import yaml

from translator import Translator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("iot.translator")

_HERE = os.path.dirname(__file__)
_DEFAULT_CONFIG = os.path.join(_HERE, "..", "config", "device.yaml")
_EXAMPLE_CONFIG = os.path.join(_HERE, "..", "config", "device.example.yaml")


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_config_path(argv: list[str]) -> str:
    if len(argv) > 1:
        return argv[1]
    if os.path.exists(_DEFAULT_CONFIG):
        return _DEFAULT_CONFIG
    logger.warning("device.yaml 이 없어 예시 설정(device.example.yaml)으로 실행합니다")
    return _EXAMPLE_CONFIG


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv
    config = load_config(resolve_config_path(argv))

    mqtt_cfg = config.get("mqtt", {})
    host = mqtt_cfg.get("host", "localhost")
    port = int(mqtt_cfg.get("port", 1883))
    qos = int(mqtt_cfg.get("qos", 1))

    client = mqtt.Client(
        protocol=mqtt.MQTTv311,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    username = mqtt_cfg.get("username")
    if username:
        client.username_pw_set(username, mqtt_cfg.get("password"))

    # 계약: retain=false 로 발행.
    def publish(topic: str, payload: str) -> None:
        client.publish(topic, payload, qos=qos, retain=False)

    translator = Translator(config, publish)

    def on_connect(cli, userdata, flags, reason_code, properties=None):
        logger.info("브로커 연결: %s:%s (rc=%s)", host, port, reason_code)
        cli.subscribe(translator.subscribe_topic, qos=qos)
        logger.info("구독: %s", translator.subscribe_topic)

    def on_message(cli, userdata, msg):
        translator.on_zigbee_message(msg.topic, msg.payload, retained=msg.retain)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(host, port)
    logger.info("번역기 시작. 종료하려면 Ctrl+C.")
    client.loop_forever()


if __name__ == "__main__":
    main()
