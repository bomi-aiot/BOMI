"""브릿지 코어를 실제 MQTT 브로커에 연결하는 paho-mqtt 어댑터다.

이 모듈은 "전송 계층"만 담당한다. 브로커 연결, 명령 토픽 구독, 수신 메시지를
브릿지 코어(:class:`MqttBridge`)로 전달, 코어가 만든 결과를 브로커로 발행하는
배선만 한다. 명령 해석과 결과 생성 같은 규칙은 코어에 있으므로 이 어댑터는 얇다.

계약상 인바운드/아웃바운드 모두 QoS 1, retain=false를 사용한다(백엔드가 이를
요구한다). 주행 실행은 기본적으로 :class:`MockRobotDriver` 를 주입하며, 실물
전환 시 이 기본값 한 곳만 바꾸면 된다.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
import os
import threading
from typing import Callable

import paho.mqtt.client as mqtt

from bridge.mqtt_bridge import MqttBridge
from bridge.robot_driver import MockRobotDriver, RobotDriver

logger = logging.getLogger(__name__)

DEFAULT_QOS = 1


class SingleFlightExecutor:
    """
    동시에 하나의 NAVIGATE 작업만 받는 비차단 실행기다.

    ``submit``은 작업을 전용 스레드에 넘기고 즉시 반환한다. 실행 중 새 작업은
    큐에 쌓지 않고 False로 거부하여 이동 시간이 연장되거나 겹치지 않게 한다.
    """

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="mqtt-navigation",
        )
        self._lock = threading.Lock()
        self._busy = False
        self._closed = False

    def submit(self, task: Callable[[], None]) -> bool:
        """실행 중인 작업이 없으면 task를 예약하고 승인 여부를 반환한다."""
        with self._lock:
            if self._closed or self._busy:
                return False
            self._busy = True

        try:
            self._executor.submit(self._run, task)
        except Exception:
            with self._lock:
                self._busy = False
            raise
        return True

    def shutdown(self) -> None:
        """새 작업을 막고 현재 작업이 안전하게 끝날 때까지 기다린다."""
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=True)

    def _run(self, task: Callable[[], None]) -> None:
        try:
            task()
        finally:
            with self._lock:
                self._busy = False


class MqttBridgeRunner:
    """paho-mqtt 클라이언트와 브릿지 코어를 연결해 구동하는 러너다."""

    def __init__(
        self,
        robot_id: str,
        host: str,
        port: int,
        *,
        driver: RobotDriver | None = None,
        username: str | None = None,
        password: str | None = None,
        client_id: str | None = None,
        use_tls: bool = False,
        ca_certs: str | None = None,
        tls_insecure: bool = False,
        nonblocking_navigation: bool = False,
    ) -> None:
        self._robot_id = robot_id
        self._host = host
        self._port = port
        self._driver = driver or MockRobotDriver()
        self._navigation_executor = (
            SingleFlightExecutor() if nonblocking_navigation else None
        )
        self._stopped = False

        self._client = mqtt.Client(
            client_id=client_id or f"bomi-robot-bridge-{robot_id}",
            protocol=mqtt.MQTTv311,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        if username:
            self._client.username_pw_set(username, password)

        # 젯슨/외부에서 EC2 브로커 8883(TLS)에 붙을 때 사용한다. 서버 인증서만
        # 검증하면 되며(브로커가 require_certificate false), ca_certs=None이면
        # 시스템 CA 저장소(Let's Encrypt 포함)를 쓴다. tls_insecure는 개발용.
        if use_tls:
            self._client.tls_set(ca_certs=ca_certs)
            if tls_insecure:
                self._client.tls_insecure_set(True)

        self._bridge = MqttBridge(
            robot_id,
            self._driver,
            self._publish,
            submit_navigation=(
                self._navigation_executor.submit
                if self._navigation_executor is not None
                else None
            ),
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def _publish(self, topic: str, payload: str) -> None:
        self._client.publish(topic, payload, qos=DEFAULT_QOS, retain=False)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        topic = self._bridge.commands_topic
        client.subscribe(topic, qos=DEFAULT_QOS)
        logger.info("브로커 연결됨, 명령 구독: %s", topic)

    def _on_message(self, client, userdata, message) -> None:
        self._bridge.on_command(message.payload)

    def start(self) -> None:
        """브로커에 연결하고 메시지 루프를 블로킹으로 실행한다."""
        self._client.connect(self._host, self._port)
        self._client.loop_forever()

    def connect_and_loop_start(self) -> None:
        """브로커에 연결하고 백그라운드 루프를 시작한다(테스트/비블로킹용)."""
        self._client.connect(self._host, self._port)
        self._client.loop_start()

    def stop(self) -> None:
        """명령 수신을 멈추고 드라이버 정지 후 브로커 연결을 종료한다."""
        if self._stopped:
            return
        self._stopped = True
        self._client.loop_stop()
        self._driver.shutdown()
        if self._navigation_executor is not None:
            self._navigation_executor.shutdown()
        self._client.disconnect()


def main() -> None:
    """환경변수로 설정을 읽어 브릿지 러너를 블로킹 실행한다.

    사용 환경변수: ``ROBOT_ID``, ``MQTT_BROKER_HOST``, ``MQTT_BROKER_PORT``,
    ``MQTT_USERNAME``, ``MQTT_PASSWORD``, ``MQTT_TLS``(true/false),
    ``MQTT_CA_CERTS``(CA 경로, 생략 시 시스템 CA), ``MQTT_TLS_INSECURE``.

    ``MQTT_TLS=true`` 이고 포트를 지정하지 않으면 8883을 기본값으로 쓴다.
    """
    logging.basicConfig(level=logging.INFO)
    use_tls = os.environ.get("MQTT_TLS", "false").lower() in ("1", "true", "yes")
    default_port = "8883" if use_tls else "1883"
    runner = MqttBridgeRunner(
        robot_id=os.environ.get("ROBOT_ID", "robot-01"),
        host=os.environ.get("MQTT_BROKER_HOST", "localhost"),
        port=int(os.environ.get("MQTT_BROKER_PORT", default_port)),
        username=os.environ.get("MQTT_USERNAME") or None,
        password=os.environ.get("MQTT_PASSWORD") or None,
        use_tls=use_tls,
        ca_certs=os.environ.get("MQTT_CA_CERTS") or None,
        tls_insecure=os.environ.get("MQTT_TLS_INSECURE", "false").lower()
        in ("1", "true", "yes"),
    )
    try:
        runner.start()
    except KeyboardInterrupt:
        runner.stop()


if __name__ == "__main__":
    main()
