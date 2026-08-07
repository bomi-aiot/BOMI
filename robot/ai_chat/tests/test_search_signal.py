"""회전 탐색 UDP 신호 검증 — 실제 소켓으로 왕복시켜 확인한다.

로봇도 마이크도 없이 돈다. 루프백 소켓 하나만 있으면 된다.
"""

import json
import socket

from bomi_ai_chat.search_signal import (
    SearchSignalSender,
    build_search_signal_sender,
    normalize_relative_deg,
)
import pytest


@pytest.fixture()
def receiver():
    """루프백에 묶인 UDP 수신 소켓. wake_search 노드 대역이다."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(1.0)
    yield sock
    sock.close()


def _receive(sock) -> dict:
    data, _address = sock.recvfrom(1024)
    return json.loads(data.decode("utf-8"))


def _sender(sock, **kwargs) -> SearchSignalSender:
    host, port = sock.getsockname()
    return SearchSignalSender(host=host, port=port, **kwargs)


# ── 각도 정규화 ─────────────────────────────────────────────────────────────


def test_normalize_relative_deg_folds_into_half_turn() -> None:
    assert normalize_relative_deg(0.0) == pytest.approx(0.0)
    assert normalize_relative_deg(90.0) == pytest.approx(90.0)
    # 350도 오른쪽은 10도 왼쪽이 아니라 10도 오른쪽이다.
    assert normalize_relative_deg(350.0) == pytest.approx(-10.0)
    assert normalize_relative_deg(-350.0) == pytest.approx(10.0)
    assert normalize_relative_deg(540.0) == pytest.approx(-180.0)


# ── 발신 ────────────────────────────────────────────────────────────────────


def test_send_wake_without_direction_sends_null_angle(receiver) -> None:
    sender = _sender(receiver)
    try:
        assert sender.send_wake() is None
        message = _receive(receiver)
    finally:
        sender.close()

    assert message == {"type": "wake", "azimuth_deg": None}


def test_send_wake_includes_the_direction(receiver) -> None:
    sender = _sender(receiver, direction_provider=lambda: 87.0)
    try:
        assert sender.send_wake() == pytest.approx(87.0)
        message = _receive(receiver)
    finally:
        sender.close()

    assert message["type"] == "wake"
    assert message["azimuth_deg"] == pytest.approx(87.0)


def test_azimuth_sign_flips_the_direction(receiver) -> None:
    # 마이크가 시계 방향으로 각도를 세는 장치면 부호를 뒤집어야 한다.
    sender = _sender(
        receiver, direction_provider=lambda: 87.0, azimuth_sign=-1.0)
    try:
        assert sender.send_wake() == pytest.approx(-87.0)
    finally:
        sender.close()


def test_direction_is_folded_into_the_short_way(receiver) -> None:
    sender = _sender(receiver, direction_provider=lambda: 350.0)
    try:
        # 350도 왼쪽으로 도는 대신 10도 오른쪽으로 돈다.
        assert sender.send_wake() == pytest.approx(-10.0)
    finally:
        sender.close()


def test_send_stop_carries_the_reason(receiver) -> None:
    sender = _sender(receiver)
    try:
        sender.send_stop("user_requested_wait")
        message = _receive(receiver)
    finally:
        sender.close()

    assert message == {"type": "stop", "reason": "user_requested_wait"}


# ── 실패해도 대화를 막지 않는다 ──────────────────────────────────────────────


def test_direction_provider_failure_falls_back_to_no_angle(receiver) -> None:
    def broken() -> float:
        raise RuntimeError("xvf_host not found")

    sender = _sender(receiver, direction_provider=broken)
    try:
        assert sender.send_wake() is None
        message = _receive(receiver)
    finally:
        sender.close()

    # 각도만 빠지고 신호 자체는 나간다 — 로봇은 전체 탐색으로 폴백한다.
    assert message["azimuth_deg"] is None


def test_non_finite_direction_is_dropped(receiver) -> None:
    sender = _sender(receiver, direction_provider=lambda: float("nan"))
    try:
        assert sender.send_wake() is None
    finally:
        sender.close()


def test_non_numeric_direction_is_dropped(receiver) -> None:
    sender = _sender(receiver, direction_provider=lambda: "왼쪽")
    try:
        assert sender.send_wake() is None
    finally:
        sender.close()


def test_close_is_idempotent_and_silences_further_sends(receiver) -> None:
    sender = _sender(receiver)
    sender.close()
    sender.close()
    sender.send_stop("after_close")  # 예외를 올리지 않는다

    receiver.settimeout(0.2)
    with pytest.raises(socket.timeout):
        receiver.recvfrom(1024)


# ── 설정 검증 ───────────────────────────────────────────────────────────────


def test_sender_rejects_bad_port() -> None:
    with pytest.raises(ValueError):
        SearchSignalSender(host="127.0.0.1", port=0)
    with pytest.raises(ValueError):
        SearchSignalSender(host="127.0.0.1", port=70000)


def test_sender_rejects_empty_host() -> None:
    with pytest.raises(ValueError):
        SearchSignalSender(host="  ", port=5006)


# ── 팩터리 ──────────────────────────────────────────────────────────────────


def test_factory_returns_none_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_SIGNAL_ENABLED", "0")
    assert build_search_signal_sender() is None


def test_factory_builds_a_sender_by_default(monkeypatch) -> None:
    monkeypatch.setenv("SEARCH_SIGNAL_ENABLED", "1")
    monkeypatch.setenv("SEARCH_USE_BEAM_DIRECTION", "0")
    sender = build_search_signal_sender()
    try:
        assert sender is not None
    finally:
        if sender is not None:
            sender.close()


def test_factory_skips_direction_when_the_beam_is_fixed(monkeypatch) -> None:
    """빔이 정면에 고정돼 있으면 방향 값이 항상 정면이라 쓸 수 없다."""
    monkeypatch.setenv("SEARCH_SIGNAL_ENABLED", "1")
    monkeypatch.setenv("SEARCH_USE_BEAM_DIRECTION", "1")

    class FixedBeam:
        enabled = True
        front_deg = 90.0

        def read_direction_deg(self) -> float:  # pragma: no cover - 불리면 안 된다
            raise AssertionError("고정된 빔에서 방향을 읽으면 안 된다")

    sender = build_search_signal_sender(FixedBeam())
    try:
        assert sender is not None
        assert sender.send_wake() is None
    finally:
        if sender is not None:
            sender.close()


def test_factory_converts_mic_angle_to_robot_relative(monkeypatch) -> None:
    """마이크 절대 각도를 로봇 정면 기준으로 바꾼다."""
    monkeypatch.setenv("SEARCH_SIGNAL_ENABLED", "1")
    monkeypatch.setenv("SEARCH_USE_BEAM_DIRECTION", "1")

    class TrackingBeam:
        enabled = False
        front_deg = 90.0

        def read_direction_deg(self) -> float:
            return 170.0

    sender = build_search_signal_sender(TrackingBeam())
    try:
        assert sender is not None
        # 마이크 기준 170도, 정면이 90도이므로 로봇 기준 왼쪽 80도.
        assert sender.send_wake() == pytest.approx(80.0)
    finally:
        if sender is not None:
            sender.close()
