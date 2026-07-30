"""환경변수 설정 로딩과 검증 테스트."""

import pytest

from bomi_ai_chat.config import (
    DEFAULT_TYPECAST_VOICE_ID,
    ConfigurationError,
    Settings,
)


def load_settings() -> Settings:
    return Settings.from_env(load_env_file=False)


def test_defaults_are_explicit():
    settings = load_settings()

    assert settings.typecast_voice_id == DEFAULT_TYPECAST_VOICE_ID
    assert settings.db_connection_mode == "ssh"
    assert settings.db_host == "localhost"
    assert settings.db_port == 5432
    assert settings.ec2_ssh_user == "ec2-user"
    assert settings.remote_db_host == "localhost"
    assert settings.remote_db_port == 5432
    assert settings.http_timeout_seconds == 10.0
    assert settings.http_max_attempts == 3
    assert settings.http_backoff_seconds == 0.5
    assert settings.http_max_backoff_seconds == 2.0
    assert settings.stt_poll_interval_seconds == 0.5
    assert settings.stt_poll_timeout_seconds == 60.0
    assert settings.stt_token_ttl_seconds == 3000.0


def test_invalid_database_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("DB_CONNECTION_MODE", "unknown")

    with pytest.raises(ConfigurationError, match="DB_CONNECTION_MODE"):
        load_settings()


def test_invalid_integer_setting_is_rejected(monkeypatch):
    monkeypatch.setenv("DB_PORT", "not-a-number")

    with pytest.raises(ConfigurationError, match="DB_PORT"):
        load_settings()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("HTTP_TIMEOUT_SECONDS", "0"),
        ("HTTP_MAX_ATTEMPTS", "-1"),
        ("HTTP_BACKOFF_SECONDS", "-0.1"),
        ("HTTP_MAX_BACKOFF_SECONDS", "-0.1"),
        ("STT_POLL_INTERVAL_SECONDS", "not-a-number"),
        ("STT_POLL_TIMEOUT_SECONDS", "0"),
        ("STT_TOKEN_TTL_SECONDS", "-5"),
    ],
)
def test_invalid_external_client_setting_is_rejected(
    monkeypatch,
    name,
    value,
):
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError, match=name):
        load_settings()


def test_conversation_settings_report_all_missing_values():
    settings = load_settings()

    with pytest.raises(ConfigurationError) as error:
        settings.validate_conversation()

    message = str(error.value)
    assert "RTZR_CLIENT_ID" in message
    assert "RTZR_CLIENT_SECRET" in message
    assert "GEMINI_API_KEY" in message
    assert "TYPECAST_API_KEY" in message


def test_direct_database_accepts_database_url(monkeypatch):
    monkeypatch.setenv("DB_CONNECTION_MODE", "direct")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/example",
    )

    load_settings().validate_database()


def test_direct_database_requires_individual_credentials_without_url(
    monkeypatch,
):
    monkeypatch.setenv("DB_CONNECTION_MODE", "direct")

    with pytest.raises(ConfigurationError) as error:
        load_settings().validate_database()

    message = str(error.value)
    assert "DB_NAME" in message
    assert "DB_USER" in message
    assert "DB_PASSWORD" in message


def test_ssh_database_requires_tunnel_settings(monkeypatch):
    monkeypatch.setenv("DB_NAME", "bomi")
    monkeypatch.setenv("DB_USER", "bomi")
    monkeypatch.setenv("DB_PASSWORD", "secret")

    with pytest.raises(ConfigurationError) as error:
        load_settings().validate_database()

    message = str(error.value)
    assert "EC2_HOST" in message
    assert "SSH_KEY_PATH" in message


def test_ssh_database_accepts_complete_settings(monkeypatch):
    monkeypatch.setenv("DB_NAME", "bomi")
    monkeypatch.setenv("DB_USER", "bomi")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setenv("EC2_HOST", "example.internal")
    monkeypatch.setenv("SSH_KEY_PATH", "keys/example.pem")

    load_settings().validate_database()
