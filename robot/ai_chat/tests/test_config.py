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

    assert settings.audio_mode == "laptop"
    # 입력 장치의 기본값은 S15P11E102-214 에서 "reSpeaker" 로 바뀌었다. USB 인덱스가
    # 재부팅마다 달라져서 이름으로 잡도록 한 의도된 변경이다(config.py 주석 참고).
    # 출력은 여전히 기본값이 없다 — 스피커는 장치 지정이 필수다.
    assert settings.audio_input_device == "reSpeaker"
    assert settings.audio_output_device is None
    assert settings.audio_sample_rate == 16000
    # 채널 기본값도 214 에서 2 로 바뀌었다. ReSpeaker 는 마이크 배열이라 스테레오로
    # 잡아야 빔 제어가 동작한다.
    assert settings.audio_channels == 2
    assert settings.audio_chunk_seconds == 0.5
    assert settings.audio_silence_threshold == 300.0
    assert settings.audio_silence_limit_seconds == 3.0
    assert settings.audio_max_seconds == 15.0
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


def test_invalid_audio_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("AUDIO_MODE", "unknown")

    with pytest.raises(ConfigurationError, match="AUDIO_MODE"):
        load_settings()


def test_audio_device_accepts_index_or_name(monkeypatch):
    monkeypatch.setenv("AUDIO_INPUT_DEVICE", "0")
    monkeypatch.setenv("AUDIO_OUTPUT_DEVICE", "USB Audio")

    settings = load_settings()

    assert settings.audio_input_device == 0
    assert settings.audio_output_device == "USB Audio"


def test_robot_audio_requires_both_devices(monkeypatch):
    monkeypatch.setenv("AUDIO_MODE", "robot")
    monkeypatch.setenv("AUDIO_INPUT_DEVICE", "0")

    with pytest.raises(ConfigurationError) as error:
        load_settings().validate_audio()

    assert "AUDIO_OUTPUT_DEVICE" in str(error.value)


def test_robot_audio_accepts_zero_device_indexes(monkeypatch):
    monkeypatch.setenv("AUDIO_MODE", "robot")
    monkeypatch.setenv("AUDIO_INPUT_DEVICE", "0")
    monkeypatch.setenv("AUDIO_OUTPUT_DEVICE", "0")

    load_settings().validate_audio()


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


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AUDIO_INPUT_DEVICE", "-1"),
        ("AUDIO_OUTPUT_DEVICE", "-2"),
        ("AUDIO_SAMPLE_RATE", "0"),
        ("AUDIO_CHANNELS", "-1"),
        ("AUDIO_CHUNK_SECONDS", "0"),
        ("AUDIO_SILENCE_THRESHOLD", "-0.1"),
        ("AUDIO_SILENCE_LIMIT_SECONDS", "0"),
        ("AUDIO_MAX_SECONDS", "not-a-number"),
    ],
)
def test_invalid_audio_setting_is_rejected(monkeypatch, name, value):
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
