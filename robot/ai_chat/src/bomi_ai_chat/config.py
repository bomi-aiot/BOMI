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


def _bool_env(name: str, default: bool) -> bool:
    """"1/true/yes/on" 을 참으로 읽는다. 그 외 값은 오류로 알린다.

    조용히 False 로 떨어뜨리지 않는 이유
        MQTT_ENABLED=True 를 MQTT_ENABLED=Ture 로 적으면 현관 구독이 뜨지 않는다.
        그리고 아무 로그도 남지 않는다. 안전 신호가 하나 사라진 것을 오타 때문에
        아무도 모르는 상태가 된다.
    """
    raw_value = _optional_env(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(
        f"{name}은 true 또는 false 여야 합니다: {raw_value!r}"
    )


def _audio_device_env(
    name: str, default: int | str | None = None
) -> int | str | None:
    """PortAudio 장치 인덱스 또는 장치명 일부를 읽는다. 미설정 시 default 반환."""

    raw_value = _optional_env(name)
    if raw_value is None:
        return default
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

    # 로봇 로컬 운영 상태가 사는 디렉터리. 배포마다 바뀌므로 policy.py 가 아니라 여기다.
    #
    # 왜 디렉터리 하나인가
    #   런타임 DB, 발신 큐 DB, 캐시 오디오가 모두 이 아래에 모인다. 일일 덤프가
    #   디렉터리 하나만 복사하면 되고, SD카드를 교체할 때 옮길 대상이 명확해진다.
    localstore_dir: str

    # 백엔드(문맥 조립 API)의 주소와 타임아웃. 배포마다 바뀌므로 policy 가 아니라 여기다.
    #
    # 타임아웃을 짧게 두는 이유
    #   이 호출은 턴 지연 예산(약 2초) '안에' 있다. 오래 기다리느니 캐시로 내려가서
    #   얕게라도 대답하는 편이 낫다. 기다리다 놓친 턴은 어르신 입장에서 그냥
    #   대답하지 않은 로봇이다.
    backend_base_url: str
    backend_timeout_seconds: float

    # 이 로봇의 id. 배포된 기기마다 다르므로 policy 가 아니라 여기다.
    #
    # 왜 필요한가
    #   로봇에서 온보딩 세션을 '새로' 시작할 때 서버가 요구한다. 앱에서 시작한 세션을
    #   이어받을 때는 필요 없다. 미설정이면 로봇이 온보딩을 시작하지 못하고, 그 사실을
    #   로그로 남긴다(조용히 안 하지 않는다).
    robot_id: str | None

    # ── MQTT: 현관 이벤트 구독  (CLAUDE.md §11, docs/mqtt/topic-convention.md) ──
    #
    # 왜 URL 한 개로 받는가
    #   브로커는 EC2(bomi-mosquitto)에도 있고 Jetson 로컬에도 있을 수 있다. 어느 쪽에
    #   붙든 코드가 같아야 하므로 주소를 설정으로 받는다. scheme 이 TLS 여부를 정한다.
    #     mqtt://host:1883   평문 (Jetson 로컬, 개발)
    #     mqtts://host:8883  TLS  (서버)
    #
    # 왜 기본값이 '비활성'인가
    #   브로커가 없는 개발 노트북에서 로봇을 띄우면 구독 스레드가 무한 재연결을 시도하고
    #   로그를 덮는다. 그리고 실기에서는 반드시 켜야 하는 값이므로, 명시적으로 켜는 것이
    #   배포 체크리스트에 남는 편이 낫다.
    mqtt_enabled: bool
    mqtt_broker_url: str
    # 구독 토픽. 규약은 bomi/v1/{domain}/{deviceId}/{channel} 이고, 센서가 여러 개이므로
    # deviceId 자리에 와일드카드를 둔다. 두 센서(SNZB-03P/04P)가 각자 다른 deviceId 로
    # 발행하기 때문이다.
    mqtt_door_topic: str
    mqtt_client_id: str
    mqtt_username: str | None
    mqtt_password: str | None

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
            # 이 프로젝트는 ReSpeaker XVF3800을 마이크로 쓴다. 미설정 시 이름으로
            # 자동 검색되도록 기본값을 "reSpeaker"로 둔다(USB 재연결로 인덱스가
            # 바뀌어도 자동 대응). 다른 마이크를 쓰려면 .env에서 AUDIO_INPUT_DEVICE를
            # 지정하면 이 기본값을 덮어쓴다.
            # 원래 기본값: audio_input_device=_audio_device_env("AUDIO_INPUT_DEVICE"),
            audio_input_device=_audio_device_env("AUDIO_INPUT_DEVICE", "reSpeaker"),
            audio_output_device=_audio_device_env("AUDIO_OUTPUT_DEVICE"),
            audio_sample_rate=_positive_integer_env(
                "AUDIO_SAMPLE_RATE",
                16000,
            ),
            # ReSpeaker는 2채널(왼쪽=처리된 빔, 오른쪽=원본 mic0)로 열어 왼쪽만
            # 사용하므로 기본값을 2로 둔다.
            # 원래 기본값: audio_channels=_positive_integer_env("AUDIO_CHANNELS", 1),
            audio_channels=_positive_integer_env("AUDIO_CHANNELS", 2),
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
            localstore_dir=(
                _optional_env("LOCALSTORE_DIR", "var/localstore") or "var/localstore"
            ),
            backend_base_url=(
                _optional_env("BACKEND_BASE_URL", "http://localhost:8080")
                or "http://localhost:8080"
            ),
            backend_timeout_seconds=_positive_float_env("BACKEND_TIMEOUT_SECONDS", 1.5),
            robot_id=_optional_env("ROBOT_ID"),
            mqtt_enabled=_bool_env("MQTT_ENABLED", False),
            mqtt_broker_url=_optional_env("MQTT_BROKER_URL", "") or "",
            mqtt_door_topic=(
                _optional_env("MQTT_DOOR_TOPIC", "bomi/v1/iot/+/events")
                or "bomi/v1/iot/+/events"
            ),
            mqtt_client_id=(
                _optional_env("MQTT_CLIENT_ID", "bomi-robot-ai-chat")
                or "bomi-robot-ai-chat"
            ),
            mqtt_username=_optional_env("MQTT_USERNAME"),
            mqtt_password=_optional_env("MQTT_PASSWORD"),
        )

    def validate_mqtt(self) -> None:
        """현관 구독에 필요한 설정을 검증한다.

        누가 호출하는가
            door.mqtt.build_door_subscriber. 활성화됐을 때만.

        왜 활성화됐을 때만 검사하는가
            비활성 상태에서 브로커 주소를 요구하면, MQTT 를 쓰지 않는 테스트와
            개발 실행이 전부 설정 오류로 죽는다.
        """
        self._require({"MQTT_BROKER_URL": self.mqtt_broker_url}, feature="현관 MQTT 구독")

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
