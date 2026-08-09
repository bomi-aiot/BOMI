"""디스플레이 상태 합성 규칙을 검증한다."""

import pytest

from bomi_display.state import DisplayStateModel, FaceState


def test_default_state_is_idle():
    """입력이 없으면 대기 상태를 표시한다."""
    assert DisplayStateModel().snapshot(now=0.0).state == FaceState.IDLE


@pytest.mark.parametrize(
    ("source", "value", "expected"),
    [
        ("nav", "navigating", FaceState.DRIVING),
        ("tts", "listening", FaceState.LISTENING),
        ("tts", "thinking", FaceState.THINKING),
        ("tts", "speaking", FaceState.SPEAKING),
    ],
)
def test_activity_states(source, value, expected):
    """Nav2와 음성 상태를 지정된 표정으로 변환한다."""
    model = DisplayStateModel()
    getattr(model, f"update_{source}")(value)
    assert model.snapshot(now=0.0).state == expected


def test_speaking_has_priority_over_driving():
    """주행 중 발화하면 발화 표정을 우선한다."""
    model = DisplayStateModel()
    model.update_nav("NAVIGATING")
    model.update_tts("SPEAKING")
    assert model.snapshot(now=0.0).state == FaceState.SPEAKING


def test_recent_nonzero_velocity_is_driving_then_expires():
    """실제 속도 명령이 들어오면 이동 상태가 되고 잠시 뒤 대기로 돌아간다."""
    model = DisplayStateModel()
    model.update_motion(True, now=10.0, hold_seconds=0.7)
    assert model.snapshot(now=10.6).state == FaceState.DRIVING
    assert model.snapshot(now=10.8).state == FaceState.IDLE


def test_disconnected_mqtt_has_error_priority():
    """MQTT 연결이 끊기면 다른 동작보다 오류를 우선한다."""
    model = DisplayStateModel()
    model.update_tts("SPEAKING")
    model.update_mqtt(False)
    snapshot = model.snapshot(now=0.0)
    assert snapshot.state == FaceState.ERROR
    assert snapshot.detail == "MQTT 연결 끊김"


def test_sensor_becomes_stale_after_timeout():
    """첫 센서 신호 이후 제한 시간 동안 갱신되지 않으면 오류로 전환한다."""
    model = DisplayStateModel(sensor_timeout_seconds=3.0)
    model.mark_sensor_update(now=10.0)
    assert model.snapshot(now=12.9).state == FaceState.IDLE
    assert model.snapshot(now=13.1).detail == "센서 데이터 만료"


def test_sensor_is_not_assumed_present_before_first_message():
    """사용하지 않는 센서가 시작 직후 오류를 만들지 않는다."""
    model = DisplayStateModel(sensor_timeout_seconds=3.0)
    assert model.snapshot(now=100.0).state == FaceState.IDLE


def test_invalid_timeout_is_rejected():
    """0 이하의 센서 만료 시간은 거부한다."""
    with pytest.raises(ValueError):
        DisplayStateModel(sensor_timeout_seconds=0.0)
