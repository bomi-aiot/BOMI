"""디스플레이 상태와 우선순위를 ROS 2 및 UI와 독립적으로 관리한다."""

from dataclasses import dataclass
from enum import Enum
import time


class FaceState(str, Enum):
    """LCD에 표현할 로봇의 대표 상태."""

    IDLE = "IDLE"
    DRIVING = "DRIVING"
    FOLLOWING = "FOLLOWING"
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
    # 추종은 Nav2 주행과 다른 경로(person_follower)라 따로 본다. 사용자 눈에는
    # "이동 중"과 "따라오는 중"이 전혀 다른 행동이다.
    FOLLOWING_NAV_STATES = frozenset({"FOLLOWING", "FOLLOW", "TRACKING"})
    LISTENING_TTS_STATES = frozenset({"LISTENING", "RECOGNIZING"})
    # 사용자 말이 끝나고 응답이 나오기 전 구간. 이게 없으면 그 몇 초 동안
    # 화면이 "듣는 중"으로 남아 로봇이 멈춘 것처럼 보인다.
    THINKING_TTS_STATES = frozenset({"THINKING", "PROCESSING", "GENERATING"})
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
        """오류, 발화, 주행, 대화, 잔여 움직임, 대기 순서로 화면을 결정한다.

        ★ 주행을 '두 단계'로 나눠 보는 이유 (2026-08-10)
            원래는 TTS 상태(듣기·생각하기)가 주행보다 항상 먼저였다. 그런데
            "보미야" 대본은 백엔드가 NAVIGATE(LIVING_ROOM) 를 함께 유발하므로
            로봇이 굴러가는 동안 ai_chat 이 마이크를 열고 STT 를 돌린다. 그
            몇 초 내내 화면에 "생각하는 중"이 떴다 — 어르신 눈에는 로봇이
            다가오고 있는데 화면은 딴소리를 하는 상태였다.

            그렇다고 움직임을 무조건 위로 올리면 반대 사고가 난다. 대화 중에도
            사람 추종이 바퀴를 조금씩 굴리는데, 그때마다 "듣고 있어요"가
            "이동 중"으로 덮여 말을 걸기 어려워진다.

            그래서 둘을 갈랐다.
              nav_state ACTIVE   진짜 Nav2 목표를 수행 중이다(bridge 가
                                 발행한다). 대화 표시보다 **위**다.
              motion_active_until  /cmd_vel 이 잠깐 움직였을 뿐이다. 추종의
                                 미세 보정이 여기 걸리므로 대화 표시보다
                                 **아래**에 둔다.
        """
        current = time.monotonic() if now is None else now
        if not self.mqtt_connected:
            return DisplaySnapshot(FaceState.ERROR, "연결 오류", "MQTT 연결 끊김")
        if self._sensor_is_stale(current):
            return DisplaySnapshot(FaceState.ERROR, "센서 확인", "센서 데이터 만료")
        if self.nav_state in self.FAILED_NAV_STATES:
            return DisplaySnapshot(FaceState.ERROR, "주행 오류", self.nav_state)
        if self.tts_state in self.FAILED_TTS_STATES:
            return DisplaySnapshot(FaceState.ERROR, "음성 오류", self.tts_state)
        # 발화는 주행보다도 위다. 짧고, 말이 나오는 동안 화면이 딴 것을
        # 가리키면 누가 말하는지 알 수 없다(현관 "야호"가 이동 중에 나온다).
        if self.tts_state in self.SPEAKING_TTS_STATES:
            return DisplaySnapshot(FaceState.SPEAKING, "말하는 중")
        # 추종을 주행보다 먼저 본다. 추종 중에도 바퀴가 도니 두 조건이 함께
        # 참일 수 있는데, 그때 보여줄 것은 "따라가는 중"이다.
        if self.nav_state in self.FOLLOWING_NAV_STATES:
            return DisplaySnapshot(FaceState.FOLLOWING, "따라가는 중")
        # 진짜 Nav2 주행. 대화 표시보다 위다(위 주석 참고).
        if self.nav_state in self.ACTIVE_NAV_STATES:
            return DisplaySnapshot(FaceState.DRIVING, "이동 중")
        if self.tts_state in self.THINKING_TTS_STATES:
            return DisplaySnapshot(FaceState.THINKING, "생각하는 중")
        if self.tts_state in self.LISTENING_TTS_STATES:
            return DisplaySnapshot(FaceState.LISTENING, "듣고 있어요")
        # 목표 없이 바퀴만 도는 경우(추종 미세 보정, 조이스틱). 대화 표시를
        # 덮지 않도록 맨 아래에 둔다.
        if current < self.motion_active_until:
            return DisplaySnapshot(FaceState.DRIVING, "이동 중")
        return DisplaySnapshot(FaceState.IDLE, "기다리고 있어요")

    def _sensor_is_stale(self, now: float) -> bool:
        """감시 중인 센서의 마지막 데이터가 제한 시간을 넘었는지 반환한다."""
        return (
            self.sensor_monitoring_enabled
            and self.last_sensor_update is not None
            and now - self.last_sensor_update > self.sensor_timeout_seconds
        )
