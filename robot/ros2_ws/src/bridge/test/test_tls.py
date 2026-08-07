"""MqttBridgeRunner의 TLS(8883) 옵션 배선을 검증한다.

실제 TLS 브로커 없이, paho 클라이언트를 목(mock)으로 바꿔 tls_set/username 등이
올바르게 호출되는지 확인한다.
"""

from unittest import mock

from bridge.mqtt_client import MqttBridgeRunner


def test_tls_enabled_calls_tls_set_and_auth() -> None:
    with mock.patch("bridge.mqtt_client.mqtt.Client") as mock_client:
        client = mock_client.return_value
        MqttBridgeRunner(
            "robot-01", "broker.example", 8883,
            use_tls=True, username="robot", password="secret",
        )
        client.tls_set.assert_called_once_with(ca_certs=None)
        client.username_pw_set.assert_called_once_with("robot", "secret")


def test_tls_disabled_does_not_call_tls_set() -> None:
    with mock.patch("bridge.mqtt_client.mqtt.Client") as mock_client:
        client = mock_client.return_value
        MqttBridgeRunner("robot-01", "localhost", 1883)
        client.tls_set.assert_not_called()


def test_tls_insecure_sets_flag() -> None:
    with mock.patch("bridge.mqtt_client.mqtt.Client") as mock_client:
        client = mock_client.return_value
        MqttBridgeRunner(
            "robot-01", "broker.example", 8883, use_tls=True, tls_insecure=True
        )
        client.tls_insecure_set.assert_called_once_with(True)


def test_custom_ca_certs_passed_through() -> None:
    with mock.patch("bridge.mqtt_client.mqtt.Client") as mock_client:
        client = mock_client.return_value
        MqttBridgeRunner(
            "robot-01", "broker.example", 8883,
            use_tls=True, ca_certs="/etc/ssl/certs/ca.pem",
        )
        client.tls_set.assert_called_once_with(ca_certs="/etc/ssl/certs/ca.pem")
