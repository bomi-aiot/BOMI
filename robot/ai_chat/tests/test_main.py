"""CLI의 단발·반복 실행 모드 회귀 테스트.

기존 네 건은 **옛 파이프라인 경로**를 검증한다. S15P11E102-232 부터 기본값이 그래프
경로가 되었으므로 `--legacy` 를 명시한다 — 되돌리기 경로가 살아 있다는 것 자체가
검증할 가치가 있다. 실기에서 새 경로에 문제가 나면 이것으로 되돌린다.

그래프 경로는 아래 별도 절에서 본다.
"""

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

    exit_code = main.main(["--once", "--legacy"])

    assert exit_code == 0
    assert [call[0] for call in calls] == ["init", "run_once"]


def test_once_option_returns_failure_exit_code(
    monkeypatch,
    settings_factory,
):
    settings = valid_settings(settings_factory)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    calls = install_runtime_stubs(monkeypatch, once_succeeded=False)

    exit_code = main.main(["--once", "--legacy"])

    assert exit_code == 1
    assert [call[0] for call in calls] == ["init", "run_once"]


def test_default_mode_runs_conversation_loop(
    monkeypatch,
    settings_factory,
):
    settings = valid_settings(settings_factory)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    calls = install_runtime_stubs(monkeypatch)

    exit_code = main.main(["--legacy"])

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

    exit_code = main.main(["--once", "--legacy"])

    assert exit_code == 0
    assert type(calls[0][1]).__name__ == "RobotAudioInput"
    assert type(calls[0][2]).__name__ == "RobotAudioOutput"


# ── 그래프 경로 (S15P11E102-232) ─────────────────────────────────────────────


def graph_settings(settings_factory, **extra):
    return settings_factory(
        RTZR_CLIENT_ID="id",
        RTZR_CLIENT_SECRET="secret",
        GEMINI_API_KEY="gemini",
        TYPECAST_API_KEY="typecast",
        SENIOR_ID="senior-1",
        **extra,
    )


def test_the_graph_path_is_the_default(monkeypatch, settings_factory):
    """★ 기본값이 옛 경로면 배선한 의미가 없다.

    200~211 의 게이트·침묵 사다리·트리아지·현관은 전부 그래프 경로에만 있다.
    """
    settings = graph_settings(settings_factory)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    install_runtime_stubs(monkeypatch)
    seen = {}

    def fake_run(settings_arg, audio_in, audio_out, *, once):
        seen["once"] = once
        return 0

    monkeypatch.setattr(main, "_run_graph_runtime", fake_run)

    assert main.main([]) == 0
    assert seen == {"once": False}


def test_legacy_flag_falls_back_to_the_old_pipeline(monkeypatch, settings_factory):
    """★ 되돌리기가 코드 수정이면 현장에서 못 한다."""
    settings = graph_settings(settings_factory)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    calls = install_runtime_stubs(monkeypatch)

    assert main.main(["--legacy"]) == 0
    assert [call[0] for call in calls] == ["init", "run"]


def test_the_env_switch_also_falls_back(monkeypatch, settings_factory):
    """플래그 없이 .env 만으로도 되돌릴 수 있어야 한다. 실기에서 인자를 못 바꾸는
    실행 방식(systemd, docker)이 있다."""
    settings = graph_settings(settings_factory, USE_GRAPH_RUNTIME="false")
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    calls = install_runtime_stubs(monkeypatch)

    assert main.main([]) == 0
    assert [call[0] for call in calls] == ["init", "run"]


def test_once_does_not_start_background_work(monkeypatch, settings_factory):
    """★ 한 턴만 보려는 실행에 스케줄러가 뜨면, 정리되기 전에 틱이 돌아 제안이
    큐에 남는다. 다음 실행이 그것을 물려받아 "왜 갑자기 말하지?"가 된다."""
    settings = graph_settings(settings_factory)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    install_runtime_stubs(monkeypatch)
    seen = {}

    def fake_run(settings_arg, audio_in, audio_out, *, once):
        seen["once"] = once
        return 0

    monkeypatch.setattr(main, "_run_graph_runtime", fake_run)

    main.main(["--once"])

    assert seen["once"] is True

# ── 로깅 (S15P11E102-233) ───────────────────────────────────────────────────


def test_logging_is_actually_configured(monkeypatch, tmp_path, settings_factory):
    """★★ basicConfig 가 주석 처리되어 있었다. 그래서 로그가 통째로 사라졌다.

    핸들러가 하나도 없으면 INFO 는 버려지고 WARNING 만 형식 없이 stderr 로 나간다.
    사라졌던 것들: "turn latency 1.83s", "scheduler built", "occupancy UNKNOWN ->
    HOME", "degrading to level 1". 실기 점검에서 봐야 할 것이 정확히 그것들이다.

    주석 한 줄로 다시 사라질 수 있는 종류의 실패라서 테스트로 고정한다.
    """
    import logging

    from bomi_ai_chat import main as main_module

    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    root = logging.getLogger()
    original = list(root.handlers)
    for handler in original:
        root.removeHandler(handler)

    try:
        main_module._setup_logging(
            settings_factory(RTZR_CLIENT_ID="i", RTZR_CLIENT_SECRET="s",
                             GEMINI_API_KEY="g", TYPECAST_API_KEY="t"),
            verbose=False)

        assert root.handlers, "핸들러가 없으면 INFO 로그가 통째로 사라진다"
        assert root.level <= logging.INFO

        # 파일에도 남아야 한다. 스크롤로 흘러간 화면은 다음 날 없고,
        # 실기 점검의 산출물은 기록이다.
        log_file = tmp_path / "localstore" / "logs" / "ai_chat.log"
        logging.getLogger("bomi_ai_chat.test").info("field-test marker")
        for handler in root.handlers:
            handler.flush()
        assert log_file.exists(), f"{log_file} 이 없다"
        assert "field-test marker" in log_file.read_text(encoding="utf-8")
    finally:
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)
        for handler in original:
            root.addHandler(handler)


def test_verbose_lowers_the_console_level_only(monkeypatch, tmp_path, settings_factory):
    """-v 는 화면만 바꾼다. 파일은 -v 없이도 항상 DEBUG 다.

    되돌릴 수 없는 것은 '남기지 않은 로그'다. 문제가 생긴 뒤에 -v 를 켜고 재현하는
    것은, 재현되지 않는 문제 앞에서 아무 의미가 없다.
    """
    import logging

    from bomi_ai_chat import main as main_module

    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    root = logging.getLogger()
    original = list(root.handlers)
    for handler in original:
        root.removeHandler(handler)

    try:
        main_module._setup_logging(
            settings_factory(RTZR_CLIENT_ID="i", RTZR_CLIENT_SECRET="s",
                             GEMINI_API_KEY="g", TYPECAST_API_KEY="t"),
            verbose=False)

        console = [h for h in root.handlers if not hasattr(h, "baseFilename")]
        files = [h for h in root.handlers if hasattr(h, "baseFilename")]

        assert console and console[0].level == logging.INFO
        assert files and files[0].level == logging.DEBUG
    finally:
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)
        for handler in original:
            root.addHandler(handler)
