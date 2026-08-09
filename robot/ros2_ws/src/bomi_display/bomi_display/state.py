"""디스플레이 상태와 우선순위를 ROS 2 및 UI와 독립적으로 관리한다."""

from dataclasses import dataclass
from enum import Enum
import time


class FaceState(str, Enum):
    """LCD에 표현할 로봇의 대표 상태."""

    IDLE = "IDLE"
    DRIVING = "DRIVING"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class DisplaySnapshot:
    """한 프레임에 표시할 상태와 안내 문구를 보관한다."""

    state: FaceState
    title: str
    detail: str = ""


class DisplayStateModel:
    """Nav2, TTS, MQTT, 센서 입력을 하나의 화면 상태로 합성한다."""

    ACTIVE_NAV_STATES = frozenset({"NAVIGATING", "DRIVING", "MOVING", "ACTIVE"})
    FAILED_NAV_STATES = frozenset({"FAILED", "ABORTED", "ERROR"})
    LISTENING_TTS_STATES = frozenset({"LISTENING", "RECOGNIZING"})
    THINKING_TTS_STATES = frozenset({"THINKING", "PROCESSING"})
    SPEAKING_TTS_STATES = frozenset({"SPEAKING", "PLAYING"})
    FAILED_TTS_STATES = frozenset({"FAILED", "ERROR"})

    def __init__(self, sensor_timeout_seconds: float = 3.0) -> None:
        """센서 만료 시간을 검증하고 초기 대기 상태를 만든다."""
        if sensor_timeout_seconds <= 0.0:
            raise ValueError("sensor_timeout_seconds는 0보다 커야 합니다")
        self.sensor_timeout_seconds = sensor_timeout_seconds
        self.nav_state = "IDLE"
        self.tts_state = "IDLE"
        self.mqtt_connected = True
        self.last_sensor_update: float | None = None
        self.sensor_monitoring_enabled = False
        self.motion_active_until = 0.0

    def update_nav(self, value: str) -> None:
        """Nav2 상태 문자열을 정규화하여 저장한다."""
        self.nav_state = value.strip().upper()

    def update_tts(self, value: str) -> None:
        """음성 인식 또는 TTS 상태 문자열을 정규화하여 저장한다."""
        self.tts_state = value.strip().upper()

    def update_motion(
        self, moving: bool, now: float | None = None, hold_seconds: float = 0.7
    ) -> None:
        """실제 속도 명령을 짧게 유지해 이동 여부로 반영한다."""
        current = time.monotonic() if now is None else now
        self.motion_active_until = current + hold_seconds if moving else current

    def update_mqtt(self, connected: bool) -> None:
        """MQTT 연결 여부를 저장한다."""
        self.mqtt_connected = bool(connected)

    def mark_sensor_update(self, now: float | None = None) -> None:
        """센서 데이터를 받은 시각을 기록하고 만료 감시를 시작한다."""
        self.last_sensor_update = time.monotonic() if now is None else now
        self.sensor_monitoring_enabled = True

    def snapshot(self, now: float | None = None) -> DisplaySnapshot:
        """오류, 발화, 듣기, 주행, 대기 순서로 현재 화면 상태를 결정한다."""
        current = time.monotonic() if now is None else now
        if not self.mqtt_connected:
            return DisplaySnapshot(FaceState.ERROR, "연결 오류", "MQTT 연결 끊김")
        if self._sensor_is_stale(current):
            return DisplaySnapshot(FaceState.ERROR, "센서 확인", "센서 데이터 만료")
        if self.nav_state in self.FAILED_NAV_STATES:
            return DisplaySnapshot(FaceState.ERROR, "주행 오류", self.nav_state)
        if self.tts_state in self.FAILED_TTS_STATES:
            return DisplaySnapshot(FaceState.ERROR, "음성 오류", self.tts_state)
        if self.tts_state in self.SPEAKING_TTS_STATES:
            return DisplaySnapshot(FaceState.SPEAKING, "말하는 중")
        if self.tts_state in self.THINKING_TTS_STATES:
            return DisplaySnapshot(FaceState.THINKING, "생각하는 중")
        if self.tts_state in self.LISTENING_TTS_STATES:
            return DisplaySnapshot(FaceState.LISTENING, "듣고 있어요")
        if self.nav_state in self.ACTIVE_NAV_STATES or current < self.motion_active_until:
            return DisplaySnapshot(FaceState.DRIVING, "이동 중")
        return DisplaySnapshot(FaceState.IDLE, "기다리고 있어요")

    def _sensor_is_stale(self, now: float) -> bool:
        """감시 중인 센서의 마지막 데이터가 제한 시간을 넘었는지 반환한다."""
        return (
            self.sensor_monitoring_enabled
            and self.last_sensor_update is not None
            and now - self.last_sensor_update > self.sensor_timeout_seconds
        )
