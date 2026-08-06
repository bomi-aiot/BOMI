"""웨이크워드 감지 MQTT 발행 — S15P11E102-349 회귀.

이 파일이 검증하는 것
    1. 봉투·토픽이 백엔드 계약(WakeWordDetectedHandler, MqttInboundMessageParser)과
       일치한다 — 여기가 어긋나면 서버가 조용히 거절하고 시나리오는 안 돈다
    2. MQTT 꺼짐 / 설정 결손이면 발행자가 만들어지지 않는다 (이유가 로그에 남는다)
    3. 발행 실패·발행자 예외가 대화 시작을 막지 않는다 — 시나리오는 부가, 대화가 본체
    4. 대화 루프가 웨이크마다 정확히 한 번 발행하고, 끝날 때 발행자를 정리한다

참고
    CLAUDE.md §24, be-develop S15P11E102-335
"""

import json

import pytest

from bomi_ai_chat import bootstrap, robot_events
from bomi_ai_chat.localstore import db

SENIOR = "senior-1"
NOW = 1_700_000_000.0


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()


def settings_with(settings_factory, **extra):
    return settings_factory(
        RTZR_CLIENT_ID="id",
        RTZR_CLIENT_SECRET="secret",
        GEMINI_API_KEY="gemini",
        TYPECAST_API_KEY="typecast",
        SENIOR_ID=SENIOR,
        **extra,
    )


def mqtt_settings(settings_factory, **extra):
    return settings_with(
        settings_factory,
        MQTT_ENABLED="true",
        MQTT_BROKER_URL="mqtt://broker.example:1883",
        ROBOT_ID="robot-7",
        **extra,
    )


class FakeMqttClient:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.published: list[tuple[str, str]] = []

    def publish(self, topic, payload):
        if self.fail:
            raise RuntimeError("broker gone")
        self.published.append((topic, payload))

    def loop_stop(self):
        pass

    def disconnect(self):
        pass


# ── 1. 봉투·토픽 계약 ───────────────────────────────────────────────────────


def test_the_envelope_matches_the_backend_contract(settings_factory, frozen_clock):
    """★ 토픽 bomi/v1/robot/{robotId}/events + type/eventId/occurredAt/payload.

    백엔드 파서는 type 허용 목록·occurredAt 형식·payload 객체를 검사하고
    어긋나면 조용히 버린다. 이 테스트가 그 계약의 로봇 쪽 고정이다.
    """
    frozen_clock(start=NOW)
    client = FakeMqttClient()
    publisher = robot_events.RobotEventPublisher(
        mqtt_settings(settings_factory), client=client)

    publisher.publish_wake_word(confidence=0.87)

    assert len(client.published) == 1
    topic, raw = client.published[0]
    assert topic == "bomi/v1/robot/robot-7/events"
    envelope = json.loads(raw)
    assert envelope["type"] == "WAKE_WORD_DETECTED"
    assert envelope["eventId"], "eventId 가 비어 있으면 서버 중복 제거가 못 돈다"
    # occurredAt 은 오프셋이 붙은 ISO-8601 이어야 한다 (서버 OffsetDateTime).
    assert envelope["occurredAt"].endswith("+00:00")
    assert envelope["payload"] == {"keyword": "보미야", "confidence": 0.87}


def test_confidence_is_optional(settings_factory, frozen_clock):
    frozen_clock(start=NOW)
    client = FakeMqttClient()
    publisher = robot_events.RobotEventPublisher(
        mqtt_settings(settings_factory), client=client)

    publisher.publish_wake_word()

    envelope = json.loads(client.published[0][1])
    assert envelope["payload"] == {"keyword": "보미야"}


# ── 2. 빌더 게이트 ──────────────────────────────────────────────────────────


def test_disabled_mqtt_builds_no_publisher(settings_factory, caplog):
    """MQTT 가 꺼져 있으면 발행하지 않는다 — 다만 그 사실이 로그에 보여야 한다.

    "보미야 호출 시나리오가 왜 한 번도 안 도는가"를 조사할 때 여기서 꺼져
    있었다는 것이 첫 확인 지점이다.
    """
    with caplog.at_level("INFO"):
        publisher = robot_events.build_robot_event_publisher(
            settings_with(settings_factory))

    assert publisher is None
    assert "MQTT is disabled" in caplog.text


def test_missing_robot_id_builds_no_publisher(settings_factory, caplog):
    with caplog.at_level("WARNING"):
        publisher = robot_events.build_robot_event_publisher(
            settings_with(settings_factory,
                          MQTT_ENABLED="true",
                          MQTT_BROKER_URL="mqtt://broker.example:1883"))

    assert publisher is None
    assert "ROBOT_ID" in caplog.text


# ── 3. 실패가 대화를 막지 않는다 ────────────────────────────────────────────


def test_a_publish_failure_is_swallowed(settings_factory, frozen_clock):
    frozen_clock(start=NOW)
    publisher = robot_events.RobotEventPublisher(
        mqtt_settings(settings_factory), client=FakeMqttClient(fail=True))

    publisher.publish_wake_word()  # 예외가 올라오면 이 줄에서 테스트가 죽는다


def test_publish_without_a_client_is_a_noop(settings_factory):
    """start() 가 실패했으면(브로커 없음) 발행은 조용히 건너뛴다."""
    publisher = robot_events.RobotEventPublisher(
        mqtt_settings(settings_factory), client=None)

    publisher.publish_wake_word()


# ── 4. 대화 루프 배선 ───────────────────────────────────────────────────────


class RecordingPublisher:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.publishes = 0
        self.stopped = False

    def publish_wake_word(self, **kwargs):
        self.publishes += 1
        if self.fail:
            raise RuntimeError("publisher broke")

    def stop(self):
        self.stopped = True


class OneWake:
    def __init__(self, wakes=1):
        self.wakes_left = wakes

    def wait_for_wake(self):
        if self.wakes_left == 0:
            raise KeyboardInterrupt
        self.wakes_left -= 1


class ScriptedAudio:
    def __init__(self, *chunks):
        self.chunks = list(chunks)

    def capture(self, onset_timeout_seconds=None):
        if not self.chunks:
            return b""  # 무응답 -> 대화 종료
        return self.chunks.pop(0)


class OneShotStt:
    def __init__(self, *texts):
        self.texts = list(texts)

    def transcribe(self, audio):
        return self.texts.pop(0) if self.texts else ""


def run_loop(monkeypatch, settings_factory, publisher, *, wakes=1, chunks=(b"a",),
             texts=("안녕",)):
    monkeypatch.setattr("bomi_ai_chat.stt.client.STTClient",
                        lambda settings: OneShotStt(*texts))
    turns = []
    monkeypatch.setattr("bomi_ai_chat.graph.turn.run_user_turn",
                        lambda app, senior, text, **kw: turns.append(text) or {})
    runtime = bootstrap.Runtime(app=object(), senior_id=SENIOR)
    count = bootstrap.run_conversation_loop(
        runtime, ScriptedAudio(*chunks), settings_with(settings_factory),
        wake=OneWake(wakes), event_publisher=publisher)
    return turns, count


def test_the_loop_publishes_once_per_wake_and_stops_the_publisher(
    monkeypatch, settings_factory, frozen_clock):
    frozen_clock(start=NOW)
    publisher = RecordingPublisher()

    turns, count = run_loop(monkeypatch, settings_factory, publisher)

    assert publisher.publishes == 1, "웨이크 한 번에 발행 한 번이다"
    assert turns == ["안녕"], "발행이 대화 처리를 바꾸면 안 된다"
    assert publisher.stopped is True, "루프가 끝나면 발행자를 정리해야 한다"


def test_a_broken_publisher_does_not_block_the_conversation(
    monkeypatch, settings_factory, frozen_clock):
    """★ 발행자가 던져도 호출 응답과 대화는 그대로 진행된다."""
    frozen_clock(start=NOW)
    publisher = RecordingPublisher(fail=True)

    turns, _count = run_loop(monkeypatch, settings_factory, publisher)

    assert publisher.publishes == 1
    assert turns == ["안녕"], "시나리오는 부가 기능이고 대화가 본체다"
