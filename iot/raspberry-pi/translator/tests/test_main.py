"""실행 설정의 YAML 기본값과 환경변수 우선순위를 검증한다."""

from main import mqtt_connection_settings


def test_mqtt_connection_settings_uses_yaml_values() -> None:
    config = {
        "mqtt": {
            "host": "yaml-broker",
            "port": 1884,
            "qos": 0,
            "username": "yaml-user",
            "password": "yaml-password",
        }
    }

    assert mqtt_connection_settings(config, {}) == {
        "host": "yaml-broker",
        "port": 1884,
        "qos": 0,
        "username": "yaml-user",
        "password": "yaml-password",
    }


def test_mqtt_connection_settings_environment_overrides_yaml() -> None:
    config = {"mqtt": {"host": "yaml-broker", "port": 1884, "qos": 0}}
    environ = {
        "MQTT_HOST": "mqtt",
        "MQTT_PORT": "1883",
        "MQTT_QOS": "1",
        "MQTT_USERNAME": "container-user",
        "MQTT_PASSWORD": "container-password",
    }

    assert mqtt_connection_settings(config, environ) == {
        "host": "mqtt",
        "port": 1883,
        "qos": 1,
        "username": "container-user",
        "password": "container-password",
    }
