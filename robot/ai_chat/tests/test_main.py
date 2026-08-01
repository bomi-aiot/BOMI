"""CLI의 단발·반복 실행 모드 회귀 테스트."""

import sys
from types import ModuleType, SimpleNamespace

from bomi_ai_chat import main


def install_runtime_stubs(monkeypatch, *, once_succeeded=True):
    laptop_module = ModuleType("bomi_ai_chat.audio_io.laptop")
    robot_module = ModuleType("bomi_ai_chat.audio_io.robot")

    class LaptopMicInput:
        def __init__(self, settings):
            self.settings = settings

    class LaptopSpeakerOutput:
        def __init__(self, settings):
            self.settings = settings

    class RobotAudioInput:
        def __init__(self, settings):
            self.settings = settings

    class RobotAudioOutput:
        def __init__(self, settings):
            self.settings = settings

    laptop_module.LaptopMicInput = LaptopMicInput
    laptop_module.LaptopSpeakerOutput = LaptopSpeakerOutput
    robot_module.RobotAudioInput = RobotAudioInput
    robot_module.RobotAudioOutput = RobotAudioOutput

    calls = []

    class StubPipeline:
        def __init__(self, *, audio_in, audio_out, settings):
            calls.append(("init", audio_in, audio_out, settings))

        def run_once(self):
            calls.append(("run_once",))
            return SimpleNamespace(succeeded=once_succeeded)

        def run(self):
            calls.append(("run",))

    pipeline_module = ModuleType("bomi_ai_chat.pipeline")
    pipeline_module.ConversationPipeline = StubPipeline

    # main의 warm-up이 실제 임베딩 모델(ko-sroberta)을 내려받지 않도록
    # 의도 판정 라우터도 가벼운 스텁으로 대체한다.
    router_module = ModuleType("bomi_ai_chat.llm.router")
    router_module.is_weather_query = lambda text: False
    router_module.is_medical_query = lambda text: False
    monkeypatch.setitem(
        sys.modules,
        "bomi_ai_chat.llm.router",
        router_module,
    )

    monkeypatch.setitem(
        sys.modules,
        "bomi_ai_chat.audio_io.laptop",
        laptop_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "bomi_ai_chat.audio_io.robot",
        robot_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "bomi_ai_chat.pipeline",
        pipeline_module,
    )
    return calls


def valid_settings(settings_factory):
    return settings_factory(
        RTZR_CLIENT_ID="id",
        RTZR_CLIENT_SECRET="secret",
        GEMINI_API_KEY="gemini",
        TYPECAST_API_KEY="typecast",
    )


def test_once_option_runs_one_turn(
    monkeypatch,
    settings_factory,
):
    settings = valid_settings(settings_factory)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    calls = install_runtime_stubs(monkeypatch)

    exit_code = main.main(["--once"])

    assert exit_code == 0
    assert [call[0] for call in calls] == ["init", "run_once"]


def test_once_option_returns_failure_exit_code(
    monkeypatch,
    settings_factory,
):
    settings = valid_settings(settings_factory)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    calls = install_runtime_stubs(monkeypatch, once_succeeded=False)

    exit_code = main.main(["--once"])

    assert exit_code == 1
    assert [call[0] for call in calls] == ["init", "run_once"]


def test_default_mode_runs_conversation_loop(
    monkeypatch,
    settings_factory,
):
    settings = valid_settings(settings_factory)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    calls = install_runtime_stubs(monkeypatch)

    exit_code = main.main([])

    assert exit_code == 0
    assert [call[0] for call in calls] == ["init", "run"]
    assert type(calls[0][1]).__name__ == "LaptopMicInput"
    assert type(calls[0][2]).__name__ == "LaptopSpeakerOutput"


def test_robot_mode_selects_robot_audio_adapters(
    monkeypatch,
    settings_factory,
):
    settings = settings_factory(
        RTZR_CLIENT_ID="id",
        RTZR_CLIENT_SECRET="secret",
        GEMINI_API_KEY="gemini",
        TYPECAST_API_KEY="typecast",
        AUDIO_MODE="robot",
        AUDIO_INPUT_DEVICE="USB Mic",
        AUDIO_OUTPUT_DEVICE="USB Speaker",
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    calls = install_runtime_stubs(monkeypatch)

    exit_code = main.main(["--once"])

    assert exit_code == 0
    assert type(calls[0][1]).__name__ == "RobotAudioInput"
    assert type(calls[0][2]).__name__ == "RobotAudioOutput"
