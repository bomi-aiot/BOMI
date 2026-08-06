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

    # 웨이크워드('보미야') 감지 설정.
    #   enabled  = 상시 청취로 로봇을 깨울지. 노트북 개발/테스트에서는 꺼서(0) 매 턴
    #              바로 대화하도록 할 수 있다. 로봇 배포에서는 켠다.
    #   model_path = 학습한 .onnx 경로. 배포 위치마다 달라질 수 있어 여기(config)에 둔다.
    # 감지 임계값·창 크기 등 '튜닝값'은 policy.py 에 있다(값의 수명이 다르다).
    wakeword_enabled: bool
    wakeword_model_path: str

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

    # 백엔드 서블릿 필터가 요구하는 공유 시크릿 (S15P11E102-307).
    #
    # 왜 선택값(optional)인가
    #   백엔드에서 이 값을 설정하지 않으면 필터가 헤더 검사를 건너뛰고 그대로
    #   통과시킨다 — 그래야 시크릿을 아직 안 돌린 로컬 개발이 계속 돌아간다. 로봇
    #   쪽도 같은 이유로 미설정을 허용한다. 다만 실기에서 백엔드에는 시크릿이 걸려
    #   있는데 로봇에 이 값이 비어 있으면, 헤더 없는 요청이 나가 401 을 맞는다 —
    #   그 401 은 조용한 캐시 폴백에 묻히지 않고 backend_client/session.py 를 거쳐
    #   경고 로그로 남는다.
    backend_shared_secret: str | None

    # 이 로봇의 id (robot 테이블의 UUID). 배포된 기기마다 다르므로 policy 가 아니라 여기다.
    #
    # 왜 필요한가
    #   로봇에서 온보딩 세션을 '새로' 시작할 때 서버가 요구한다. 앱에서 시작한 세션을
    #   이어받을 때는 필요 없다. 미설정이면 로봇이 온보딩을 시작하지 못하고, 그 사실을
    #   로그로 남긴다(조용히 안 하지 않는다).
    #
    # ★ MQTT 토픽에는 이 값을 쓰지 않는다 — 그쪽은 robot_device_id 다. 두 값은 서로
    #   다른 id 공간이고, 혼용은 실제로 있었던 사고다: MQTT 봉투에 UUID 를 넣으면
    #   백엔드가 UNKNOWN_ROBOT 으로 '조용히' 차단해 시나리오가 한 번도 돌지 않는다.
    robot_id: str | None

    # 이 로봇의 MQTT deviceId (robot 테이블의 device_id, 예: bomi-AA001).
    #
    # 왜 robot_id 와 분리하는가
    #   백엔드 MQTT 계약의 {robotId} 는 UUID 가 아니라 deviceId 다
    #   (ScenarioRobotStartPolicy 가 findLockCandidateByDeviceId 로 조회). 하나의
    #   환경변수를 REST(UUID)와 MQTT(deviceId) 양쪽에 쓰던 것이 식별자 충돌의
    #   원인이었다. 토픽·봉투를 만드는 모든 코드는 이 값을 쓴다.
    robot_device_id: str | None

    # 이 로봇이 돌보는 어르신.
    #
    # ★ checkpointer 의 thread_id 이자 모든 로컬 저장소의 키다. 틀리면 두 어르신이
    #   침묵 사다리를 공유하게 되고, 안전 시스템에서 그것은 한 사람의 발화가 다른
    #   사람의 에스컬레이션을 억제한다는 뜻이다 (graph/build.py).
    #
    # 기본값을 두지 않는다. 임의의 값으로 기동하면 그 값으로 상태가 쌓이고, 나중에
    # 진짜 id 로 바꾸는 순간 그동안의 사다리와 재실 기록이 통째로 사라진다.
    senior_id: str | None

    # 그래프 경로로 띄울 것인가.
    #
    # 왜 스위치가 있는가
    #   200~211 의 대화 런타임은 실기에서 한 번도 돌아본 적이 없다(S15P11E102-233).
    #   실기에서 문제가 나면 즉시 옛 경로로 되돌릴 수 있어야 하고, 그 되돌리기가
    #   코드 수정이면 현장에서 못 한다.
    #
    #   기본값이 true 인 이유: 배선이 끝난 뒤에도 false 로 두면 아무도 새 경로를
    #   쓰지 않고, 그러면 배선한 의미가 없다.
    use_graph_runtime: bool

    # T3 동의 질문 기능의 운영 킬스위치 (S15P11E102-253).
    #
    # policy.T3_CONSENT_ENABLED 와 무엇이 다른가
    #   policy 쪽은 '제품 판단'(코드 상수)이고, 이 값은 '오늘 당장 끄고 싶다'는
    #   운영 판단이다. 실기에서 이 질문이 이상하게 나간다는 신고가 들어왔을 때,
    #   코드를 고치고 재배포할 시간이 없어도 이 환경변수 하나로 그날 안에
    #   끌 수 있어야 한다(CLAUDE.md §26 의 "재현 가능한 방식으로 끌 수 있어야
    #   한다"는 원칙과 같다). jobs/ticks.consent_tick 이 이 값과 policy 값을
    #   모두 확인하고, 둘 중 하나라도 꺼지면 질문을 올리지 않는다.
    #
    # 기본값이 True 인 이유
    #   꺼진 채로 배포되면 정서 발화가 아무리 쌓여도 보호자에게 절대 닿지 않고,
    #   그 사실이 로그 한 줄 없이 조용하다. 명시적으로 끄는 것이 배포 체크리스트에
    #   남는 편이 안전하다.
    t3_consent_enabled: bool

    # 사실 추출 기능의 운영 킬스위치 (S15P11E102-255).
    #
    # policy.EXTRACTION_ENABLED 와 무엇이 다른가
    #   t3_consent_enabled 와 같은 구도다. policy 쪽은 '제품 판단'(코드 상수)이고,
    #   이 값은 '오늘 당장 끄고 싶다'는 운영 판단이다. LLM 비용이 튀거나 잘못된
    #   사실 후보가 쏟아진다는 신고가 들어왔을 때, 코드를 고치고 재배포할 시간이
    #   없어도 이 환경변수 하나로 그날 안에 끌 수 있어야 한다. graph/build.py 의
    #   큐잉과 jobs/ticks.extraction_flush 둘 다 이 값과 policy 값을 모두 확인하고,
    #   둘 중 하나라도 꺼지면 아무것도 하지 않는다.
    extraction_enabled: bool

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
            # 하드웨어 전용 기본값은 robot 모드에서만 적용한다 (S15P11E102-233).
            #
            # ★ 이 프로젝트는 ReSpeaker XVF3800 을 마이크로 쓰고, USB 재연결로 인덱스가
            #   바뀌어도 따라가도록 이름으로 자동 검색한다. 그 편의가 맞는 것은 로봇
            #   위에서뿐이다.
            #
            # 왜 모드별로 갈랐나
            #   laptop 모드에서도 "reSpeaker" 를 찾다가 실기 점검이 첫 명령에서 막혔다.
            #       RuntimeError: 이름에 'reSpeaker'가 들어간 입력 장치를 찾을 수 없습니다
            #   노트북에는 그 마이크가 없는 것이 정상이다. laptop 모드의 뜻이 "OS 기본
            #   장치를 쓴다"인데, 없는 USB 장치를 요구하면 그 모드가 의미를 잃는다.
            #   .env 로 덮어쓸 수는 있었지만, 기본값이 틀린 것을 사용자가 매번 고치는
            #   것은 설정이 아니라 우회다.
            audio_input_device=_audio_device_env(
                "AUDIO_INPUT_DEVICE", "reSpeaker" if audio_mode == "robot" else None),
            audio_output_device=_audio_device_env("AUDIO_OUTPUT_DEVICE"),
            audio_sample_rate=_positive_integer_env(
                "AUDIO_SAMPLE_RATE",
                16000,
            ),
            # ReSpeaker 는 2채널(왼쪽=처리된 빔, 오른쪽=원본 mic0)로 열어 왼쪽만 쓴다.
            # 위와 같은 이유로 robot 모드에서만 2다 — 노트북 마이크에 2채널을 요구하면
            # 장치에 따라 InputStream 열기가 실패한다 (S15P11E102-233).
            audio_channels=_positive_integer_env(
                "AUDIO_CHANNELS", 2 if audio_mode == "robot" else 1),
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
            # 웨이크워드: 로봇 배포에선 켜는 게 기본. 노트북 개발에선 .env 로 끌 수 있다.
            wakeword_enabled=_bool_env("WAKEWORD_ENABLED", True),
            wakeword_model_path=(
                _optional_env("WAKEWORD_MODEL_PATH", "models/bomiya.onnx")
                or "models/bomiya.onnx"
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
            backend_shared_secret=_optional_env("BACKEND_SHARED_SECRET"),
            robot_id=_optional_env("ROBOT_ID"),
            robot_device_id=_optional_env("ROBOT_DEVICE_ID"),
            senior_id=_optional_env("SENIOR_ID"),
            use_graph_runtime=_bool_env("USE_GRAPH_RUNTIME", True),
            t3_consent_enabled=_bool_env("T3_CONSENT_ENABLED", True),
            extraction_enabled=_bool_env("EXTRACTION_ENABLED", True),
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
