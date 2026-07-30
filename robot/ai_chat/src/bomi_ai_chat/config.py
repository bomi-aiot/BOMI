"""환경변수 기반 애플리케이션 설정."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_TYPECAST_VOICE_ID = "tc_666a9871abcf27a5169850d0"
VALID_DB_CONNECTION_MODES = {"direct", "ssh"}
VALID_AUDIO_MODES = {"laptop", "robot"}


class ConfigurationError(RuntimeError):
    """필수 설정이 없거나 올바르지 않을 때 발생하는 오류."""


def _optional_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped or default


def _integer_env(name: str, default: int) -> int:
    raw_value = _optional_env(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(
            f"{name}은 정수여야 합니다: {raw_value!r}"
        ) from exc


def _positive_integer_env(name: str, default: int) -> int:
    value = _integer_env(name, default)
    if value <= 0:
        raise ConfigurationError(f"{name}은 0보다 큰 정수여야 합니다: {value!r}")
    return value


def _float_env(name: str, default: float) -> float:
    raw_value = _optional_env(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(
            f"{name}은 숫자여야 합니다: {raw_value!r}"
        ) from exc


def _positive_float_env(name: str, default: float) -> float:
    value = _float_env(name, default)
    if value <= 0:
        raise ConfigurationError(f"{name}은 0보다 큰 숫자여야 합니다: {value!r}")
    return value


def _non_negative_float_env(name: str, default: float) -> float:
    value = _float_env(name, default)
    if value < 0:
        raise ConfigurationError(f"{name}은 0 이상이어야 합니다: {value!r}")
    return value


def _audio_device_env(name: str) -> int | str | None:
    """PortAudio 장치 인덱스 또는 장치명 일부를 읽는다."""

    raw_value = _optional_env(name)
    if raw_value is None:
        return None
    try:
        device_index = int(raw_value)
    except ValueError:
        return raw_value
    if device_index < 0:
        raise ConfigurationError(
            f"{name} 장치 인덱스는 0 이상이어야 합니다: {device_index!r}"
        )
    return device_index


@dataclass(frozen=True)
class Settings:
    """ai_chat에서 사용하는 환경설정을 한 곳에 모은 값 객체."""

    rtzr_client_id: str | None
    rtzr_client_secret: str | None
    gemini_api_key: str | None
    typecast_api_key: str | None
    typecast_voice_id: str
    kma_api_key: str | None

    audio_mode: str
    audio_input_device: int | str | None
    audio_output_device: int | str | None
    audio_sample_rate: int
    audio_channels: int
    audio_chunk_seconds: float
    audio_silence_threshold: float
    audio_silence_limit_seconds: float
    audio_max_seconds: float

    http_timeout_seconds: float
    http_max_attempts: int
    http_backoff_seconds: float
    http_max_backoff_seconds: float
    stt_poll_interval_seconds: float
    stt_poll_timeout_seconds: float
    stt_token_ttl_seconds: float

    db_connection_mode: str
    database_url: str | None
    db_host: str
    db_port: int
    db_name: str | None
    db_user: str | None
    db_password: str | None

    ec2_host: str | None
    ec2_ssh_user: str
    ssh_key_path: str | None
    remote_db_host: str
    remote_db_port: int

    @classmethod
    def from_env(
        cls,
        *,
        load_env_file: bool = True,
    ) -> Settings:
        """현재 환경변수와 선택적으로 명시된 `.env` 파일을 읽는다."""

        if load_env_file:
            env_file = Path(os.getenv("AI_CHAT_ENV_FILE", ".env"))
            load_dotenv(dotenv_path=env_file, override=False)

        db_connection_mode = (
            _optional_env("DB_CONNECTION_MODE", "ssh") or "ssh"
        ).lower()
        if db_connection_mode not in VALID_DB_CONNECTION_MODES:
            allowed = ", ".join(sorted(VALID_DB_CONNECTION_MODES))
            raise ConfigurationError(
                "DB_CONNECTION_MODE는 "
                f"{allowed} 중 하나여야 합니다: {db_connection_mode!r}"
            )

        audio_mode = (_optional_env("AUDIO_MODE", "laptop") or "laptop").lower()
        if audio_mode not in VALID_AUDIO_MODES:
            allowed = ", ".join(sorted(VALID_AUDIO_MODES))
            raise ConfigurationError(
                f"AUDIO_MODE는 {allowed} 중 하나여야 합니다: {audio_mode!r}"
            )

        return cls(
            rtzr_client_id=_optional_env("RTZR_CLIENT_ID"),
            rtzr_client_secret=_optional_env("RTZR_CLIENT_SECRET"),
            gemini_api_key=_optional_env("GEMINI_API_KEY"),
            typecast_api_key=_optional_env("TYPECAST_API_KEY"),
            typecast_voice_id=(
                _optional_env(
                    "TYPECAST_VOICE_ID",
                    DEFAULT_TYPECAST_VOICE_ID,
                )
                or DEFAULT_TYPECAST_VOICE_ID
            ),
            kma_api_key=_optional_env("KMA_API_KEY"),
            audio_mode=audio_mode,
            audio_input_device=_audio_device_env("AUDIO_INPUT_DEVICE"),
            audio_output_device=_audio_device_env("AUDIO_OUTPUT_DEVICE"),
            audio_sample_rate=_positive_integer_env(
                "AUDIO_SAMPLE_RATE",
                16000,
            ),
            audio_channels=_positive_integer_env("AUDIO_CHANNELS", 1),
            audio_chunk_seconds=_positive_float_env(
                "AUDIO_CHUNK_SECONDS",
                0.5,
            ),
            audio_silence_threshold=_non_negative_float_env(
                "AUDIO_SILENCE_THRESHOLD",
                300.0,
            ),
            audio_silence_limit_seconds=_positive_float_env(
                "AUDIO_SILENCE_LIMIT_SECONDS",
                3.0,
            ),
            audio_max_seconds=_positive_float_env(
                "AUDIO_MAX_SECONDS",
                15.0,
            ),
            http_timeout_seconds=_positive_float_env(
                "HTTP_TIMEOUT_SECONDS",
                10.0,
            ),
            http_max_attempts=_positive_integer_env(
                "HTTP_MAX_ATTEMPTS",
                3,
            ),
            http_backoff_seconds=_non_negative_float_env(
                "HTTP_BACKOFF_SECONDS",
                0.5,
            ),
            http_max_backoff_seconds=_non_negative_float_env(
                "HTTP_MAX_BACKOFF_SECONDS",
                2.0,
            ),
            stt_poll_interval_seconds=_positive_float_env(
                "STT_POLL_INTERVAL_SECONDS",
                0.5,
            ),
            stt_poll_timeout_seconds=_positive_float_env(
                "STT_POLL_TIMEOUT_SECONDS",
                60.0,
            ),
            stt_token_ttl_seconds=_positive_float_env(
                "STT_TOKEN_TTL_SECONDS",
                3000.0,
            ),
            db_connection_mode=db_connection_mode,
            database_url=_optional_env("DATABASE_URL"),
            db_host=_optional_env("DB_HOST", "localhost") or "localhost",
            db_port=_integer_env("DB_PORT", 5432),
            db_name=_optional_env("DB_NAME"),
            db_user=_optional_env("DB_USER"),
            db_password=_optional_env("DB_PASSWORD"),
            ec2_host=_optional_env("EC2_HOST"),
            ec2_ssh_user=(
                _optional_env("EC2_SSH_USER", "ec2-user") or "ec2-user"
            ),
            ssh_key_path=_optional_env("SSH_KEY_PATH"),
            remote_db_host=(
                _optional_env("REMOTE_DB_HOST", "localhost") or "localhost"
            ),
            remote_db_port=_integer_env("REMOTE_DB_PORT", 5432),
        )

    def validate_conversation(self) -> None:
        """기본 음성 대화 실행에 필요한 설정을 검증한다."""

        self._require(
            {
                "RTZR_CLIENT_ID": self.rtzr_client_id,
                "RTZR_CLIENT_SECRET": self.rtzr_client_secret,
                "GEMINI_API_KEY": self.gemini_api_key,
                "TYPECAST_API_KEY": self.typecast_api_key,
            },
            feature="기본 음성 대화",
        )
        self.validate_audio()

    def validate_audio(self) -> None:
        """선택한 오디오 모드의 장치 설정을 검증한다."""

        if self.audio_mode == "robot":
            self.validate_robot_audio()

    def validate_robot_audio(self) -> None:
        """로봇 어댑터에 필요한 입력·출력 장치를 검증한다."""

        self._require(
            {
                "AUDIO_INPUT_DEVICE": self.audio_input_device,
                "AUDIO_OUTPUT_DEVICE": self.audio_output_device,
            },
            feature="로봇 오디오",
        )

    def validate_weather(self) -> None:
        """날씨 조회에 필요한 설정을 검증한다."""

        self._require(
            {"KMA_API_KEY": self.kma_api_key},
            feature="날씨 조회",
        )

    def validate_database(self) -> None:
        """선택한 방식으로 의료 DB에 연결할 수 있는지 검증한다."""

        if self.db_connection_mode == "direct" and self.database_url:
            return

        self._require(
            {
                "DB_NAME": self.db_name,
                "DB_USER": self.db_user,
                "DB_PASSWORD": self.db_password,
            },
            feature="의료 DB 연결",
        )
        if self.db_connection_mode == "ssh":
            self.validate_ssh_database()

    def validate_ssh_database(self) -> None:
        """SSH 터널 연결에 필요한 설정을 검증한다."""

        self._require(
            {
                "EC2_HOST": self.ec2_host,
                "SSH_KEY_PATH": self.ssh_key_path,
            },
            feature="SSH 의료 DB 연결",
        )

    @staticmethod
    def _require(
        values: dict[str, object | None],
        *,
        feature: str,
    ) -> None:
        missing = [
            name
            for name, value in values.items()
            if value is None or (isinstance(value, str) and not value)
        ]
        if missing:
            joined = ", ".join(missing)
            raise ConfigurationError(
                f"{feature}에 필요한 환경변수가 없습니다: {joined}"
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """프로세스에서 재사용할 설정 인스턴스를 반환한다."""

    return Settings.from_env()


def clear_settings_cache() -> None:
    """테스트 또는 환경 재로딩을 위해 설정 캐시를 비운다."""

    get_settings.cache_clear()
