"""외부 환경과 격리된 pytest 공통 fixture."""

from collections.abc import Callable

import pytest
import requests

from bomi_ai_chat.clock import Clock, SimClock, install_clock
from bomi_ai_chat.config import Settings, clear_settings_cache

SETTING_VARIABLES = (
    "AI_CHAT_ENV_FILE",
    "RTZR_CLIENT_ID",
    "RTZR_CLIENT_SECRET",
    "GEMINI_API_KEY",
    "TYPECAST_API_KEY",
    "TYPECAST_VOICE_ID",
    "KMA_API_KEY",
    "AUDIO_MODE",
    "AUDIO_INPUT_DEVICE",
    "AUDIO_OUTPUT_DEVICE",
    "AUDIO_SAMPLE_RATE",
    "AUDIO_CHANNELS",
    "AUDIO_CHUNK_SECONDS",
    "AUDIO_SILENCE_THRESHOLD",
    "AUDIO_SILENCE_LIMIT_SECONDS",
    "AUDIO_MAX_SECONDS",
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
    "LOCALSTORE_DIR",
    "BACKEND_BASE_URL",
    "BACKEND_TIMEOUT_SECONDS",
    "ROBOT_ID",
    # 개발자 .env 의 MQTT 설정이 테스트로 새면, 브로커에 실제로 붙으려 하거나
    # 비활성 기본값을 검증하는 테스트가 머신마다 다른 결과를 낸다.
    "MQTT_ENABLED",
    "MQTT_BROKER_URL",
    "MQTT_DOOR_TOPIC",
    "MQTT_CLIENT_ID",
    "MQTT_USERNAME",
    "MQTT_PASSWORD",
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
def frozen_clock():
    """스스로 흐르지 않는 시계를 설치하고, 테스트가 끝나면 되돌린다.

    왜 speed=0.0 인가
        SimClock 의 기본값 speed=1.0 은 시작점부터 '실제 시간과 함께' 흐른다.
        그래서 now() 가 정확히 start 값이 아니고, 시각을 직접 비교하는 단위 테스트가
        머신 부하에 따라 흔들린다. speed=0.0 은 시간을 멈춰서 advance() 로만
        움직이게 하므로, "3시간 뒤"를 결정적으로 재현할 수 있다.

    사용 예
        def test_something(frozen_clock):
            sim = frozen_clock(start=1_000.0)
            ...
            sim.advance(3 * 3600)
    """

    installed: list[Clock] = []

    def install(start: float = 1_700_000_000.0) -> SimClock:
        sim = SimClock(start=start, speed=0.0)
        installed.append(install_clock(sim))
        return sim

    yield install

    # 설치한 역순으로 되돌린다. 전역 상태이므로 복원을 빼먹으면 이후 테스트가
    # 가짜 시계를 물려받는다.
    for previous in reversed(installed):
        install_clock(previous)


@pytest.fixture
def settings_factory(monkeypatch) -> Callable[..., Settings]:
    """필요한 환경변수만 주입한 Settings를 만드는 공통 factory."""

    def build(**values: str) -> Settings:
        for name, value in values.items():
            monkeypatch.setenv(name, value)
        return Settings.from_env(load_env_file=False)

    return build
