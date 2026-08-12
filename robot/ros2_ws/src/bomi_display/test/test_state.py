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


def test_nav2_driving_beats_thinking():
    """★ 2026-08-10 회귀 방지.

    "보미야" 대본은 백엔드가 NAVIGATE(LIVING_ROOM) 를 함께 유발하므로 로봇이
    굴러가는 동안 ai_chat 이 마이크를 열고 STT 를 돌린다. 그때 화면에
    "생각하는 중"이 떠서, 다가오는 로봇을 보는 어르신에게 딴소리를 했다.
    진짜 Nav2 목표가 있는 동안은 이동 표시가 이긴다.
    """
    model = DisplayStateModel()
    model.update_nav("NAVIGATING")
    model.update_tts("THINKING")

    snapshot = model.snapshot(now=0.0)
    assert snapshot.state == FaceState.DRIVING
    assert snapshot.title == "이동 중"


def test_nav2_driving_beats_listening():
    """이동 중에 마이크가 열려 있어도 화면은 '이동 중'이다."""
    model = DisplayStateModel()
    model.update_nav("NAVIGATING")
    model.update_tts("LISTENING")

    assert model.snapshot(now=0.0).state == FaceState.DRIVING


def test_speaking_still_beats_nav2_driving():
    """발화는 이동보다도 위다 — 현관 '야호'가 이동 중에 나온다."""
    model = DisplayStateModel()
    model.update_nav("NAVIGATING")
    model.update_tts("SPEAKING")

    assert model.snapshot(now=0.0).state == FaceState.SPEAKING


def test_incidental_motion_does_not_cover_the_conversation():
    """목표 없이 바퀴만 도는 것(추종 미세 보정)은 대화 표시를 덮지 않는다.

    이걸 덮게 두면 반대 사고가 난다 — 대화 중 추종이 조금씩 바퀴를 굴릴
    때마다 "듣고 있어요"가 "이동 중"으로 바뀌어 말을 걸기 어려워진다.
    """
    model = DisplayStateModel()
    model.update_motion(True, now=0.0)
    model.update_tts("LISTENING")

    assert model.snapshot(now=0.1).state == FaceState.LISTENING


def test_incidental_motion_still_shows_driving_when_idle():
    """대화가 없을 때는 바퀴 움직임만으로도 '이동 중'을 보여준다."""
    model = DisplayStateModel()
    model.update_motion(True, now=0.0)

    assert model.snapshot(now=0.1).state == FaceState.DRIVING


def test_following_beats_nav2_driving():
    """추종 중에는 '따라가는 중'이다 — 두 조건이 함께 참일 수 있다."""
    model = DisplayStateModel()
    model.update_nav("FOLLOWING")

    assert model.snapshot(now=0.0).state == FaceState.FOLLOWING
