"""브릿지 코어 로직: 백엔드 명령을 받아 로봇 동작으로 실행하고 결과를 발행한다.

이 클래스는 MQTT 라이브러리와 ROS 2에 의존하지 않는다. "메시지를 발행하는
방법"을 ``publish`` 콜백으로 주입받으므로, 테스트에서는 리스트 수집기로,
운영에서는 paho-mqtt 발행 함수로 바꿔 끼울 수 있다. 실제 주행 실행도
``RobotDriver`` 경계로 주입받아 Mock/실물을 교체할 수 있다.

흐름:

``commands 수신 → 계약 파싱 → RobotDriver 실행 → results 발행(scenarioId echo-back)``
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from datetime import datetime
import threading
from typing import Callable

from bridge import contract
from bridge.robot_driver import RobotDriver

logger = logging.getLogger(__name__)

# 발행 콜백 형태: (topic, payload_json) -> None
PublishFn = Callable[[str, str], None]
SubmitFn = Callable[[Callable[[], None]], bool]
DEFAULT_RECENT_COMMAND_LIMIT = 256


class MqttBridge:
    """백엔드 MQTT 명령과 로봇 동작 사이의 통역 코어다."""

    def __init__(
        self,
        robot_id: str,
        driver: RobotDriver,
        publish: PublishFn,
        *,
        submit_navigation: SubmitFn | None = None,
        now: Callable[[], datetime] | None = None,
        recent_command_limit: int = DEFAULT_RECENT_COMMAND_LIMIT,
    ) -> None:
        """
        브릿지 의존성과 중복 명령 보관 한도를 설정한다.

        ``submit_navigation``은 NAVIGATE 작업을 MQTT callback 밖에서 실행한다.
        생략하면 기존처럼 현재 스레드에서 즉시 실행하므로 순수 단위 테스트에서
        별도 스레드가 필요 없다. 최근 commandId는 정해진 개수만 보관한다.
        """
        if recent_command_limit <= 0:
            raise ValueError("recent_command_limit must be positive")
        self._robot_id = robot_id
        self._driver = driver
        self._publish = publish
        self._submit_navigation = submit_navigation or self._run_immediately
        self._now = now
        self._recent_command_limit = recent_command_limit
        self._recent_command_ids: OrderedDict[str, None] = OrderedDict()
        self._command_lock = threading.Lock()

    @property
    def commands_topic(self) -> str:
        """이 로봇이 구독해야 하는 명령 토픽이다."""
        return contract.robot_commands_topic(self._robot_id)

    def publish_rest_state(self, rest_state: str) -> None:
        """로봇 휴식 상태 변화를 status 토픽으로 발행한다(REST_STATE_CHANGED).

        ``rest_state`` 는 ``contract.REST_STATE_RESTING`` 또는
        ``contract.REST_STATE_AWAKE`` 를 사용한다. 상태를 판정하는 센서 로직은
        이 브릿지 범위 밖이며, 여기서는 판정된 값을 계약대로 발행만 한다.
        """
        self._publish_status(
            contract.STATUS_TYPE_REST_STATE_CHANGED,
            {contract.REST_STATE_KEY: rest_state},
        )

    def publish_navigation_status(self, detail: dict) -> None:
        """주행 진행 상태를 status 토픽으로 발행한다(NAVIGATION_STATUS).

        진행률 등 세부 payload는 아직 계약이 고정되지 않아 호출자가 넘긴
        ``detail`` 을 그대로 싣는다(백엔드는 현재 이 상태를 로깅만 한다).
        """
        self._publish_status(contract.STATUS_TYPE_NAVIGATION, detail)

    def _publish_status(self, status_type: str, payload: dict) -> None:
        envelope = contract.build_status_envelope(
            self._robot_id, status_type, payload
        )
        self._publish(
            contract.robot_status_topic(self._robot_id),
            json.dumps(envelope, ensure_ascii=False),
        )
        logger.info("상태 발행: type=%s", status_type)

    def on_command(self, raw_payload: str | bytes) -> None:
        """수신한 명령 하나를 처리한다.

        계약 위반 메시지는 로그를 남기고 버린다(백엔드도 동일 정책). 다른
        로봇을 향한 명령은 무시한다. 정상 명령은 타입별로 실행하고 결과를
        발행한다.
        """
        try:
            command = contract.parse_command(raw_payload)
        except contract.ContractError as error:
            logger.warning("Invalid command ignored: %s", error)
            return

        if command.robot_id != self._robot_id:
            logger.debug(
                "다른 로봇(%s)을 향한 명령이라 무시합니다", command.robot_id
            )
            return

        logger.info(
            "Received command: commandId=%s scenarioId=%s type=%s target=%s",
            command.command_id,
            command.scenario_id,
            command.type,
            command.target,
        )

        if not self._remember_command_id(command.command_id):
            logger.warning(
                "Duplicate command ignored: commandId=%s scenarioId=%s",
                command.command_id,
                command.scenario_id,
            )
            return

        if contract.is_command_expired(command, now=self._now):
            logger.warning(
                "Expired command ignored: commandId=%s scenarioId=%s",
                command.command_id,
                command.scenario_id,
            )
            if command.type == contract.CMD_NAVIGATE:
                self._publish_result(
                    contract.RESULT_NAVIGATION,
                    command.scenario_id,
                    contract.STATUS_FAILED,
                )
            return

        if command.type == contract.CMD_NAVIGATE:
            self._handle_navigate(command)
        elif command.type == contract.CMD_SPEAK:
            self._handle_speak(command)
        elif command.type == contract.CMD_CANCEL:
            self._handle_cancel(command)
        elif command.type == contract.CMD_FOLLOW_START:
            self._handle_follow(command, start=True)
        elif command.type == contract.CMD_FOLLOW_STOP:
            self._handle_follow(command, start=False)
        else:  # parse_command이 이미 걸러내지만 방어적으로 둔다
            logger.warning("처리할 수 없는 명령 타입입니다: %s", command.type)

    def _handle_navigate(self, command: contract.RobotCommand) -> None:
        target = command.target
        if not isinstance(target, str) or target not in contract.NAV_TARGETS:
            logger.warning(
                "Unknown navigation target: commandId=%s scenarioId=%s target=%s",
                command.command_id,
                command.scenario_id,
                target,
            )
            self._publish_result(
                contract.RESULT_NAVIGATION,
                command.scenario_id,
                contract.STATUS_FAILED,
            )
            return

        def task() -> None:
            self._execute_navigate(command, target)

        try:
            accepted = self._submit_navigation(task)
        except Exception as error:
            logger.error(
                "Navigation task submission failed: commandId=%s error=%s",
                command.command_id,
                error,
            )
            accepted = False

        if not accepted:
            logger.warning(
                "Navigation command rejected while busy: commandId=%s "
                "scenarioId=%s",
                command.command_id,
                command.scenario_id,
            )
            self._publish_result(
                contract.RESULT_NAVIGATION,
                command.scenario_id,
                contract.STATUS_FAILED,
            )

    def _execute_navigate(
        self,
        command: contract.RobotCommand,
        target: str,
    ) -> None:
        """승인된 NAVIGATE를 드라이버에서 실행하고 완료 결과를 발행한다."""
        try:
            status = self._driver.navigate(target)
        except Exception as error:
            logger.error(
                "Navigation execution failed: commandId=%s scenarioId=%s error=%s",
                command.command_id,
                command.scenario_id,
                error,
            )
            try:
                self._driver.cancel()
            except Exception as cancel_error:
                logger.error("Emergency stop failed: %s", cancel_error)
            status = contract.STATUS_FAILED

        self._publish_result(
            contract.RESULT_NAVIGATION,
            command.scenario_id,
            status,
        )
        logger.info(
            "Navigation test completed: commandId=%s scenarioId=%s "
            "target=%s status=%s",
            command.command_id,
            command.scenario_id,
            target,
            status,
        )

    def _handle_speak(self, command: contract.RobotCommand) -> None:
        status = self._driver.speak(command.text or "")
        self._publish_result(contract.RESULT_SPEAK, command.scenario_id, status)

    def _handle_cancel(self, command: contract.RobotCommand) -> None:
        status = self._driver.cancel()
        self._publish_result(contract.RESULT_CANCEL, command.scenario_id, status)

    def _handle_follow(
        self,
        command: contract.RobotCommand,
        *,
        start: bool,
    ) -> None:
        """추종 명령을 드라이버 경계로 전달하되 전진 테스트와 분리한다."""
        status = (
            self._driver.follow_start() if start else self._driver.follow_stop()
        )
        self._publish_result(contract.RESULT_FOLLOW, command.scenario_id, status)

    def _publish_result(self, result_type: str, scenario_id: str, status: str) -> None:
        envelope = contract.build_result_envelope(
            self._robot_id, result_type, scenario_id, status
        )
        self._publish(
            contract.robot_results_topic(self._robot_id),
            json.dumps(envelope, ensure_ascii=False),
        )
        logger.info(
            "결과 발행: type=%s, scenarioId=%s, status=%s",
            result_type,
            scenario_id,
            status,
        )

    def _remember_command_id(self, command_id: str) -> bool:
        """최근 commandId를 유한한 크기로 보관하고 중복 여부를 반환한다."""
        with self._command_lock:
            if command_id in self._recent_command_ids:
                return False

            self._recent_command_ids[command_id] = None
            if len(self._recent_command_ids) > self._recent_command_limit:
                self._recent_command_ids.popitem(last=False)
            return True

    @staticmethod
    def _run_immediately(task: Callable[[], None]) -> bool:
        """단위 테스트와 기존 직접 사용 경로에서 작업을 즉시 실행한다."""
        task()
        return True
