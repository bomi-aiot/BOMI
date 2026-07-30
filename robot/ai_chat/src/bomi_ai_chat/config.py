"""환경변수 기반 애플리케이션 설정."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_TYPECAST_VOICE_ID = "tc_666a9871abcf27a5169850d0"
VALID_DB_CONNECTION_MODES = {"direct", "ssh"}


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


@dataclass(frozen=True)
class Settings:
    """ai_chat에서 사용하는 환경설정을 한 곳에 모은 값 객체."""

    rtzr_client_id: str | None
    rtzr_client_secret: str | None
    gemini_api_key: str | None
    typecast_api_key: str | None
    typecast_voice_id: str
    kma_api_key: str | None
    hira_hospital_api_key: str | None
    hira_pharmacy_api_key: str | None
    dur_prdlst_api_key: str | None

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
            hira_hospital_api_key=_optional_env("HIRA_HOSPITAL_API_KEY"),
            hira_pharmacy_api_key=_optional_env("HIRA_PHARMACY_API_KEY"),
            dur_prdlst_api_key=_optional_env("DUR_PRDLST_API_KEY"),
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
        values: dict[str, str | None],
        *,
        feature: str,
    ) -> None:
        missing = [name for name, value in values.items() if not value]
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
