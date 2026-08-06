"""통신 테스트 전진 드라이버의 속도 발행과 안전 정지를 검증한다."""

from datetime import datetime, timezone
import json
import threading

from bridge import contract
from bridge.forward_test_robot_driver import ForwardTestRobotDriver
from bridge.mqtt_bridge import MqttBridge
from bridge.mqtt_client import SingleFlightExecutor
import pytest


class _Clock:
    """테스트가 직접 진행시키는 단조 시계다."""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class _Logger:
    """ROS 로거 호출을 받아들이는 테스트 대역이다."""

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


class _Publisher:
    """발행된 Twist를 복사해 보관하고 선택적으로 예외를 발생시킨다."""

    def __init__(self) -> None:
        self.messages: list[tuple[float, float]] = []
        self.first_message = threading.Event()
        self.fail_on_call: int | None = None
        self.call_count = 0

    def publish(self, message) -> None:
        self.call_count += 1
        if self.call_count == self.fail_on_call:
            raise RuntimeError("publish failed")
        self.messages.append((message.linear.x, message.angular.z))
        self.first_message.set()


class _Timer:
    """callback을 수동 호출할 수 있는 ROS timer 대역이다."""

    def __init__(self, period: float, callback) -> None:
        self.period = period
        self.callback = callback


class _Node:
    """publisher와 timer 생성만 제공하는 ROS 노드 대역이다."""

    def __init__(self) -> None:
        self.publisher = _Publisher()
        self.timer: _Timer | None = None
        self.topic: str | None = None
        self.timer_destroyed = False
        self.logger = _Logger()

    def get_logger(self):
        return self.logger

    def create_publisher(self, message_type, topic: str, qos: int):
        self.topic = topic
        return self.publisher

    def create_timer(self, period: float, callback):
        self.timer = _Timer(period, callback)
        return self.timer

    def destroy_timer(self, timer) -> None:
        self.timer_destroyed = True


def _create_driver():
    node = _Node()
    clock = _Clock()
    driver = ForwardTestRobotDriver(node, clock=clock)
    return driver, node, clock


def _start_navigation(driver, target: str):
    results: list[str] = []
    thread = threading.Thread(
        target=lambda: results.append(driver.navigate(target))
    )
    thread.start()
    return thread, results


@pytest.mark.parametrize(
    "target",
    [
        contract.TARGET_ENTRANCE,
        contract.TARGET_DEFAULT,
        contract.TARGET_LIVING_ROOM,
    ],
)
def test_valid_target_moves_forward_then_stops(target: str) -> None:
    driver, node, clock = _create_driver()

    thread, results = _start_navigation(driver, target)
    assert node.publisher.first_message.wait(timeout=1.0)
    assert node.publisher.messages[-1] == pytest.approx((0.08, 0.0))

    node.timer.callback()
    assert node.publisher.messages[-1] == pytest.approx((0.08, 0.0))

    clock.value = 2.0
    node.timer.callback()
    thread.join(timeout=1.0)

    assert thread.is_alive() is False
    assert node.publisher.messages[-1] == pytest.approx((0.0, 0.0))
    assert results == [contract.STATUS_ARRIVED]
    assert node.topic == "/cmd_vel_backend_test"
    assert node.timer.period == pytest.approx(0.1)


def test_speak_does_not_publish_velocity() -> None:
    driver, node, _clock = _create_driver()

    assert driver.speak("hello") == contract.STATUS_DONE
    assert node.publisher.messages == []


def test_cancel_stops_active_motion_without_starting_another() -> None:
    driver, node, _clock = _create_driver()
    thread, results = _start_navigation(driver, contract.TARGET_ENTRANCE)
    assert node.publisher.first_message.wait(timeout=1.0)

    assert driver.cancel() == contract.STATUS_CANCELLED
    thread.join(timeout=1.0)

    assert node.publisher.messages[-1] == pytest.approx((0.0, 0.0))
    assert results == [contract.STATUS_FAILED]


def test_second_navigation_is_rejected_while_moving() -> None:
    driver, node, _clock = _create_driver()
    thread, first_results = _start_navigation(
        driver, contract.TARGET_ENTRANCE
    )
    assert node.publisher.first_message.wait(timeout=1.0)

    second = driver.navigate(contract.TARGET_LIVING_ROOM)
    driver.cancel()
    thread.join(timeout=1.0)

    assert second == contract.STATUS_FAILED
    assert first_results == [contract.STATUS_FAILED]


def test_publish_error_issues_stop_and_returns_failed() -> None:
    driver, node, _clock = _create_driver()
    node.publisher.fail_on_call = 2
    thread, results = _start_navigation(driver, contract.TARGET_ENTRANCE)
    assert node.publisher.first_message.wait(timeout=1.0)

    node.timer.callback()
    thread.join(timeout=1.0)

    assert results == [contract.STATUS_FAILED]
    assert node.publisher.messages[-1] == pytest.approx((0.0, 0.0))


def test_shutdown_stops_motion_and_releases_waiter() -> None:
    driver, node, _clock = _create_driver()
    thread, results = _start_navigation(driver, contract.TARGET_ENTRANCE)
    assert node.publisher.first_message.wait(timeout=1.0)

    driver.shutdown()
    thread.join(timeout=1.0)

    assert results == [contract.STATUS_FAILED]
    assert node.publisher.messages[-1] == pytest.approx((0.0, 0.0))
    assert node.timer_destroyed is True


def test_bridge_publishes_result_only_after_forward_stop() -> None:
    driver, node, clock = _create_driver()
    executor = SingleFlightExecutor()
    results: list[tuple[str, str]] = []
    bridge = MqttBridge(
        "robot-01",
        driver,
        lambda topic, payload: results.append((topic, payload)),
        submit_navigation=executor.submit,
        now=lambda: datetime(2026, 8, 6, tzinfo=timezone.utc),
    )
    command = json.dumps(
        {
            "commandId": "drive-integration-1",
            "scenarioId": "scenario-integration",
            "robotId": "robot-01",
            "type": contract.CMD_NAVIGATE,
            "occurredAt": "2026-08-06T09:00:00+09:00",
            "expiresAt": "2026-08-06T10:00:00+09:00",
            "payload": {"target": contract.TARGET_LIVING_ROOM},
        }
    )

    bridge.on_command(command)
    assert node.publisher.first_message.wait(timeout=1.0)
    assert results == []

    clock.value = 2.0
    node.timer.callback()
    executor.shutdown()

    assert node.publisher.messages[-1] == pytest.approx((0.0, 0.0))
    topic, payload = results[0]
    envelope = json.loads(payload)
    assert topic == contract.robot_results_topic("robot-01")
    assert envelope["type"] == contract.RESULT_NAVIGATION
    assert envelope["payload"]["scenarioId"] == "scenario-integration"
    assert envelope["payload"]["status"] == contract.STATUS_ARRIVED


@pytest.mark.parametrize(
    "overrides",
    [
        {"forward_speed_m_s": 0.0},
        {"forward_speed_m_s": 0.2},
        {"forward_duration_seconds": 0.0},
        {"publish_rate_hz": 0.0},
        {"command_topic": ""},
    ],
)
def test_invalid_parameters_are_rejected(overrides: dict) -> None:
    with pytest.raises(ValueError):
        ForwardTestRobotDriver(_Node(), **overrides)
