"""GPIO4에 연결된 DHT11 값을 읽어 로컬 MQTT 브로커에 발행한다."""

from __future__ import annotations

import logging
import os
import signal
import time

import paho.mqtt.client as mqtt

from ambient_publisher import AmbientPublisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("iot.dht11")


def env_int(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if value <= 0:
        raise ValueError(f"{name}은 1 이상이어야 합니다")
    return value


def main() -> None:
    # board.D4는 BCM GPIO4, 즉 Raspberry Pi 물리 핀 7번이다.
    import adafruit_dht
    import board

    host = os.environ.get("MQTT_HOST", "localhost")
    port = env_int("MQTT_PORT", 1883)
    qos = int(os.environ.get("MQTT_QOS", "1"))
    interval = env_int("READ_INTERVAL_SECONDS", 30)
    # ★ 백엔드 application.yml 의 bomi.observation.ambient-sensor-to-senior
    #   에 등록된 값과 정확히 같아야 한다. 예전 기본값 "living-room-ambient"
    #   는 그 표에 없어 이벤트가 도착해도 어르신에게 매핑되지 않고 조용히
    #   폐기됐다(S15P11E102 통합 스프린트 2-4).
    source_id = os.environ.get("SENSOR_ID", "ambient-sensor-01")
    location = os.environ.get("LOCATION", "LIVING_ROOM")

    client = mqtt.Client(
        protocol=mqtt.MQTTv311,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    )
    username = os.environ.get("MQTT_USERNAME")
    if username:
        client.username_pw_set(username, os.environ.get("MQTT_PASSWORD"))
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(host, port)
    client.loop_start()

    publisher = AmbientPublisher(
        source_id,
        location,
        lambda topic, payload: client.publish(topic, payload, qos=qos, retain=False),
    )
    sensor = adafruit_dht.DHT11(board.D4, use_pulseio=False)
    running = True

    def stop(_signum, _frame) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logger.info("DHT11 수집기 시작: GPIO4, sensorId=%s, interval=%ss", source_id, interval)

    try:
        while running:
            try:
                emitted = publisher.publish_observation(sensor.temperature, sensor.humidity)
                if emitted:
                    logger.info("온습도 이벤트 발행 완료")
                else:
                    logger.warning("DHT11 측정값이 허용 범위를 벗어나 발행하지 않음")
            except RuntimeError as exc:
                # DHT 계열의 일시적인 checksum/timing 오류는 다음 주기에 재시도한다.
                logger.warning("DHT11 읽기 실패, 다음 주기에 재시도: %s", exc)
            time.sleep(interval)
    finally:
        sensor.exit()
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
