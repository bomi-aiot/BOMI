"""설치 패키지와 진입점 smoke test."""

import sys

import pytest

import bomi_ai_chat
from bomi_ai_chat import main
from bomi_ai_chat.config import Settings


def test_package_exposes_version():
    assert bomi_ai_chat.__version__ == "0.1.0"


def test_importing_entrypoint_does_not_load_heavy_router():
    assert "bomi_ai_chat.llm.router" not in sys.modules


def test_entrypoint_fails_before_runtime_import_when_settings_are_missing(
    monkeypatch,
):
    for variable in (
        "RTZR_CLIENT_ID",
        "RTZR_CLIENT_SECRET",
        "GEMINI_API_KEY",
        "TYPECAST_API_KEY",
    ):
        monkeypatch.delenv(variable, raising=False)
    settings = Settings.from_env(load_env_file=False)
    monkeypatch.setattr(main, "get_settings", lambda: settings)

    with pytest.raises(SystemExit, match="설정 오류:.*RTZR_CLIENT_ID"):
        main.main()

    assert "bomi_ai_chat.llm.router" not in sys.modules
