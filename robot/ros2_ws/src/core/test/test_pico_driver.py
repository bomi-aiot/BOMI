"""
Pico 드라이버 노드의 순수 헬퍼와 가짜 시리얼을 이용한 생성을 검증한다.

실제 파싱과 변환 로직은 test_pico_protocol.py가 다룬다. 여기서는
정적 메서드와, 가짜 시리얼 포트로 노드 생성·시작 절차·텔레메트리
처리가 실제로 맞물려 도는지를 확인한다.
"""

from collections import deque

import pytest
import rclpy

from core import pico_driver as pico_driver_module
from core.pico_driver import PicoDriver


class FakeSerial:
    """시리얼 핸드셰이크와 읽기·쓰기를 흉내 내는 가짜 포트."""

    def __init__(self, port: str, timeout: float = 0) -> None:
        self.port = port
        self.timeout = timeout
        self.written: list[bytes] = []
        self.closed = False

        self._pending_lines: deque[bytes] = deque(
            [
                b"ACK STOP command\n",
                b"ACK P proto=1 fw=closed_loop_speed\n",
                b"ACK Z\n",
                b"ACK T on\n",
            ]
        )
        self._extra_buffer = b""

    def write(self, data: bytes) -> None:
        self.written.append(data)

    def readline(self) -> bytes:
        if self._pending_lines:
            return self._pending_lines.popleft()

        return b""

    @property
    def in_waiting(self) -> int:
        return len(self._extra_buffer)

    def read(self, size: int) -> bytes:
        data = self._extra_buffer[:size]
        self._extra_buffer = self._extra_buffer[size:]

        return data

    def feed_line(self, line: str) -> None:
        """다음 in_waiting/read 호출에서 읽힐 텔레메트리 줄을 채운다."""
        self._extra_buffer += (line + "\n").encode("ascii")

    def reset_input_buffer(self) -> None:
        """대기 중이던 잔여 바이트를 비운다."""
        self._extra_buffer = b""

    def reset_output_buffer(self) -> None:
        """보내다 만 바이트를 비운다. 재시도 사이에 불린다."""

    def close(self) -> None:
        self.closed = True


class SilentThenReadySerial(FakeSerial):
    """처음 몇 번은 아무 응답도 하지 않다가 그 뒤에 정상 응답하는 포트.

    젯슨 부팅 직후 Pico가 아직 명령을 받지 못하는 상태를 흉내 낸다.
    """

    def __init__(self, port: str, timeout: float = 0, silent: int = 1) -> None:
        super().__init__(port, timeout)
        self._silent_attempts_left = silent
        self._ready_lines = deque(self._pending_lines)
        self._pending_lines = deque()

    def write(self, data: bytes) -> None:
        super().write(data)

        # 'S'는 매 시도의 첫 명령이다. 조용할 횟수를 다 쓰면 그때부터
        # 정상 응답을 내놓는다.
        if data == b"S\n":
            if self._silent_attempts_left > 0:
                self._silent_attempts_left -= 1
            else:
                self._pending_lines = deque(self._ready_lines)


NO_RETRY_DELAY_OVERRIDE = rclpy.parameter.Parameter(
    "startup_retry_delay_sec",
    rclpy.parameter.Parameter.Type.DOUBLE,
    0.0,
)


FAST_STARTUP_OVERRIDE = rclpy.parameter.Parameter(
    "startup_response_timeout_sec",
    rclpy.parameter.Parameter.Type.DOUBLE,
    0.2,
)


@pytest.fixture()
def pico_driver_node(monkeypatch):
    """
    가짜 시리얼로 PicoDriver를 생성하고 테스트 후 정리한다.

    테스트마다 독립된 rclpy Context를 써서 전역 컨텍스트 상태가
    테스트 사이에 번지지 않게 한다.
    """
    fake_serial = FakeSerial("/dev/ttyACM0")

    monkeypatch.setattr(
        pico_driver_module.serial,
        "Serial",
        lambda port, timeout: fake_serial,
    )

    context = rclpy.Context()
    rclpy.init(context=context)
    node = PicoDriver(
        context=context,
        parameter_overrides=[FAST_STARTUP_OVERRIDE],
    )

    try:
        yield node, fake_serial
    finally:
        node.destroy_node()
        rclpy.shutdown(context=context)


def test_pico_driver_runs_startup_sequence(pico_driver_node) -> None:
    """생성 시 빈 줄로 버퍼를 끊고 S, P, Z, T 1 순서로 명령을 보낸다."""
    _node, fake_serial = pico_driver_node

    assert fake_serial.written[0] == b"\n"
    assert fake_serial.written[1] == b"S\n"
    assert fake_serial.written[2] == b"P\n"
    assert fake_serial.written[3] == b"Z\n"
    assert fake_serial.written[4] == b"T 1\n"


def test_pico_driver_clears_partial_command_before_handshake(
    pico_driver_node,
) -> None:
    """'S' 앞에 빈 줄이 나가야 앞 세션이 남긴 명령 조각이 끊긴다.

    2026-08-07 리허설 회귀: 조각에 'S'가 이어붙어 Pico가
    'ERR usage: T <0|1>'로 답하고 ACK를 주지 않았다.
    """
    _node, fake_serial = pico_driver_node

    assert fake_serial.written.index(b"\n") < fake_serial.written.index(b"S\n")


def test_pico_driver_integrates_odometry_from_telemetry(
    pico_driver_node,
) -> None:
    """텔레메트리 두 줄을 받으면 카운트 차분만큼 위치가 이동한다."""
    node, _fake_serial = pico_driver_node

    first_line = (
        "T 0 0.0 0.0 0.0 0.0 "
        "1000 1000 1000 1000 0.0 0.0 "
        "0.0 0.0 0.0 0x01"
    )
    second_line = (
        "T 20 0.5 0.5 0.5 0.5 "
        "1100 1100 1100 1100 30.0 30.0 "
        "0.0 0.0 0.0 0x03"
    )

    node._handle_incoming_line(first_line)

    assert node._x_m == pytest.approx(0.0)
    assert node._y_m == pytest.approx(0.0)

    node._handle_incoming_line(second_line)

    expected_distance_m = (100 / 979) * 0.1929

    assert node._x_m == pytest.approx(expected_distance_m)
    assert node._y_m == pytest.approx(0.0, abs=1e-9)


def test_pico_driver_rate_limits_velocity_commands(pico_driver_node) -> None:
    """
    제어 주기마다 읽되 V 명령은 command_hz로 제한해서 보낸다.

    펌웨어는 메인 루프 한 바퀴에 문자 하나만 읽으므로, 전송이 잦으면
    USB 버퍼에 명령이 쌓여 조작 지연이 누적된다.
    """
    node, fake_serial = pico_driver_node

    for _ in range(5):
        node._on_control_tick()

    sent = [line for line in fake_serial.written if line.startswith(b"V ")]

    assert len(sent) == 1


def test_pico_driver_rejects_command_rate_above_control_rate(
    monkeypatch,
) -> None:
    """읽기 주기보다 빠른 전송 주기는 거부한다."""
    fake_serial = FakeSerial("/dev/ttyACM0")

    monkeypatch.setattr(
        pico_driver_module.serial,
        "Serial",
        lambda port, timeout: fake_serial,
    )

    context = rclpy.Context()
    rclpy.init(context=context)

    try:
        with pytest.raises(ValueError):
            PicoDriver(
                context=context,
                parameter_overrides=[
                    FAST_STARTUP_OVERRIDE,
                    rclpy.parameter.Parameter(
                        "control_hz",
                        rclpy.parameter.Parameter.Type.DOUBLE,
                        20.0,
                    ),
                    rclpy.parameter.Parameter(
                        "command_hz",
                        rclpy.parameter.Parameter.Type.DOUBLE,
                        50.0,
                    ),
                ],
            )
    finally:
        rclpy.shutdown(context=context)


def test_pico_driver_rejects_wrong_protocol_version(monkeypatch) -> None:
    """proto가 1이 아니면 노드 생성이 실패하고 포트를 닫는다."""
    fake_serial = FakeSerial("/dev/ttyACM0")
    fake_serial._pending_lines = deque(
        [
            b"ACK STOP command\n",
            b"ACK P proto=2 fw=closed_loop_speed\n",
        ]
    )

    monkeypatch.setattr(
        pico_driver_module.serial,
        "Serial",
        lambda port, timeout: fake_serial,
    )

    context = rclpy.Context()
    rclpy.init(context=context)

    try:
        with pytest.raises(RuntimeError):
            PicoDriver(
                context=context,
                parameter_overrides=[FAST_STARTUP_OVERRIDE],
            )

        assert fake_serial.closed is True
    finally:
        rclpy.shutdown(context=context)


def test_pico_driver_retries_handshake_until_pico_answers(monkeypatch) -> None:
    """첫 시도에 Pico가 조용해도 다시 걸어 노드를 살려낸다.

    2026-08-07 리허설 회귀: 부팅 직후 첫 'S'가 흘려져 이 노드만 죽었고,
    나머지 스택은 정상으로 보이는 채 /cmd_vel 구독자만 사라졌다.
    """
    fake_serial = SilentThenReadySerial("/dev/ttyACM0", silent=2)

    monkeypatch.setattr(
        pico_driver_module.serial,
        "Serial",
        lambda port, timeout: fake_serial,
    )

    context = rclpy.Context()
    rclpy.init(context=context)
    node = None

    try:
        node = PicoDriver(
            context=context,
            parameter_overrides=[
                FAST_STARTUP_OVERRIDE,
                NO_RETRY_DELAY_OVERRIDE,
            ],
        )

        # 조용한 2번 + 성공한 1번 = 'S' 세 번.
        assert fake_serial.written.count(b"S\n") == 3
        assert fake_serial.closed is False
        assert fake_serial.written[-4:] == [b"S\n", b"P\n", b"Z\n", b"T 1\n"]
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown(context=context)


def test_pico_driver_gives_up_after_configured_attempts(monkeypatch) -> None:
    """끝내 응답이 없으면 시도 횟수를 다 쓰고 포트를 닫으며 실패한다."""
    fake_serial = SilentThenReadySerial("/dev/ttyACM0", silent=99)

    monkeypatch.setattr(
        pico_driver_module.serial,
        "Serial",
        lambda port, timeout: fake_serial,
    )

    context = rclpy.Context()
    rclpy.init(context=context)

    try:
        with pytest.raises(TimeoutError):
            PicoDriver(
                context=context,
                parameter_overrides=[
                    FAST_STARTUP_OVERRIDE,
                    NO_RETRY_DELAY_OVERRIDE,
                    rclpy.parameter.Parameter(
                        "startup_attempts",
                        rclpy.parameter.Parameter.Type.INTEGER,
                        3,
                    ),
                ],
            )

        assert fake_serial.written.count(b"S\n") == 3
        assert fake_serial.closed is True
    finally:
        rclpy.shutdown(context=context)


def test_pico_driver_does_not_retry_protocol_mismatch(monkeypatch) -> None:
    """버전 불일치는 기다려도 낫지 않으므로 다시 시도하지 않는다."""
    fake_serial = FakeSerial("/dev/ttyACM0")
    fake_serial._pending_lines = deque(
        [
            b"ACK STOP command\n",
            b"ACK P proto=2 fw=closed_loop_speed\n",
        ]
    )

    monkeypatch.setattr(
        pico_driver_module.serial,
        "Serial",
        lambda port, timeout: fake_serial,
    )

    context = rclpy.Context()
    rclpy.init(context=context)

    try:
        with pytest.raises(RuntimeError):
            PicoDriver(
                context=context,
                parameter_overrides=[
                    FAST_STARTUP_OVERRIDE,
                    NO_RETRY_DELAY_OVERRIDE,
                ],
            )

        assert fake_serial.written.count(b"S\n") == 1
    finally:
        rclpy.shutdown(context=context)


def test_is_positive_finite_accepts_positive_values() -> None:
    """유한한 양수는 참으로 판정한다."""
    assert PicoDriver._is_positive_finite(0.5) is True
    assert PicoDriver._is_positive_finite(1.0) is True


def test_is_positive_finite_rejects_zero_and_negative() -> None:
    """0과 음수는 거짓으로 판정한다."""
    assert PicoDriver._is_positive_finite(0.0) is False
    assert PicoDriver._is_positive_finite(-1.0) is False


def test_is_positive_finite_rejects_nan_and_inf() -> None:
    """NaN과 무한대는 거짓으로 판정한다."""
    assert PicoDriver._is_positive_finite(float("nan")) is False
    assert PicoDriver._is_positive_finite(float("inf")) is False


def test_diagonal_covariance_places_values_on_diagonal() -> None:
    """대각값 목록을 6x6 공분산 행렬의 대각선에만 채운다."""
    matrix = PicoDriver._diagonal_covariance(
        [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        size=6,
    )

    assert len(matrix) == 36

    for row in range(6):
        for column in range(6):
            index = row * 6 + column

            if row == column:
                assert matrix[index] == pytest.approx(row + 1.0)
            else:
                assert matrix[index] == 0.0


def test_parse_proto_version_reads_proto_field() -> None:
    """'ACK P proto=1 fw=...' 응답에서 버전 숫자를 뽑는다."""
    version = PicoDriver._parse_proto_version(
        "ACK P proto=1 fw=closed_loop_speed"
    )

    assert version == 1


def test_parse_proto_version_rejects_missing_field() -> None:
    """응답에 proto 필드가 없으면 ValueError를 낸다."""
    with pytest.raises(ValueError):
        PicoDriver._parse_proto_version("ACK P fw=closed_loop_speed")
