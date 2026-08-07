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
    # 214 가 입력 장치 기본값을 "reSpeaker" 로, 채널을 2 로 바꿨다. USB 인덱스가
    # 재부팅마다 달라져서 이름으로 잡도록 한 의도된 변경이었다.
    #
    # 233 에서 그 기본값을 **robot 모드로 한정**했다. 의도를 되돌린 것이 아니라
    # 적용 범위를 좁힌 것이다 — laptop 모드에서도 ReSpeaker 를 찾다가 실기 점검이
    # 첫 명령에서 막혔다. 노트북에 그 USB 마이크가 없는 것은 정상이고, laptop 모드의
    # 뜻이 "OS 기본 장치를 쓴다"인데 없는 장치를 요구하면 그 모드가 의미를 잃는다.
    # robot 모드의 동작은 그대로다(아래 test_robot_mode_still_finds_the_respeaker_by_name).
    assert settings.audio_input_device is None
    assert settings.audio_output_device is None
    assert settings.audio_sample_rate == 16000
    assert settings.audio_channels == 1
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

# ── 하드웨어 전용 기본값은 robot 모드에서만 (S15P11E102-233) ────────────────


def test_laptop_mode_uses_the_os_default_microphone(settings_factory):
    """★★ 실기 점검이 첫 명령에서 막혔던 지점이다.

        RuntimeError: 이름에 'reSpeaker'가 들어간 입력 장치를 찾을 수 없습니다

    laptop 모드의 뜻은 "OS 기본 장치를 쓴다"인데, 없는 USB 마이크를 요구하면 그
    모드가 의미를 잃는다. 노트북에 ReSpeaker 가 없는 것은 정상이다.
    """
    settings = settings_factory(AUDIO_MODE="laptop")

    assert settings.audio_input_device is None, (
        "laptop 모드에서 특정 USB 마이크 이름을 기본값으로 요구하면 안 된다")
    assert settings.audio_channels == 1


def test_robot_mode_still_finds_the_respeaker_by_name(settings_factory):
    """★ 로봇 위에서는 이름 검색이 옳다.

    USB 를 다시 꽂으면 PortAudio 인덱스가 바뀐다. 인덱스를 박아 두면 재부팅 한 번에
    마이크를 잃는다. 그 편의를 없애자는 것이 아니라, 맞는 자리에만 두자는 것이다.
    """
    settings = settings_factory(AUDIO_MODE="robot")

    assert settings.audio_input_device == "reSpeaker"
    assert settings.audio_channels == 2, (
        "ReSpeaker 는 2채널(왼쪽=처리된 빔)로 열어 왼쪽만 쓴다")


def test_an_explicit_device_always_wins(settings_factory):
    """어느 모드든 .env 가 이긴다. 기본값은 '아무것도 안 적었을 때'의 값이다."""
    assert settings_factory(AUDIO_MODE="laptop", AUDIO_INPUT_DEVICE="1").audio_input_device == 1
    assert settings_factory(
        AUDIO_MODE="robot", AUDIO_INPUT_DEVICE="7").audio_input_device == 7
    assert settings_factory(
        AUDIO_MODE="laptop", AUDIO_CHANNELS="2").audio_channels == 2
