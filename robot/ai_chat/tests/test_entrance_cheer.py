"""현관 이동 환호(entrance_cheer)의 판정 로직 검증.

브로커 없이 handle_payload 만 본다 — 어떤 메시지에 외치고 어떤 메시지에
침묵하는가가 이 기능의 전부다. 특히 **현관이 아닌 이동에는 절대 외치지
않는다**와 **같은 명령에 두 번 외치지 않는다**를 고정한다.
"""

from __future__ import annotations

import json
import threading

import pytest

from bomi_ai_chat.entrance_cheer import (
    DEFAULT_CHEER_TEXT,
    EntranceCheerWatcher,
    build_entrance_cheer_watcher,
    split_phrases,
)


class _ImmediateThread:
    """start() 가 곧바로 target 을 실행하는 가짜 스레드."""

    def __init__(self, target=None, daemon=None) -> None:
        self._target = target
        self.daemon = daemon

    def start(self) -> None:
        self._target()


class _Settings:
    robot_device_id = "bomi-AA001"
    mqtt_enabled = True
    mqtt_broker_url = "mqtts://example.invalid:8883"
    mqtt_username = "u"
    mqtt_password = "p"
    mqtt_client_id = "test"

    def validate_mqtt(self) -> None:
        pass


class _Clock:
    """테스트가 20초를 실제로 기다릴 수는 없다. sleep 이 시계를 밀어 준다."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _make(**kwargs):
    spoken: list[str] = []
    clock = kwargs.pop("clock", None) or _Clock()
    watcher = EntranceCheerWatcher(
        spoken.append,
        settings=_Settings(),
        thread_factory=_ImmediateThread,
        clock=clock,
        sleep=clock.sleep,
        **kwargs,
    )
    return watcher, spoken


def _command(target: str = "ENTRANCE", **overrides) -> str:
    body = {
        "commandId": "cmd-1",
        "scenarioId": "sc-1",
        "robotId": "bomi-AA001",
        "type": "NAVIGATE",
        "payload": {"target": target},
    }
    body.update(overrides)
    return json.dumps(body)


def test_cheers_when_navigating_to_the_entrance() -> None:
    watcher, spoken = _make()

    assert watcher.handle_payload(_command()) is True
    # 기본 문구는 여러 마디다 — 현관까지 가는 15~30초를 소리로 채우기 위해서다.
    assert spoken == split_phrases(DEFAULT_CHEER_TEXT)
    assert len(spoken) > 1


def test_stays_quiet_for_other_targets() -> None:
    """거실·복귀 이동에는 외치지 않는다."""
    for target in ("LIVING_ROOM", "DEFAULT"):
        watcher, spoken = _make()
        assert watcher.handle_payload(_command(target)) is False
        assert spoken == []


def test_stays_quiet_for_other_command_types() -> None:
    watcher, spoken = _make()

    assert watcher.handle_payload(_command(type="CANCEL")) is False
    assert spoken == []


def test_ignores_commands_for_another_robot() -> None:
    watcher, spoken = _make()

    assert watcher.handle_payload(_command(robotId="other-robot")) is False
    assert spoken == []


def test_does_not_cheer_twice_for_the_same_command() -> None:
    """QoS 1 재배달이나 백엔드 재전송으로 같은 명령이 또 와도 한 번만 외친다."""
    watcher, spoken = _make()

    assert watcher.handle_payload(_command()) is True
    assert watcher.handle_payload(_command()) is False
    assert spoken == split_phrases(DEFAULT_CHEER_TEXT)


def test_cheers_again_for_a_new_command() -> None:
    """다음 귀가는 새 commandId 이므로 다시 외친다."""
    watcher, spoken = _make()

    watcher.handle_payload(_command())
    assert watcher.handle_payload(_command(commandId="cmd-2")) is True
    assert spoken == split_phrases(DEFAULT_CHEER_TEXT) * 2


@pytest.mark.parametrize(
    "raw",
    [b"not json", "[]", "{}", json.dumps({"type": "NAVIGATE"})],
)
def test_broken_payloads_are_ignored(raw) -> None:
    """형식이 깨져도 예외를 던지지 않는다 — 환호는 곁가지다."""
    watcher, spoken = _make()

    assert watcher.handle_payload(raw) is False
    assert spoken == []


def test_speak_failure_does_not_escape() -> None:
    """재생이 실패해도 예외가 위로 새지 않는다."""

    def boom(text: str) -> None:
        raise RuntimeError("speaker is gone")

    watcher = EntranceCheerWatcher(
        boom, settings=_Settings(), thread_factory=_ImmediateThread)

    assert watcher.handle_payload(_command()) is True


def test_custom_text_is_used() -> None:
    watcher, spoken = _make(text="다 왔어요")

    watcher.handle_payload(_command())
    assert spoken == ["다 왔어요"]


def test_disabled_by_environment(monkeypatch) -> None:
    monkeypatch.setenv("ENTRANCE_CHEER_ENABLED", "0")

    assert build_entrance_cheer_watcher(lambda text: None, _Settings()) is None


def test_not_built_without_mqtt(monkeypatch) -> None:
    monkeypatch.setenv("ENTRANCE_CHEER_ENABLED", "1")

    class _NoMqtt(_Settings):
        mqtt_enabled = False

    assert build_entrance_cheer_watcher(lambda text: None, _NoMqtt()) is None


def test_not_built_without_robot_device_id(monkeypatch) -> None:
    monkeypatch.setenv("ENTRANCE_CHEER_ENABLED", "1")

    class _NoId(_Settings):
        robot_device_id = None

    assert build_entrance_cheer_watcher(lambda text: None, _NoId()) is None


def test_real_thread_factory_is_the_default() -> None:
    """운영 기본값은 진짜 데몬 스레드다 — paho 콜백을 막지 않기 위해서."""
    done = threading.Event()
    watcher = EntranceCheerWatcher(
        lambda text: done.set(), settings=_Settings())

    assert watcher.handle_payload(_command()) is True
    assert done.wait(5.0) is True


# ── 환호가 실제로 소리까지 가는지 ──────────────────────────────────────────────

def test_cheer_speaker_reaches_the_audio_output() -> None:
    """Runtime 에서 합성기와 재생기를 찾아 실제로 재생까지 간다.

    2026-08-10 실기에서 이 경로가 AttributeError('Runtime' object has no
    attribute 'tts') 로 죽어, 현관 환호가 한 번도 소리 난 적이 없었다.
    """
    from bomi_ai_chat import bootstrap

    class _Tts:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def synthesize(self, text: str) -> bytes:
            self.calls.append(text)
            return b"wav"

    class _AudioOut:
        def __init__(self) -> None:
            self.played: list[bytes] = []

        def play(self, audio: bytes) -> None:
            self.played.append(audio)

    tts = _Tts()
    audio_out = _AudioOut()
    runtime = bootstrap.Runtime(
        app=None, senior_id="senior", tts=tts, audio_out=audio_out)

    speak = bootstrap._build_cheer_speaker(runtime)
    speak("야호")
    speak("야호")

    assert audio_out.played == [b"wav", b"wav"]
    # 문구가 매번 같으므로 합성은 첫 번째만 네트워크를 탄다.
    assert tts.calls == ["야호"]


def test_cheer_speaker_stays_quiet_without_audio() -> None:
    """출력이 없는 실행(--once, 테스트)에서는 조용히 넘어간다."""
    from bomi_ai_chat import bootstrap

    speak = bootstrap._build_cheer_speaker(
        bootstrap.Runtime(app=None, senior_id="senior"))

    speak("야호")  # 예외가 나지 않으면 통과다.


# ── 여러 마디를 이어 말한다 ─────────────────────────────────────────────────

def test_phrases_are_spoken_in_order() -> None:
    watcher, spoken = _make(text="하나|둘|셋")

    watcher.handle_payload(_command())

    assert spoken == ["하나", "둘", "셋"]


def test_blank_phrases_are_dropped() -> None:
    """구분자를 잘못 넣어도 빈 문장을 합성하러 가지 않는다."""
    assert split_phrases("야호!||  |할머니!") == ["야호!", "할머니!"]


def test_a_single_phrase_still_works() -> None:
    """구분자가 없으면 예전처럼 한 마디다."""
    watcher, spoken = _make(text="다 왔어요")

    watcher.handle_payload(_command())

    assert spoken == ["다 왔어요"]


def test_the_time_limit_drops_the_remaining_phrases(monkeypatch) -> None:
    """도착해서 귀가 인사가 시작될 시점에 환호가 남아 있으면 소리가 겹친다."""
    monkeypatch.setenv("ENTRANCE_CHEER_MAX_SECONDS", "1.0")
    monkeypatch.setenv("ENTRANCE_CHEER_GAP_SEC", "0.6")
    watcher, spoken = _make(text="하나|둘|셋|넷")

    watcher.handle_payload(_command())

    # 0.6초 숨 두 번이면 1.2초라 셋째 마디 앞에서 상한에 걸린다.
    assert spoken == ["하나", "둘"]


def test_a_broken_time_limit_falls_back_to_the_default(monkeypatch) -> None:
    monkeypatch.setenv("ENTRANCE_CHEER_MAX_SECONDS", "곧")
    watcher, spoken = _make(text="하나|둘")

    watcher.handle_payload(_command())

    assert spoken == ["하나", "둘"]


def test_a_failing_speaker_stops_the_rest() -> None:
    """스피커가 죽었으면 남은 마디를 시도해 봐야 같은 예외만 쌓인다."""
    calls: list[str] = []

    def boom(text: str) -> None:
        calls.append(text)
        raise RuntimeError("speaker is gone")

    clock = _Clock()
    watcher = EntranceCheerWatcher(
        boom, settings=_Settings(), thread_factory=_ImmediateThread,
        text="하나|둘|셋", clock=clock, sleep=clock.sleep)

    assert watcher.handle_payload(_command()) is True
    assert calls == ["하나"]
