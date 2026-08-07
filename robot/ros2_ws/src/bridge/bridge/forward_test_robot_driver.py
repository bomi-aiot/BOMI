"""
MQTT 통신 검증용으로 로봇을 짧게 직진시키는 ROS 2 드라이버다.

실제 목적지 좌표나 Nav2를 사용하지 않는다. 유효한 NAVIGATE 명령이 들어오면
전용 속도 토픽에 저속 전진 Twist를 주기적으로 발행하고, 설정 시간이 지나면
zero Twist를 발행한 뒤 결과를 반환한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import threading
import time
from typing import Any, Callable

from geometry_msgs.msg import Twist

from bridge import contract
from bridge.robot_driver import RobotDriver


DEFAULT_FORWARD_SPEED_M_S = 0.08
DEFAULT_FORWARD_DURATION_SECONDS = 2.0
DEFAULT_PUBLISH_RATE_HZ = 10.0
DEFAULT_COMMAND_TOPIC = "/cmd_vel_backend_test"
MAX_SAFE_TEST_SPEED_M_S = 0.154


@dataclass
class _MotionRun:
    """한 번의 전진 실행에서 완료 시각과 결과를 공유한다."""

    deadline: float
    completed: threading.Event = field(default_factory=threading.Event)
    status: str | None = None


class ForwardTestRobotDriver(RobotDriver):
    """
    유효한 NAVIGATE를 설정 시간 동안의 저속 직진으로 실행한다.

    입력값: ROS 2 publisher/timer를 만들 ``node``와 속도(m/s), 시간(초), 발행률
        (Hz), 출력 토픽을 받는다. 테스트에서는 ``clock``을 주입할 수 있다.
    반환값: 전진 후 정지까지 성공하면 ARRIVED, 취소·예외·종료에서는 FAILED.
    주의사항: ``navigate``는 전용 명령 작업 스레드에서 호출해야 한다. 실제 속도
        발행과 종료 판정은 ROS 2 timer가 담당하므로 MQTT callback은 차단하지 않는다.
    """

    def __init__(
        self,
        node: Any,
        *,
        forward_speed_m_s: float = DEFAULT_FORWARD_SPEED_M_S,
        forward_duration_seconds: float = DEFAULT_FORWARD_DURATION_SECONDS,
        publish_rate_hz: float = DEFAULT_PUBLISH_RATE_HZ,
        command_topic: str = DEFAULT_COMMAND_TOPIC,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._validate_parameters(
            forward_speed_m_s,
            forward_duration_seconds,
            publish_rate_hz,
            command_topic,
        )
        self._node = node
        self._logger = node.get_logger()
        self._forward_speed_m_s = float(forward_speed_m_s)
        self._forward_duration_seconds = float(forward_duration_seconds)
        self._clock = clock
        self._publisher = node.create_publisher(Twist, command_topic, 10)
        self._timer = node.create_timer(1.0 / publish_rate_hz, self._on_timer)

        self._lock = threading.Lock()
        self._active_run: _MotionRun | None = None
        self._shutting_down = False

    def navigate(self, target: str) -> str:
        """
        전진 실행을 시작하고 zero Twist 발행까지 끝난 결과를 반환한다.

        이미 이동 중이거나 종료 중이면 새 timer나 이동 시간을 만들지 않고 FAILED를
        반환한다. target 유효성은 MQTT 브릿지에서 먼저 검증한다.
        """
        with self._lock:
            if self._shutting_down or self._active_run is not None:
                self._logger.warning(
                    "Backend drive test rejected: another motion is active"
                )
                return contract.STATUS_FAILED

            run = _MotionRun(
                deadline=self._clock() + self._forward_duration_seconds
            )
            self._active_run = run
            try:
                self._publish_velocity(self._forward_speed_m_s)
            except Exception as error:
                self._logger.error(f"Forward command publish failed: {error}")
                self._complete_locked(contract.STATUS_FAILED)

        self._logger.info(f"Backend drive test started: target={target}")

        run.completed.wait()
        return run.status or contract.STATUS_FAILED

    def speak(self, text: str) -> str:
        """SPEAK 기존 테스트 결과를 유지하되 속도 명령은 발행하지 않는다."""
        return contract.STATUS_DONE

    def cancel(self) -> str:
        """진행 중인 전진을 즉시 정지시키고 CANCELLED를 반환한다."""
        self._complete_active_run(contract.STATUS_FAILED)
        return contract.STATUS_CANCELLED

    def shutdown(self) -> None:
        """종료 중인 전진을 실패 처리하고 마지막 zero Twist를 발행한다."""
        with self._lock:
            self._shutting_down = True

        self._complete_active_run(contract.STATUS_FAILED)
        self._publish_stop_best_effort()

        try:
            self._node.destroy_timer(self._timer)
        except Exception as error:
            self._logger.warning(f"Drive test timer cleanup failed: {error}")

    def _on_timer(self) -> None:
        """전진 Twist를 반복 발행하고 마감 시각에 정지한다."""
        with self._lock:
            run = self._active_run
            if run is None:
                return

            if self._clock() >= run.deadline:
                final_status = self._complete_locked(contract.STATUS_ARRIVED)
            else:
                try:
                    self._publish_velocity(self._forward_speed_m_s)
                    return
                except Exception as error:
                    self._logger.error(f"Forward command publish failed: {error}")
                    final_status = self._complete_locked(contract.STATUS_FAILED)

        self._logger.info(
            f"Backend drive test stopped: status={final_status}"
        )

    def _complete_active_run(self, requested_status: str) -> None:
        """활성 실행을 한 번만 정지시키고 대기 중인 명령 작업을 깨운다."""
        with self._lock:
            final_status = self._complete_locked(requested_status)
            if final_status is None:
                return

        self._logger.info(
            f"Backend drive test stopped: status={final_status}"
        )

    def _complete_locked(self, requested_status: str) -> str | None:
        """잠금을 보유한 상태에서 정지 발행과 실행 완료 처리를 수행한다."""
        run = self._active_run
        if run is None:
            return None

        final_status = requested_status
        try:
            self._publish_velocity(0.0)
        except Exception as error:
            final_status = contract.STATUS_FAILED
            self._logger.error(f"Stop command publish failed: {error}")

        self._active_run = None
        run.status = final_status
        run.completed.set()
        return final_status

    def _publish_stop_best_effort(self) -> None:
        """예외를 밖으로 전파하지 않고 zero Twist 발행을 최선으로 시도한다."""
        try:
            self._publish_velocity(0.0)
        except Exception as error:
            self._logger.error(f"Final stop command publish failed: {error}")

    def _publish_velocity(self, linear_x: float) -> None:
        """직진 또는 정지 Twist 한 개를 전용 토픽에 발행한다."""
        message = Twist()
        message.linear.x = linear_x
        message.angular.z = 0.0
        self._publisher.publish(message)

    @staticmethod
    def _validate_parameters(
        forward_speed_m_s: float,
        forward_duration_seconds: float,
        publish_rate_hz: float,
        command_topic: str,
    ) -> None:
        """속도·시간·주기·토픽 설정을 시작 전에 검증한다."""
        if not math.isfinite(forward_speed_m_s) or not (
            0.0 < forward_speed_m_s <= MAX_SAFE_TEST_SPEED_M_S
        ):
            raise ValueError(
                "forward_speed_m_s must be finite and in "
                f"(0, {MAX_SAFE_TEST_SPEED_M_S}]"
            )
        if not math.isfinite(forward_duration_seconds) or (
            forward_duration_seconds <= 0.0
        ):
            raise ValueError("forward_duration_seconds must be finite and positive")
        if not math.isfinite(publish_rate_hz) or publish_rate_hz <= 0.0:
            raise ValueError("publish_rate_hz must be finite and positive")
        if not command_topic.strip():
            raise ValueError("command_topic must not be blank")
