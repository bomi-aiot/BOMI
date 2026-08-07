"""Nav2 없이 "정해진 시간만큼 직진"으로 NAVIGATE 를 대체하는 임시 드라이버.

왜 있는가
    시연 준비에서 지도 작성(SLAM)과 좌표 실측이 병목이다. 그런데 Nav2 가
    없으면 NAVIGATE 가 전부 실패로 회신되고, 그 뒤에 이어지는 것들 — 백엔드
    시나리오 종결, START_CONVERSATION 왕복, 대화, 복귀, DB COMPLETED — 을
    **하나도** 검증할 수 없다. 실패 결과 하나가 로봇을 SAFE_STOP 으로 잠그기
    때문에 더더욱 그렇다(CLAUDE.md §3).

    그래서 "목적지로 정확히 간다"를 포기하고 "명령을 받으면 실제로 바퀴가
    돌고 ARRIVED 를 회신한다"만 남긴다. 배선·계약·대화·DB 는 전부 진짜로
    검증되고, 오직 주행 품질만 가짜다. Nav2 가 준비되면 driver_type 만
    ``nav2`` 로 바꾸면 된다 — 이 파일은 지우면 그만이다.

무엇을 보장하지 않는가
    목적지 구분이 없다. ENTRANCE 든 LIVING_ROOM 이든 DEFAULT 든 똑같이
    "2초 직진"이다. 위치가 맞을 리 없으므로 **실주행 리허설의 근거로 쓰면
    안 된다.** 계약 왕복과 대화 흐름 검증 전용이다.

안전 (이 파일에서 가장 중요한 부분)
    * Pico 워치독이 300ms 다. 그래서 주행 중에는 ``tick_sec``(기본 0.1초)
      간격으로 속도를 **계속** 발행한다. 한 번만 발행하고 기다리면 300ms 뒤
      Pico 가 스스로 멈춰서 "2초 직진"이 "0.3초 직진"이 된다.
    * 어떤 경로로 끝나든(정상 종료·취소·예외) ``finally`` 에서 정지(0)를
      발행한다. 이 보장이 깨지면 로봇이 명령 없이 계속 굴러간다.
    * 기본 속도는 0.08 m/s 로 매우 느리다. 받침대 검증(V3)을 먼저 하라는
      전제이며, 바닥에서 올릴 때도 이 값부터 시작한다
      (``robot/docs/robot-joystick-slam.md``).

스레드 모델
    ``navigate()`` 는 브릿지의 **워커 스레드**에서, ``cancel()`` 은 **수신
    (paho 콜백) 스레드**에서 불린다(Nav2 드라이버와 동일). 그래서 취소는
    ``threading.Event`` 하나로 주고받는다 — cancel() 은 이벤트만 세우고
    즉시 돌아오고, 주행 루프가 그것을 보고 멈춘 뒤 정지를 발행한다.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from bridge import contract
from bridge.robot_driver import RobotDriver

#: 한 번의 NAVIGATE 가 직진하는 시간(초). "2초 직진"의 그 2초.
DEFAULT_DRIVE_DURATION_SEC = 2.0

#: 직진 속도(m/s). 받침대에서 시작하는 안전한 값.
DEFAULT_LINEAR_SPEED = 0.08

#: 속도 재발행 간격(초). Pico 워치독 300ms 보다 반드시 작아야 한다.
DEFAULT_TICK_SEC = 0.1

#: tick_sec 이 이 값을 넘으면 Pico 가 주행 중에 스스로 멈춘다.
_PICO_WATCHDOG_SEC = 0.3


class TimedDriveRobotDriver(RobotDriver):
    """NAVIGATE 를 "정해진 시간 직진"으로 실행하는 임시 드라이버.

    역할: 목적지를 무시하고 duration_sec 동안 linear_speed 로 직진한 뒤
        ARRIVED 를 반환한다. 주행 중 cancel() 이 오면 즉시 멈추고 CANCELLED.
    입력값(생성자): publish_velocity - 선속도(m/s) 하나를 받아 로봇에
        발행하는 함수(ROS 2 노드가 Twist 발행자를 감싸 주입한다).
        duration_sec/linear_speed/tick_sec - 위 상수 참고. logger - 선택,
        ROS 2 로거 호환 객체. monotonic/sleep - 테스트용 시간 주입.
    """

    def __init__(
        self,
        publish_velocity: Callable[[float], None],
        *,
        duration_sec: float = DEFAULT_DRIVE_DURATION_SEC,
        linear_speed: float = DEFAULT_LINEAR_SPEED,
        tick_sec: float = DEFAULT_TICK_SEC,
        logger: Any | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if duration_sec <= 0.0:
            raise ValueError("duration_sec must be a positive number of seconds")
        if tick_sec <= 0.0:
            raise ValueError("tick_sec must be a positive number of seconds")
        if tick_sec >= _PICO_WATCHDOG_SEC:
            # 조용히 허용하면 "2초 직진"이 워치독 때문에 0.3초로 잘린다.
            # 설정 실수를 실행 시점에 잡는다.
            raise ValueError(
                f"tick_sec must stay under the Pico watchdog "
                f"({_PICO_WATCHDOG_SEC}s); got {tick_sec}s"
            )

        self._publish_velocity = publish_velocity
        self._duration_sec = float(duration_sec)
        self._linear_speed = float(linear_speed)
        self._tick_sec = float(tick_sec)
        self._logger = logger
        self._monotonic = monotonic
        self._sleep = sleep

        # 수신 스레드가 세우고 워커 스레드가 읽는다.
        self._cancel_requested = threading.Event()

        # 브릿지가 실패 결과의 reasonCode 로 읽어 가는 값(선택 규약).
        self.last_reason_code: str | None = None

    # ── RobotDriver 인터페이스 ────────────────────────────────────────────

    def navigate(self, target: str) -> str:
        """duration_sec 동안 직진하고 ARRIVED 를 반환한다.

        목적지는 유효성만 검사하고 이동에는 반영하지 않는다. 알 수 없는
        목적지까지 성공으로 돌려주면 백엔드가 존재하지 않는 곳에 "도착했다"는
        거짓을 받게 되므로, 그 판정만은 실물과 같게 유지한다.
        """
        self.last_reason_code = None

        if target not in contract.NAVIGATION_TARGETS:
            self._log("warning", f"Unsupported navigation target '{target}'")
            self.last_reason_code = contract.REASON_UNKNOWN_TARGET
            return contract.STATUS_FAILED

        # 이전 명령이 남긴 취소 요청을 물려받지 않는다.
        self._cancel_requested.clear()

        self._log(
            "info",
            f"[timed-drive] '{target}' -> driving forward "
            f"{self._duration_sec}s at {self._linear_speed} m/s "
            "(NOT a real navigation)",
        )

        try:
            cancelled = self._drive_forward()
        except Exception as error:
            self._log("error", f"[timed-drive] driving failed: {error}")
            self.last_reason_code = contract.REASON_INTERNAL_ERROR
            return contract.STATUS_FAILED

        if cancelled:
            self._log("info", "[timed-drive] cancelled while driving")
            return contract.STATUS_CANCELLED

        return contract.STATUS_ARRIVED

    def speak(self, text: str) -> str:
        """발화 수단이 없으므로 FAILED 를 반환한다.

        가짜 성공(DONE)을 돌려주지 않는다. 백엔드는 SPEAK 를 발행하지 않으므로
        (CLAUDE.md §1) 실제로 여기에 올 일은 없다.
        """
        self._log("warning", "[timed-drive] speak is not supported")
        self.last_reason_code = contract.REASON_INTERNAL_ERROR
        return contract.STATUS_FAILED

    def cancel(self) -> str:
        """주행 중이면 멈추라고 표시하고 즉시 반환한다.

        ★ 수신 스레드에서 불린다. 여기서 직접 정지를 발행하지 않는 이유는,
        주행 루프가 매 tick 속도를 재발행하고 있어서 두 스레드가 같은
        발행자를 두드리면 정지 뒤에 주행 명령이 한 번 더 나갈 수 있기
        때문이다. 정지 발행은 주행 루프의 finally 가 단독으로 책임진다.

        알려진 창: navigate() 는 진입 시 취소 상태를 지우므로, **워커가
        NAVIGATE 를 집어 들기 직전에 도착한 CANCEL 은 유실된다.** 지우지
        않으면 반대로 예전 취소가 다음 명령을 영구히 막는다. Nav2 드라이버도
        같은 선택을 한다(진행 중 목표가 없으면 취소는 무동작) — 두 드라이버의
        의미를 일부러 맞춰 둔 것이다.
        """
        self._cancel_requested.set()
        return contract.STATUS_CANCELLED

    def shutdown(self) -> None:
        """종료 시 확실히 멈춘다.

        주행 중에 노드가 죽으면 마지막 속도 명령이 그대로 남는다(Pico
        워치독이 300ms 뒤 멈추긴 하지만, 명시적으로 0을 보내는 편이 안전하다).
        """
        self._cancel_requested.set()
        try:
            self._publish_velocity(0.0)
        except Exception as error:
            self._log("warning", f"[timed-drive] failed to publish stop: {error}")

    # ── 내부 ──────────────────────────────────────────────────────────────

    def _drive_forward(self) -> bool:
        """duration_sec 동안 직진한다. 취소로 끝났으면 True 를 반환한다.

        정지 발행은 어떤 경로로 빠져나가든 finally 에서 한 번 한다 — 이
        보장이 이 클래스에서 가장 중요하다.
        """
        deadline = self._monotonic() + self._duration_sec
        cancelled = False
        try:
            while True:
                if self._cancel_requested.is_set():
                    cancelled = True
                    break
                remaining = deadline - self._monotonic()
                if remaining <= 0.0:
                    break
                self._publish_velocity(self._linear_speed)
                # 남은 시간보다 오래 자지 않는다 — 마지막 tick 이 정해진
                # 시간을 넘겨 주행을 길게 만드는 것을 막는다.
                self._sleep(min(self._tick_sec, remaining))
        finally:
            self._publish_velocity(0.0)
        return cancelled

    def _log(self, level: str, message: str) -> None:
        if self._logger is None:
            return
        emit = getattr(self._logger, level, None)
        if emit is not None:
            emit(message)
