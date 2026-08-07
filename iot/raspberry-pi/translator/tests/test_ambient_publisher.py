import json
from datetime import datetime, timezone

from ambient_publisher import AmbientPublisher


def _now() -> datetime:
    return datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def test_valid_observation_publishes_contract_event() -> None:
    published = []
    publisher = AmbientPublisher(
        "living-room-ambient",
        "LIVING_ROOM",
        lambda topic, payload: published.append((topic, payload)),
        now=_now,
    )

    assert publisher.publish_observation(26, 58) is True
    assert len(published) == 1
    topic, raw = published[0]
    event = json.loads(raw)
    assert topic == "bomi/v1/iot/living-room-ambient/events"
    assert event["type"] == "AMBIENT_ENVIRONMENT_OBSERVED"
    assert event["sourceId"] == "living-room-ambient"
    assert event["occurredAt"] == "2026-08-04T12:00:00+00:00"
    assert event["payload"] == {
        "location": "LIVING_ROOM",
        "temperatureC": 26.0,
        "humidityPercent": 58.0,
    }


def test_invalid_observations_are_not_published() -> None:
    published = []
    publisher = AmbientPublisher("ambient-01", "LIVING_ROOM", lambda *args: published.append(args))

    for temperature, humidity in [
        (float("nan"), 50),
        (25, float("inf")),
        (-1, 50),
        (51, 50),
        (25, 19),
        (25, 91),
        (True, 50),
    ]:
        assert publisher.publish_observation(temperature, humidity) is False

    assert published == []
