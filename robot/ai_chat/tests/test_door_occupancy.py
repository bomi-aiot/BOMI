"""현관 이벤트와 재실 상태 — 208 완료 조건 회귀.

이 파일이 검증하는 완료 조건
    1. 문 이벤트 -> occupancy 즉시 전환, 게이트를 거치지 않음
    2. 방향을 만들지 않는다. 문 활동은 보수적으로 UNKNOWN
    3. 하트비트 중단 -> UNKNOWN 강등
    4. 라즈베리파이 시각이 틀려도 도착 시각으로 정규화됨
    5. 야간 외출·장시간 미귀가가 outbox 에 적재
    6. 이벤트가 백엔드로 전달됨(판정은 백엔드)
    7. door_event 가 인사를 제안하지 않는다  <- 2026-08-01 재정의의 핵심

가장 중요한 두 테스트
    test_door_event_does_not_propose_a_greeting
        인사 판정이 백엔드로 갔다는 것을 코드로 못박는다. 누가 이 노드에 제안을
        되돌려 놓으면 심판이 둘이 되고, 백엔드가 보낸 인사가 로봇의 쿨다운에
        조용히 삼켜지기 시작한다.

    test_speech_beats_a_stale_backend_occupancy
        말하고 있는 사람이 AWAY 로 바뀌면 침묵 사다리가 정지한다. 그리고 아무도
        그 사실을 모른다.

참고
    CLAUDE.md §11 (현관과 재실), §10 (사다리가 읽는 값)
    S15P11E102-208, S15P11E102-226(백엔드 방향 판정)
"""

import json

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.contracts.door import DoorEventError, parse_door_event
from bomi_ai_chat.door import intake
from bomi_ai_chat.door import occupancy as occupancy_rules
from bomi_ai_chat.graph import ingress
from bomi_ai_chat.jobs import ticks
from bomi_ai_chat.localstore import context_cache, db, outbox
from bomi_ai_chat.localstore import runtime as runtime_store

SENIOR = "senior-1"

# 2026-08-01 00:00 UTC = 서울 09:00
MORNING_UTC = 1785542400.0
HOUR = 3600.0

SEOUL_PROFILE = {
    "profile": {
        "timeZone": "Asia/Seoul",
        "quietHoursStart": "22:00",
        "quietHoursEnd": "07:00",
    }
}


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()


class RecordingDoorClient:
    """전달된 이벤트를 기록한다. 성공/실패를 지정할 수 있다."""

    def __init__(self, *, ok: bool = True):
        self.ok = ok
        self.sent: list[tuple[str, object]] = []

    def forward_event(self, senior_id, event) -> bool:
        self.sent.append((senior_id, event))
        return self.ok


def envelope(event_type: str, *, occurred_at=None, direction=None, source="door-01"):
    """규약(docs/mqtt/topic-convention.md)에 맞는 봉투를 만든다."""
    payload: dict = {}
    if direction is not None:
        payload["direction"] = direction
    message: dict = {
        "eventId": f"evt-{event_type}",
        "type": event_type,
        "sourceId": source,
        "payload": payload,
    }
    if occurred_at is not None:
        message["occurredAt"] = occurred_at
    return message


# ── 계약: 봉투 파싱과 시각 정규화 ─────────────────────────────────────────────


def test_arrival_time_is_authoritative_even_when_the_pi_clock_is_wrong(frozen_clock):
    """(완료조건 4) 라즈베리파이가 1970년을 주장해도 도착 시각을 쓴다.

    배터리 백업 RTC 가 없는 라즈베리파이는 재부팅 후 시계가 틀린 채로 돈다.
    틀린 문 이벤트 시각은 루틴 베이스라인 학습과 TTL 산술을 함께 오염시킨다.
    """
    frozen_clock(start=MORNING_UTC)

    event = parse_door_event(envelope("DOOR_OPENED", occurred_at="1970-01-01T00:00:00+00:00"))

    assert event.received_at == MORNING_UTC
    # 원본은 버리지 않고 참고용으로 남긴다. 서버 쪽에서도 어긋난 시계를 볼 수 있어야 한다.
    assert event.reported_at == 0.0
    assert event.clock_skew_sec == MORNING_UTC


def test_missing_occurred_at_does_not_drop_the_event(frozen_clock):
    """참고용 값 하나가 없다고 문 이벤트를 버리지 않는다.

    버리면 시계가 망가진 라즈베리파이가 곧 현관 감시를 통째로 끄는 셈이 된다.
    """
    frozen_clock(start=MORNING_UTC)

    event = parse_door_event(envelope("DOOR_OPENED"))

    assert event.reported_at is None
    assert event.received_at == MORNING_UTC


def test_naive_occurred_at_is_ignored_not_guessed(frozen_clock):
    """타임존 없는 시각을 로컬로 가정하지 않는다. 9시간 어긋난 값이 조용히 들어온다."""
    frozen_clock(start=MORNING_UTC)

    event = parse_door_event(envelope("DOOR_OPENED", occurred_at="2026-08-01T09:00:00"))

    assert event.reported_at is None


def test_json_bytes_and_dict_are_all_accepted(frozen_clock):
    """브로커는 bytes 를 주고, 테스트는 dict 를 준다. 둘 다 같은 결과여야 한다."""
    frozen_clock(start=MORNING_UTC)
    message = envelope("MOTION_DETECTED")

    from_dict = parse_door_event(message)
    from_bytes = parse_door_event(json.dumps(message).encode("utf-8"))

    assert from_dict.type == from_bytes.type == "MOTION_DETECTED"


def test_unknown_event_type_is_rejected_loudly(frozen_clock):
    """조용히 무시하면 "센서가 안 왔다"와 "메시지를 못 읽었다"가 구분되지 않는다."""
    frozen_clock(start=MORNING_UTC)

    with pytest.raises(DoorEventError, match="unknown door event type"):
        parse_door_event(envelope("WINDOW_SMASHED"))


# ── 재실 규칙: 로봇은 방향을 만들지 않는다 ─────────────────────────────────────


def test_door_activity_resolves_to_unknown_never_home_or_away():
    """(완료조건 2) 문 활동은 UNKNOWN 이다. 추측하지 않는다.

    HOME 이라고 두면 빈 집을 상대로 사다리가 돌고, AWAY 라고 두면 집에 있는
    사람에 대한 감시가 꺼진다. 둘 다 조용한 실패다.
    """
    assert occupancy_rules.local_occupancy_for("DOOR_OPENED") == "UNKNOWN"
    assert occupancy_rules.local_occupancy_for("MOTION_DETECTED") == "UNKNOWN"
    # 문이 닫힌 것과 하트비트는 재실에 대해 아무 말도 하지 않는다.
    assert occupancy_rules.local_occupancy_for("DOOR_CLOSED") is None
    assert occupancy_rules.local_occupancy_for("HEARTBEAT") is None


def test_home_is_downgraded_to_unknown_when_the_door_opens(frozen_clock):
    """HOME 이었어도 문이 열리면 UNKNOWN 으로 내린다.

    옛 HOME 을 유지하는 것은 "모른다"를 "집에 있다"로 바꿔 말하는 것이다.
    """
    sim = frozen_clock(start=MORNING_UTC)
    occupancy_rules.set_occupancy(SENIOR, "HOME", observed_at=MORNING_UTC, source="speech")

    sim.advance(60)
    intake.ingest(SENIOR, parse_door_event(envelope("DOOR_OPENED")))

    assert runtime_store.load(SENIOR)["occupancy"] == "UNKNOWN"


def test_speech_beats_a_stale_backend_occupancy(frozen_clock):
    """★ 발화가 센서를 이긴다 — 낡은 관측은 적용되지 않는다.

    어르신이 방금 말했다(HOME, t+60). 백엔드가 t+0 에 일어난 외출을 이제야 판정해
    AWAY 를 내려보낸다. 도착 순서대로 적용하면 말하고 있는 사람이 AWAY 가 되고,
    그 상태로 침묵 사다리가 정지한다. 그리고 아무도 그 사실을 모른다.
    """
    sim = frozen_clock(start=MORNING_UTC)

    sim.advance(60)
    occupancy_rules.set_occupancy(
        SENIOR, "HOME", observed_at=MORNING_UTC + 60, source="speech")

    # 뒤늦게 도착한, 더 오래된 관측.
    written = occupancy_rules.apply_backend_occupancy(
        SENIOR, "AWAY", observed_at=MORNING_UTC)

    assert written == {}
    assert runtime_store.load(SENIOR)["occupancy"] == "HOME"


def test_backend_occupancy_applies_when_it_is_newer(frozen_clock):
    """반대로, 발화 뒤에 실제로 나갔으면 AWAY 가 적용되어야 한다."""
    sim = frozen_clock(start=MORNING_UTC)
    occupancy_rules.set_occupancy(SENIOR, "HOME", observed_at=MORNING_UTC, source="speech")

    sim.advance(120)
    occupancy_rules.apply_backend_occupancy(
        SENIOR, "AWAY", observed_at=MORNING_UTC + 120)

    stored = runtime_store.load(SENIOR)
    assert stored["occupancy"] == "AWAY"
    assert stored["away_since"] == MORNING_UTC + 120


def test_away_since_is_not_reset_by_repeated_away_observations(frozen_clock):
    """★ 부재 '시작' 시각은 한 번만 찍는다.

    AWAY 를 다시 관측할 때마다 시작 시각을 갱신하면 부재 시간이 매번 0 으로
    리셋되어 미귀가 알림이 영원히 나가지 않는다.
    """
    sim = frozen_clock(start=MORNING_UTC)
    occupancy_rules.apply_backend_occupancy(SENIOR, "AWAY", observed_at=MORNING_UTC)

    sim.advance(2 * HOUR)
    occupancy_rules.apply_backend_occupancy(SENIOR, "AWAY", observed_at=MORNING_UTC + 2 * HOUR)

    assert runtime_store.load(SENIOR)["away_since"] == MORNING_UTC


def test_returning_home_clears_away_since(frozen_clock):
    """귀가하면 부재 시작 시각을 지운다. 안 지우면 다음 외출이 이미 6시간째로 계산된다."""
    sim = frozen_clock(start=MORNING_UTC)
    occupancy_rules.apply_backend_occupancy(SENIOR, "AWAY", observed_at=MORNING_UTC)

    sim.advance(HOUR)
    occupancy_rules.apply_backend_occupancy(SENIOR, "HOME", observed_at=MORNING_UTC + HOUR)

    assert runtime_store.load(SENIOR)["away_since"] == 0.0


def test_unknown_occupancy_value_is_rejected():
    """오타가 조용히 저장되면 사다리가 이상하게 동작한다."""
    with pytest.raises(ValueError, match="unknown occupancy"):
        occupancy_rules.set_occupancy(SENIOR, "away", observed_at=0.0, source="test")


# ── intake: 하트비트, 문 개폐, 전달 ───────────────────────────────────────────


def test_any_event_counts_as_a_heartbeat(frozen_clock):
    """★ HEARTBEAT 타입만 인정하면 살아있는 증거를 무시하는 셈이 된다.

    문은 부지런히 열리는데 하트비트 발행만 죽은 라즈베리파이에서 occupancy 가
    UNKNOWN 으로 강등된다.
    """
    frozen_clock(start=MORNING_UTC)

    intake.ingest(SENIOR, parse_door_event(envelope("DOOR_CLOSED")))

    assert runtime_store.load(SENIOR)["door_heartbeat_at"] == MORNING_UTC


def test_open_and_close_track_door_open_since(frozen_clock):
    """문 개폐가 door_open_since 를 켜고 끈다."""
    sim = frozen_clock(start=MORNING_UTC)

    intake.ingest(SENIOR, parse_door_event(envelope("DOOR_OPENED")))
    assert runtime_store.load(SENIOR)["door_open_since"] == MORNING_UTC

    sim.advance(30)
    intake.ingest(SENIOR, parse_door_event(envelope("DOOR_CLOSED")))
    assert runtime_store.load(SENIOR)["door_open_since"] == 0.0


def test_event_is_forwarded_to_the_backend(frozen_clock):
    """(완료조건 6) 판정은 백엔드가 한다. 로봇은 사실을 올린다."""
    frozen_clock(start=MORNING_UTC)
    client = RecordingDoorClient()

    result = intake.ingest(SENIOR, parse_door_event(envelope("DOOR_OPENED")),
                          door_client=client)

    assert result["forwarded"] is True
    assert len(client.sent) == 1
    assert client.sent[0][0] == SENIOR


def test_local_occupancy_survives_a_failed_forward(frozen_clock):
    """전달 실패는 인사를 잃는 것이고, 안전 감시를 잃는 것이 아니다."""
    frozen_clock(start=MORNING_UTC)
    client = RecordingDoorClient(ok=False)

    result = intake.ingest(SENIOR, parse_door_event(envelope("DOOR_OPENED")),
                           door_client=client)

    assert result["forwarded"] is False
    # 오프라인에서도 사다리가 읽는 값은 갱신돼 있어야 한다.
    assert runtime_store.load(SENIOR)["occupancy"] == "UNKNOWN"
    assert runtime_store.load(SENIOR)["door_heartbeat_at"] == MORNING_UTC


def test_sensor_supplied_direction_is_not_acted_on(frozen_clock):
    """★ 센서 토픽의 direction 을 믿지 않는다.

    믿기 시작하면 방향 판정이 로봇에도 생긴 것이다. 확정 재실 상태가 들어오는
    경로는 apply_backend_occupancy 하나여야 한다 (CLAUDE.md §11).
    """
    frozen_clock(start=MORNING_UTC)

    event = parse_door_event(envelope("DOOR_OPENED", direction="out"))
    intake.ingest(SENIOR, event)

    # 계약 변경 사실은 읽어 두지만(로그로 남긴다), AWAY 로 바꾸지는 않는다.
    assert event.direction == "out"
    assert runtime_store.load(SENIOR)["occupancy"] == "UNKNOWN"


# ── 그래프: door_event 는 사실만 반영하고 끝난다 ──────────────────────────────


def test_door_event_does_not_propose_a_greeting(frozen_clock):
    """★★ (완료조건 7) 인사 판정은 백엔드 몫이다.

    초안에서는 이 노드가 인사를 제안하고 로봇의 게이트가 심판했다. 합의된 구조는
    다르다. 누가 제안을 되돌려 놓으면 심판이 둘이 되고, 백엔드가 보낸 인사가
    로봇의 쿨다운에 조용히 삼켜지기 시작한다.
    """
    frozen_clock(start=MORNING_UTC)

    out = ingress.door_event({
        "senior_id": SENIOR,
        "last_door_event": {"type": "DOOR_OPENED", "ts": MORNING_UTC, "direction": None},
    })

    assert "proposals" not in out
    assert out["occupancy"] == "UNKNOWN"


def test_door_event_reaches_the_durable_store_not_just_the_checkpoint(frozen_clock):
    """★ 침묵 사다리는 그래프를 거치지 않고 runtime_state 를 읽는다.

    checkpoint 에만 쓰면 문 이벤트가 안전 감시에 영원히 도달하지 못한다.
    """
    frozen_clock(start=MORNING_UTC)

    ingress.door_event({
        "senior_id": SENIOR,
        "last_door_event": {"type": "DOOR_OPENED", "ts": MORNING_UTC},
    })

    assert runtime_store.load(SENIOR)["occupancy"] == "UNKNOWN"


def test_door_closed_says_nothing_about_occupancy(frozen_clock):
    """문이 닫힌 것으로 재실 상태를 바꾸지 않는다."""
    frozen_clock(start=MORNING_UTC)

    out = ingress.door_event({
        "senior_id": SENIOR,
        "last_door_event": {"type": "DOOR_CLOSED", "ts": MORNING_UTC},
    })

    assert out == {}


def test_note_interaction_persists_the_survival_signal(frozen_clock):
    """★ 208 에서 발견한 결함의 회귀 테스트.

    note_interaction 이 checkpoint 에만 쓰던 동안, runtime_state 의
    last_user_interaction_at 은 0 에 머물렀다. silence_tick 은 그 값을 읽고
    `<= 0.0` 가드에서 매번 조용히 되돌아갔다 — 즉 침묵 사다리가 실기에서
    한 번도 돌지 않는 상태였다.
    """
    frozen_clock(start=MORNING_UTC)
    runtime_store.save(SENIOR, silence_level=2)

    ingress.note_interaction({"senior_id": SENIOR, "user_input": "밥 먹었어"})

    stored = runtime_store.load(SENIOR)
    assert stored["last_user_interaction_at"] == MORNING_UTC
    assert stored["silence_level"] == 0
    assert stored["occupancy"] == "HOME"


# ── 백엔드 명령 경로 ──────────────────────────────────────────────────────────


def test_backend_command_carries_the_final_text(frozen_clock):
    """문구는 백엔드가 정한다. 로봇은 다시 고르지 않는다."""
    frozen_clock(start=MORNING_UTC)

    out = ingress.backend_command({
        "senior_id": SENIOR,
        "command": {
            "text": "비 와요, 우산 챙기세요.",
            "intent": "greeting",
            "origin": "scenario:homecoming",
        },
    })

    assert out["user_input"] == "비 와요, 우산 챙기세요."
    assert out["intent"] == "greeting"
    assert out["speech_origin"] == "scenario:homecoming"


def test_backend_command_clears_stale_closing_turn(frozen_clock):
    """A new greeting must not inherit the previous conversation's final turn."""
    frozen_clock(start=MORNING_UTC)

    out = ingress.backend_command({
        "senior_id": SENIOR,
        "closing_turn": True,
        "command": {
            "text": "다녀오셨어요? 오늘 외출은 어떠셨어요?",
            "intent": "greeting",
            "origin": "scenario:HOMECOMING_GREETING",
        },
    })

    assert out["closing_turn"] is False
    assert out["user_input"] == "다녀오셨어요? 오늘 외출은 어떠셨어요?"


def test_backend_command_can_confirm_occupancy(frozen_clock):
    """방향을 판정한 쪽이 확정 재실 상태를 함께 내려보낸다."""
    frozen_clock(start=MORNING_UTC)

    out = ingress.backend_command({
        "senior_id": SENIOR,
        "command": {
            "text": "다녀오세요.",
            "occupancy": "AWAY",
            "occupancyObservedAt": MORNING_UTC,
        },
    })

    assert out["occupancy"] == "AWAY"
    assert runtime_store.load(SENIOR)["occupancy"] == "AWAY"


def test_empty_backend_command_says_nothing(frozen_clock):
    """빈 문장을 파이프라인에 올리면 TTS 가 무음을 재생한다."""
    frozen_clock(start=MORNING_UTC)

    out = ingress.backend_command({"senior_id": SENIOR, "command": {"text": "   "}})

    # ★ 값이 아예 없는 게 아니라 명시적으로 None 이어야 한다 — 체크포인트에
    # 남은 지난 턴의 intent/user_input 을 classify_intent 가 재사용하지
    # 않도록 이번 턴이 직접 비운다(랭그래프 분석에서 발견된 오염 방지).
    assert out["user_input"] is None
    assert out["intent"] is None


def test_empty_backend_command_clears_a_stale_checkpointed_intent(frozen_clock):
    """★ 회귀: 빈 명령이 '이전 턴의' intent/user_input 을 재사용하게 두지 않는다.

    checkpointer 가 물려주는 state 에 지난 backend_command 턴의 intent 가
    남아 있어도, 이번 턴이 빈 명령이면 그 값을 지워야 한다. 안 그러면
    classify_intent 가 "이미 분류됨"으로 착각해 지난 문구를 그대로 다시
    말하게 된다.
    """
    frozen_clock(start=MORNING_UTC)

    stale_state = {
        "senior_id": SENIOR,
        "intent": "greeting",
        "user_input": "어제 남은 오래된 문구",
        "command": {"text": "   "},  # 이번엔 말할 게 없다
    }

    out = ingress.backend_command(stale_state)

    assert out["intent"] is None
    assert out["user_input"] is None


def test_greeting_handler_passes_the_backend_text_through(frozen_clock):
    """handle_greeting 이 얇은 것이 의도다. 선택은 백엔드가 했다."""
    frozen_clock(start=MORNING_UTC)
    from bomi_ai_chat.graph import handlers

    out = handlers.handle_greeting({"user_input": "어서 오세요, 물 한 잔 드릴까요?"})

    assert out["response"] == "어서 오세요, 물 한 잔 드릴까요?"


# ── door_watch_tick: 사다리가 볼 수 없는 것들 ─────────────────────────────────


class CollectingChannel:
    """보호자 채널 대역. 전송된 알림을 누적한다.

    왜 outbox 를 SQL 로 들여다보지 않는가
        검증하려는 것은 "보호자에게 무엇이 도달하는가"다. 표의 모양이 아니다.
        flush 를 거쳐 보면 티어와 payload 가 실제 전송 경로 그대로 보인다
        (test_outbox.py 와 같은 방식).
    """

    def __init__(self):
        self.delivered: list[tuple[str, dict]] = []

    def notify_guardian(self, tier: str, payload: dict) -> None:
        self.delivered.append((tier, payload))


@pytest.fixture
def guardian():
    return CollectingChannel()


def door_alerts(guardian, reason: str | None = None) -> list[tuple[str, dict]]:
    """지금까지 보호자에게 도달한 현관 알림. reason 으로 걸러 볼 수 있다."""
    outbox.flush(guardian)
    if reason is None:
        return list(guardian.delivered)
    return [(tier, p) for tier, p in guardian.delivered if p.get("reason") == reason]


def test_heartbeat_loss_degrades_occupancy_and_reports_it(frozen_clock, guardian):
    """(완료조건 3) 라즈베리파이가 죽으면 UNKNOWN 으로 내리고 보호자에게 알린다.

    강등만 하고 조용히 있으면 '조용한 실패'를 UNKNOWN 이라는 이름으로 바꿔 부른
    것에 지나지 않는다. 현관 감시가 꺼졌다는 사실은 누군가 조치할 수 있어야 한다.
    기기 문제이므로 T2 다.
    """
    sim = frozen_clock(start=MORNING_UTC)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    occupancy_rules.apply_backend_occupancy(SENIOR, "AWAY", observed_at=MORNING_UTC)
    runtime_store.save(SENIOR, door_heartbeat_at=MORNING_UTC)

    sim.advance(policy.DOOR_HEARTBEAT_TIMEOUT_SEC + 60)
    ticks.door_watch_tick(SENIOR, None)

    assert runtime_store.load(SENIOR)["occupancy"] == "UNKNOWN"
    assert len(door_alerts(guardian, "door_node_offline")) == 1


def test_heartbeat_alert_is_not_repeated_every_tick(frozen_clock, guardian):
    """★ 60초마다 같은 알림이 쌓이면 보호자가 알림을 읽지 않게 된다."""
    sim = frozen_clock(start=MORNING_UTC)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    runtime_store.save(SENIOR, door_heartbeat_at=MORNING_UTC)

    sim.advance(policy.DOOR_HEARTBEAT_TIMEOUT_SEC + 60)
    for _ in range(5):
        sim.advance(60)
        ticks.door_watch_tick(SENIOR, None)

    assert len(door_alerts(guardian, "door_node_offline")) == 1


def test_never_seen_door_node_does_not_spam(frozen_clock, guardian):
    """하트비트가 한 번도 없으면 "미설치"와 "죽었다"를 구분할 수 없다. 알리지 않는다."""
    sim = frozen_clock(start=MORNING_UTC)
    context_cache.save(SENIOR, SEOUL_PROFILE)

    sim.advance(2 * HOUR)
    ticks.door_watch_tick(SENIOR, None)

    assert door_alerts(guardian) == []


def test_door_left_open_is_reported(frozen_clock, guardian):
    """★ 방향 없이 로봇이 혼자 판정할 수 있는 유일한 현관 신호."""
    sim = frozen_clock(start=MORNING_UTC)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    intake.ingest(SENIOR, parse_door_event(envelope("DOOR_OPENED")))

    sim.advance(policy.DOOR_OPEN_TOO_LONG_SEC + 60)
    ticks.door_watch_tick(SENIOR, None)

    alerts = door_alerts(guardian, "door_left_open")
    assert len(alerts) == 1
    tier, payload = alerts[0]
    assert tier == "T2"
    assert payload["open_sec"] >= policy.DOOR_OPEN_TOO_LONG_SEC


def test_briefly_open_door_is_not_reported(frozen_clock, guardian):
    """잠깐 열고 닫은 문에 알림이 가면 안 된다."""
    sim = frozen_clock(start=MORNING_UTC)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    intake.ingest(SENIOR, parse_door_event(envelope("DOOR_OPENED")))

    sim.advance(30)
    intake.ingest(SENIOR, parse_door_event(envelope("DOOR_CLOSED")))
    sim.advance(HOUR)
    ticks.door_watch_tick(SENIOR, None)

    assert door_alerts(guardian, "door_left_open") == []


def test_long_absence_escalates_from_t2_to_t1(frozen_clock, guardian):
    """(완료조건 5) 미귀가는 T2 로 시작해 T1 이 된다.

    사다리는 이것을 볼 수 없다 — 집에 아무도 없으면 아예 시작되지 않는다.
    """
    sim = frozen_clock(start=MORNING_UTC)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    occupancy_rules.apply_backend_occupancy(SENIOR, "AWAY", observed_at=MORNING_UTC)
    runtime_store.save(SENIOR, door_heartbeat_at=MORNING_UTC)

    # 6시간: 보고할 만하다.
    sim.advance(policy.ABSENCE_CONCERN_SEC + 60)
    runtime_store.save(SENIOR, door_heartbeat_at=MORNING_UTC + policy.ABSENCE_CONCERN_SEC)
    ticks.door_watch_tick(SENIOR, None)
    assert len(door_alerts(guardian, "long_absence")) == 1
    assert door_alerts(guardian, "not_returned") == []

    # 12시간: 밤을 넘긴 미귀가는 명백한 이상이다.
    sim.advance(policy.ABSENCE_ALERT_SEC - policy.ABSENCE_CONCERN_SEC)
    runtime_store.save(SENIOR, door_heartbeat_at=MORNING_UTC + policy.ABSENCE_ALERT_SEC)
    ticks.door_watch_tick(SENIOR, None)
    assert len(door_alerts(guardian, "not_returned")) == 1


def test_absence_alerts_are_tiered_correctly(frozen_clock, guardian):
    """T1 과 T2 를 뒤집으면 보호자가 알림을 신뢰하지 않게 된다."""
    sim = frozen_clock(start=MORNING_UTC)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    occupancy_rules.apply_backend_occupancy(SENIOR, "AWAY", observed_at=MORNING_UTC)
    runtime_store.save(SENIOR, door_heartbeat_at=MORNING_UTC)

    sim.advance(policy.ABSENCE_ALERT_SEC + 60)
    runtime_store.save(SENIOR, door_heartbeat_at=MORNING_UTC + policy.ABSENCE_ALERT_SEC)
    ticks.door_watch_tick(SENIOR, None)

    tiers = {tier for tier, _ in door_alerts(guardian)}
    assert "T1" in tiers


def test_night_exit_is_reported_as_a_trend_not_an_emergency(frozen_clock, guardian):
    """야간 배회는 침묵이 아니라 '활동'이라서 사다리에게 구조적으로 보이지 않는다.

    치매의 대표 증상이므로 인지 축이 객관적 신호를 얻는 곳이 이 검사다.
    다만 한 번의 야간 외출은 추세 신호이므로 T2 다.
    """
    # 서울 새벽 1시 = 전날 16:00 UTC
    night_utc = MORNING_UTC + 16 * HOUR
    sim = frozen_clock(start=night_utc)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    occupancy_rules.apply_backend_occupancy(SENIOR, "AWAY", observed_at=night_utc)
    runtime_store.save(SENIOR, door_heartbeat_at=night_utc)

    sim.advance(600)
    runtime_store.save(SENIOR, door_heartbeat_at=night_utc + 600)
    ticks.door_watch_tick(SENIOR, None)

    alerts = door_alerts(guardian, "night_exit")
    assert len(alerts) == 1
    # 한 번의 야간 외출은 '추세 신호'다. T1 으로 올리면 오탐이 폭발한다.
    assert alerts[0][0] == "T2"


def test_daytime_exit_is_not_wandering(frozen_clock, guardian):
    """낮에 나간 것은 배회가 아니다. 장보기에 알림이 가면 오탐이 폭발한다."""
    sim = frozen_clock(start=MORNING_UTC)  # 서울 09:00
    context_cache.save(SENIOR, SEOUL_PROFILE)
    occupancy_rules.apply_backend_occupancy(SENIOR, "AWAY", observed_at=MORNING_UTC)
    runtime_store.save(SENIOR, door_heartbeat_at=MORNING_UTC)

    sim.advance(600)
    runtime_store.save(SENIOR, door_heartbeat_at=MORNING_UTC + 600)
    ticks.door_watch_tick(SENIOR, None)

    assert door_alerts(guardian, "night_exit") == []


def test_evening_exit_does_not_become_wandering_after_midnight(frozen_clock, guardian):
    """★ 배회 판정은 부재가 '시작된' 시각으로 한다.

    지금 시각으로 판정하면 저녁 8시에 나간 외출이 자정을 넘기는 순간 배회로 바뀐다.
    """
    # 서울 20:00 = 11:00 UTC
    evening_utc = MORNING_UTC + 11 * HOUR
    sim = frozen_clock(start=evening_utc)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    occupancy_rules.apply_backend_occupancy(SENIOR, "AWAY", observed_at=evening_utc)
    runtime_store.save(SENIOR, door_heartbeat_at=evening_utc)

    # 자정을 넘긴다.
    sim.advance(5 * HOUR)
    runtime_store.save(SENIOR, door_heartbeat_at=evening_utc + 5 * HOUR)
    ticks.door_watch_tick(SENIOR, None)

    assert door_alerts(guardian, "night_exit") == []


def test_door_watch_survives_a_missing_profile(frozen_clock, guardian):
    """문맥 캐시가 비어 있어도 현관 감시는 돌아야 한다.

    프로필이 없으면 시간대를 모르고, 그러면 야간 판정이 UTC 기준이 된다. 그것은
    부정확하지만, 감시를 멈추는 것보다는 낫다 — 프로필이 안 온 어르신에게 안전
    감시가 아예 없는 상태가 더 나쁘다.
    """
    sim = frozen_clock(start=MORNING_UTC)
    occupancy_rules.apply_backend_occupancy(SENIOR, "AWAY", observed_at=MORNING_UTC)
    runtime_store.save(SENIOR, door_heartbeat_at=MORNING_UTC)

    sim.advance(policy.ABSENCE_CONCERN_SEC + 60)
    runtime_store.save(SENIOR, door_heartbeat_at=sim.now())
    ticks.door_watch_tick(SENIOR, None)

    assert len(door_alerts(guardian, "long_absence")) == 1


def test_home_senior_produces_no_door_alerts(frozen_clock, guardian):
    """집에 있는 어르신에 대해 현관 감시는 조용해야 한다."""
    sim = frozen_clock(start=MORNING_UTC)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    occupancy_rules.set_occupancy(SENIOR, "HOME", observed_at=MORNING_UTC, source="speech")
    runtime_store.save(SENIOR, door_heartbeat_at=MORNING_UTC)

    for _ in range(4):
        sim.advance(60)
        runtime_store.save(SENIOR, door_heartbeat_at=sim.now())
        ticks.door_watch_tick(SENIOR, None)

    assert door_alerts(guardian) == []


# ── MQTT 어댑터: 브로커 없이 검증할 수 있는 범위 ──────────────────────────────


def test_broker_url_scheme_decides_tls():
    """★ host/port/tls 를 따로 받지 않는 이유.

    세 값을 따로 받으면 어긋난 조합(8883 인데 평문)이 생기고, 그러면 연결이 조용히
    실패한다. scheme 하나가 세 값을 묶어준다.
    """
    from bomi_ai_chat.door.mqtt import _parse_broker_url

    assert _parse_broker_url("mqtt://jetson.local") == ("jetson.local", 1883, False)
    assert _parse_broker_url("mqtts://broker.example") == ("broker.example", 8883, True)
    # 명시된 포트가 기본값을 덮어쓴다.
    assert _parse_broker_url("mqtts://broker.example:9999") == ("broker.example", 9999, True)
    # scheme 이 없으면 평문으로 본다. 실기에서는 .env 에 명시하게 되어 있다.
    assert _parse_broker_url("jetson.local:1884") == ("jetson.local", 1884, False)


def test_broker_url_rejects_an_unknown_scheme():
    """http:// 를 넣으면 요란하게 실패해야 한다. 조용히 1883 으로 붙지 않는다."""
    from bomi_ai_chat.door.mqtt import _parse_broker_url

    with pytest.raises(ValueError, match="unsupported MQTT scheme"):
        _parse_broker_url("http://broker.example")


def test_mqtt_is_disabled_by_default(settings_factory):
    """브로커가 없는 개발 노트북에서 무한 재연결로 로그를 덮지 않는다."""
    from bomi_ai_chat.door.mqtt import build_door_subscriber

    settings = settings_factory()

    assert settings.mqtt_enabled is False
    assert build_door_subscriber(SENIOR, settings=settings) is None


def test_subscriber_processes_a_raw_broker_payload(frozen_clock, settings_factory):
    """브로커에서 온 bytes 하나가 재실 상태까지 도달한다. 전 경로 확인."""
    from bomi_ai_chat.door.mqtt import DoorSubscriber

    frozen_clock(start=MORNING_UTC)
    client = RecordingDoorClient()
    subscriber = DoorSubscriber(
        SENIOR, settings=settings_factory(), door_client=client)

    accepted = subscriber.handle_payload(json.dumps(envelope("DOOR_OPENED")).encode())

    assert accepted is True
    assert runtime_store.load(SENIOR)["occupancy"] == "UNKNOWN"
    assert len(client.sent) == 1


def test_subscriber_drops_a_bad_message_without_dying(frozen_clock, settings_factory):
    """★ 계약 위반 하나가 구독 루프를 멈추면 현관 감시가 조용히 꺼진다."""
    from bomi_ai_chat.door.mqtt import DoorSubscriber

    frozen_clock(start=MORNING_UTC)
    subscriber = DoorSubscriber(SENIOR, settings=settings_factory())

    assert subscriber.handle_payload(b"not json at all") is False
    assert subscriber.handle_payload(json.dumps(envelope("WHO_KNOWS")).encode()) is False
    # 그 뒤로도 정상 메시지를 계속 처리한다.
    assert subscriber.handle_payload(json.dumps(envelope("HEARTBEAT")).encode()) is True


# ── 그래프 배선 ───────────────────────────────────────────────────────────────


def test_door_event_is_a_terminal_path(tmp_path):
    """★ 문 이벤트는 게이트를 마주하지 않는다.

    door_event 에서 proactive_gate 로 가는 엣지가 되살아나면, 인사 판정이 다시
    로봇으로 돌아온 것이다 (CLAUDE.md §11).
    """
    from langgraph.graph import END

    from bomi_ai_chat.graph.build import build_graph

    graph = build_graph(str(tmp_path / "checkpoint.sqlite")).get_graph()
    targets = {edge.target for edge in graph.edges if edge.source == "door_event"}

    assert targets == {END}


def test_backend_command_skips_the_gate(tmp_path):
    """★ 이미 판정한 쪽에서 온 명령은 게이트를 건너뛰고 인텐트를 유지한다.

    게이트를 거치게 하면 백엔드가 보낸 인사가 로봇의 쿨다운에 조용히 삼켜지고,
    백엔드는 자기가 보낸 인사가 나갔다고 기록한다. classify_intent 는 문서 요청
    순서 때문에 공통 경로에 있지만 이미 붙은 intent 를 바꾸지 않는다.
    """
    from bomi_ai_chat.graph.build import build_graph

    graph = build_graph(str(tmp_path / "checkpoint.sqlite")).get_graph()
    targets = {edge.target for edge in graph.edges if edge.source == "backend_command"}

    assert targets == {"classify_intent"}
    assert not any(
        edge.target == "proactive_gate"
        for edge in graph.edges
        if edge.source == "backend_command"
    )
    assert "proactive_gate" not in targets
