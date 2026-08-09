"""주행 상태 훅(LCD "이동 중" 표시)의 발행 순서를 검증한다.

★ 이 훅이 왜 생겼나 (2026-08-10)
    bomi_display 의 DisplayStateModel 은 처음부터 /bomi/nav_status 를 받아
    "이동 중"을 띄우도록 만들어져 있었는데, **그 토픽을 발행하는 곳이 없었다.**
    그래서 화면은 /cmd_vel 움직임 감지에만 의존했고, 그건 "바퀴가 돌았다"만
    알 뿐 "목표를 향해 가는 중"인지 몰라 대화 표시(생각하는 중)에 덮였다.
    "보미야"를 부르면 이동 내내 "생각하는 중"이 뜨던 것이 그 결과다.

여기서 고정하는 것
    * NAVIGATE 를 시작하면 NAVIGATING, 끝나면 IDLE 이 **순서대로** 나간다.
    * 주행이 실패하거나 예외로 죽어도 IDLE 이 반드시 나간다 — 안 나가면
      멈춰 선 로봇이 화면에서는 영원히 가는 중이다.
    * 훅이 터져도 명령 처리는 계속된다.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json

from bridge import contract
from bridge.mqtt_bridge import MqttBridge
from bridge.robot_driver import MockRobotDriver

_NOW_ISO = "2026-08-10T01:00:00+09:00"
# 시각을 주입해 만료 검사를 결정적으로 만든다(test_mqtt_bridge.py 와 같은 방식).
_NOW = datetime(2026, 8, 9, 16, 0, tzinfo=timezone.utc)


class _Collector:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def __call__(self, topic: str, payload: str) -> None:
        self.messages.append((topic, payload))


class _ExplodingDriver(MockRobotDriver):
    def navigate(self, target: str) -> str:
        raise RuntimeError("motor board is gone")


class _FailingDriver(MockRobotDriver):
    def navigate(self, target: str) -> str:
        return contract.STATUS_FAILED


def _make(driver=None):
    states: list[str] = []
    bridge = MqttBridge(
        "robot-01",
        driver or MockRobotDriver(),
        _Collector(),
        now=lambda: _NOW,
        on_navigation_state=states.append,
    )
    return bridge, states


def _navigate(target: str = "LIVING_ROOM", command_id: str = "cmd-1") -> str:
    return json.dumps({
        "commandId": command_id,
        "scenarioId": "scenario-1",
        "robotId": "robot-01",
        "type": contract.CMD_NAVIGATE,
        "occurredAt": _NOW_ISO,
        "expiresAt": "2026-08-10T01:02:00+09:00",
        "payload": {"target": target},
    })


def test_navigation_publishes_navigating_then_idle() -> None:
    bridge, states = _make()

    bridge.on_command(_navigate())

    assert states == [contract.NAV_STATE_NAVIGATING, contract.NAV_STATE_IDLE]


def test_idle_is_published_even_when_navigation_fails() -> None:
    """실패해도 표시는 내린다 — 안 내리면 화면이 영원히 '이동 중'이다."""
    bridge, states = _make(_FailingDriver())

    bridge.on_command(_navigate())

    assert states == [contract.NAV_STATE_NAVIGATING, contract.NAV_STATE_IDLE]


def test_idle_is_published_even_when_the_driver_raises() -> None:
    bridge, states = _make(_ExplodingDriver())

    bridge.on_command(_navigate())

    assert states == [contract.NAV_STATE_NAVIGATING, contract.NAV_STATE_IDLE]


def test_unknown_target_never_claims_to_be_driving() -> None:
    """목적지를 못 알아들으면 주행 자체를 시작하지 않으므로 표시도 없다."""
    bridge, states = _make()

    bridge.on_command(_navigate(target="BATHROOM"))

    assert states == []


def test_a_broken_hook_does_not_stop_the_command() -> None:
    """표시 실패가 주행이나 결과 회신을 죽이면 안 된다."""
    collector = _Collector()

    def boom(state: str) -> None:
        raise RuntimeError("no display")

    bridge = MqttBridge(
        "robot-01",
        MockRobotDriver(),
        collector,
        now=lambda: _NOW,
        on_navigation_state=boom,
    )

    bridge.on_command(_navigate())

    # 결과는 정상적으로 회신됐다.
    assert collector.messages
    topic, payload = collector.messages[-1]
    assert json.loads(payload)["payload"]["outcome"] == contract.OUTCOME_SUCCEEDED


def test_no_hook_is_allowed() -> None:
    """순수 paho 경로처럼 훅이 없는 실행 경로도 그대로 동작한다."""
    collector = _Collector()
    bridge = MqttBridge(
        "robot-01", MockRobotDriver(), collector, now=lambda: _NOW)

    bridge.on_command(_navigate())

    assert collector.messages
