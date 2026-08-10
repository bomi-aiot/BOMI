# robot/ai_chat/tests/test_navigation_watch.py
"""이동 중 침묵의 도착 신호 — NavigationArrivalWatcher 회귀.

이 파일이 검증하는 것
    1. v1 NAVIGATION_RESULT 중 SUCCEEDED/ARRIVED 만 신호를 세운다.
    2. 우리 로봇이 아닌 결과, 형식이 깨진 결과, 실패한 결과는 무시한다
       (무시 = 신호를 세우지 않는다. 타임아웃이 그 경우를 책임진다).
    3. reset() 이 지난 신호를 지운다 — 안 지우면 다음 대화가 도착 전에
       곧바로 '이미 도착함'으로 오판한다.
    4. build_navigation_arrival_watcher 의 옵트인 게이트 — 기본값(꺼짐)에서
       개발 환경의 45초 지연 사고를 막는다.

참고
    CLAUDE.md §3a
"""

import json

from bomi_ai_chat.navigation_watch import (
    NavigationArrivalWatcher,
    build_navigation_arrival_watcher,
)

ROBOT_DEVICE_ID = "bomi-AA001"


def navigation_result_json(**overrides) -> str:
    body = {
        "eventId": "evt-1",
        "type": "NAVIGATION_RESULT",
        "occurredAt": "2026-08-04T18:10:08+09:00",
        "robotId": ROBOT_DEVICE_ID,
        "scenarioId": "scenario-1",
        "commandId": "cmd-1",
        "payload": {"outcome": "SUCCEEDED", "resultCode": "ARRIVED", "reasonCode": None},
    }
    body.update(overrides)
    return json.dumps(body)


def _watcher(settings_factory, **extra):
    settings = settings_factory(ROBOT_DEVICE_ID=ROBOT_DEVICE_ID, **extra)
    return NavigationArrivalWatcher(settings=settings)


# ── handle_payload ───────────────────────────────────────────────────────────


def test_arrived_result_sets_the_signal(settings_factory):
    watcher = _watcher(settings_factory)

    handled = watcher.handle_payload(navigation_result_json())

    assert handled is True
    assert watcher.wait_for_arrival(0.0) is True


def test_failed_result_does_not_set_the_signal(settings_factory):
    watcher = _watcher(settings_factory)

    handled = watcher.handle_payload(
        navigation_result_json(
            payload={"outcome": "FAILED", "resultCode": "NOT_ARRIVED",
                     "reasonCode": "PATH_BLOCKED"}
        )
    )

    assert handled is False
    assert watcher.wait_for_arrival(0.0) is False


def test_other_robots_result_is_ignored(settings_factory):
    watcher = _watcher(settings_factory)

    handled = watcher.handle_payload(navigation_result_json(robotId="some-other-robot"))

    assert handled is False
    assert watcher.wait_for_arrival(0.0) is False


def test_non_navigation_result_is_ignored(settings_factory):
    watcher = _watcher(settings_factory)

    handled = watcher.handle_payload(
        navigation_result_json(type="SPEAK_RESULT",
                                payload={"outcome": "SUCCEEDED", "resultCode": "SPOKEN",
                                         "reasonCode": None})
    )

    assert handled is False


def test_malformed_payload_does_not_raise(settings_factory):
    watcher = _watcher(settings_factory)

    assert watcher.handle_payload("not json") is False
    assert watcher.handle_payload(b"\xff\xfe not utf-8") is False
    assert watcher.handle_payload(json.dumps([1, 2, 3])) is False


def test_accepts_bytes_payload(settings_factory):
    watcher = _watcher(settings_factory)

    handled = watcher.handle_payload(navigation_result_json().encode("utf-8"))

    assert handled is True


# ── reset ─────────────────────────────────────────────────────────────────


def test_reset_clears_a_stale_signal(settings_factory):
    """★ 지우지 않으면 다음 대화가 도착 전에 곧바로 '이미 도착함'으로 오판한다."""
    watcher = _watcher(settings_factory)
    watcher.handle_payload(navigation_result_json())
    assert watcher.wait_for_arrival(0.0) is True

    watcher.reset()

    assert watcher.wait_for_arrival(0.0) is False


# ── build_navigation_arrival_watcher 게이트 ──────────────────────────────────


def test_disabled_by_default(settings_factory):
    """★ 기본값이 꺼짐이어야 한다 — 안 그러면 로봇 없는 개발 환경에서
    매 '보미야'가 45초씩 느려진다."""
    settings = settings_factory()

    assert settings.wake_movement_wait_enabled is False
    assert build_navigation_arrival_watcher(settings) is None


def test_enabled_but_mqtt_disabled_builds_nothing(settings_factory, caplog):
    settings = settings_factory(WAKE_MOVEMENT_WAIT_ENABLED="true")

    with caplog.at_level("WARNING"):
        watcher = build_navigation_arrival_watcher(settings)

    assert watcher is None
    assert "MQTT is disabled" in caplog.text


def test_enabled_but_missing_robot_device_id_builds_nothing(settings_factory, caplog):
    settings = settings_factory(
        WAKE_MOVEMENT_WAIT_ENABLED="true",
        MQTT_ENABLED="true", MQTT_BROKER_URL="mqtt://broker.example:1883",
    )

    with caplog.at_level("WARNING"):
        watcher = build_navigation_arrival_watcher(settings)

    assert watcher is None
    assert "ROBOT_DEVICE_ID" in caplog.text


def test_fully_configured_builds_a_watcher(settings_factory):
    settings = settings_factory(
        WAKE_MOVEMENT_WAIT_ENABLED="true",
        MQTT_ENABLED="true", MQTT_BROKER_URL="mqtt://broker.example:1883",
        ROBOT_DEVICE_ID=ROBOT_DEVICE_ID,
    )

    watcher = build_navigation_arrival_watcher(settings)

    assert watcher is not None
