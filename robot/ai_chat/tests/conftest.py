"""외부 환경과 격리된 pytest 공통 fixture."""

from collections.abc import Callable

import pytest
import requests

from bomi_ai_chat.config import Settings, clear_settings_cache

SETTING_VARIABLES = (
    "AI_CHAT_ENV_FILE",
    "RTZR_CLIENT_ID",
    "RTZR_CLIENT_SECRET",
    "GEMINI_API_KEY",
    "TYPECAST_API_KEY",
    "TYPECAST_VOICE_ID",
    "KMA_API_KEY",
    "HIRA_HOSPITAL_API_KEY",
    "HIRA_PHARMACY_API_KEY",
    "DUR_PRDLST_API_KEY",
    "HTTP_TIMEOUT_SECONDS",
    "HTTP_MAX_ATTEMPTS",
    "HTTP_BACKOFF_SECONDS",
    "HTTP_MAX_BACKOFF_SECONDS",
    "STT_POLL_INTERVAL_SECONDS",
    "STT_POLL_TIMEOUT_SECONDS",
    "STT_TOKEN_TTL_SECONDS",
    "DB_CONNECTION_MODE",
    "DATABASE_URL",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "EC2_HOST",
    "EC2_SSH_USER",
    "SSH_KEY_PATH",
    "REMOTE_DB_HOST",
    "REMOTE_DB_PORT",
)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    """로컬 .env와 프로세스 설정 캐시가 테스트에 스며들지 않게 한다."""

    for variable in SETTING_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("AI_CHAT_ENV_FILE", str(tmp_path / "missing.env"))
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture(autouse=True)
def block_external_http(monkeypatch, request):
    """기본 테스트에서 실수로 실제 HTTP 요청을 보내면 즉시 실패시킨다."""

    if request.node.get_closest_marker("integration") or request.node.get_closest_marker(
        "manual"
    ):
        return

    def fail_request(*args, **kwargs):
        raise AssertionError(
            "기본 테스트에서는 외부 HTTP 요청을 사용할 수 없습니다. "
            "응답을 mock하거나 integration/manual 테스트로 분리하세요."
        )

    monkeypatch.setattr(requests.sessions.Session, "request", fail_request)


@pytest.fixture
def settings_factory(monkeypatch) -> Callable[..., Settings]:
    """필요한 환경변수만 주입한 Settings를 만드는 공통 factory."""

    def build(**values: str) -> Settings:
        for name, value in values.items():
            monkeypatch.setenv(name, value)
        return Settings.from_env(load_env_file=False)

    return build
