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
from typing import Callable

from bridge import contract
from bridge.robot_driver import RobotDriver

logger = logging.getLogger(__name__)

# 발행 콜백 형태: (topic, payload_json) -> None
PublishFn = Callable[[str, str], None]


class MqttBridge:
    """백엔드 MQTT 명령과 로봇 동작 사이의 통역 코어다."""

    def __init__(self, robot_id: str, driver: RobotDriver, publish: PublishFn) -> None:
        self._robot_id = robot_id
        self._driver = driver
        self._publish = publish

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
            logger.warning("계약 위반 명령을 버립니다: %s", error)
            return

        if command.robot_id != self._robot_id:
            logger.debug(
                "다른 로봇(%s)을 향한 명령이라 무시합니다", command.robot_id
            )
            return

        if command.type == contract.CMD_NAVIGATE:
            self._handle_navigate(command)
        elif command.type == contract.CMD_SPEAK:
            self._handle_speak(command)
        elif command.type == contract.CMD_CANCEL:
            self._handle_cancel(command)
        else:  # parse_command이 이미 걸러내지만 방어적으로 둔다
            logger.warning("처리할 수 없는 명령 타입입니다: %s", command.type)

    def _handle_navigate(self, command: contract.RobotCommand) -> None:
        target = command.target
        if not target:
            logger.warning("NAVIGATE 명령에 target이 없어 FAILED로 처리합니다")
            status = contract.STATUS_FAILED
        else:
            status = self._driver.navigate(target)
        self._publish_result(contract.RESULT_NAVIGATION, command.scenario_id, status)

    def _handle_speak(self, command: contract.RobotCommand) -> None:
        status = self._driver.speak(command.text or "")
        self._publish_result(contract.RESULT_SPEAK, command.scenario_id, status)

    def _handle_cancel(self, command: contract.RobotCommand) -> None:
        status = self._driver.cancel()
        self._publish_result(contract.RESULT_CANCEL, command.scenario_id, status)

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
