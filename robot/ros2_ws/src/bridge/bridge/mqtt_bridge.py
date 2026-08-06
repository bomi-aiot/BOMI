"""브릿지 코어 로직: 백엔드 명령을 받아 로봇 동작으로 실행하고 결과를 발행한다.

이 클래스는 MQTT 라이브러리와 ROS 2에 의존하지 않는다. "메시지를 발행하는
방법"을 ``publish`` 콜백으로 주입받으므로, 테스트에서는 리스트 수집기로,
운영에서는 paho-mqtt 발행 함수로 바꿔 끼울 수 있다. 실제 주행 실행도
``RobotDriver`` 경계로 주입받아 Mock/실물을 교체할 수 있다.

흐름::

    commands 수신 → 계약 파싱 → 만료/중복 검사 → 실행(워커) → v1 결과 발행

v1 정합 개편(2026-08)에서 추가된 안전 규칙 — 인수인계 필수 항목이다:

* **expiresAt 만료 명령 실행 금지.** 늦게 도착한 "현관으로 가라"가 빈 현관
  주행이 되는 것을 막는다. 만료는 COMMAND_EXPIRED 실패로 회신한다(무시 금지).
* **동일 commandId 중복 실행 금지.** QoS 1 은 at-least-once 라 재전송이 정상
  동작이다. 중복은 실행하지 않고 버린다(백엔드 계약: "이미 실행 중이면 유지").
* **MQTT 수신과 실행의 스레드 분리.** navigate 가 최대 120초 블로킹하는 동안
  paho 콜백 스레드를 잡고 있으면 (1) CANCEL 이 큐에서 썩고 (2) keepalive(60초)
  PINGREQ 를 못 보내 브로커가 연결을 끊는다. 실행은 워커 스레드로 넘긴다.
* **STOP/CANCEL 즉시 처리.** CANCEL 은 워커를 거치지 않고 수신 스레드에서 곧장
  driver.cancel() 을 부른다 — 그래야 진행 중인 주행이 실제로 멈춘다.
* **무응답 금지.** 계약 위반이라도 scenarioId/commandId/type 을 읽을 수 있으면
  FAILED 를 회신한다. 조용히 버리면 백엔드는 20분 타임아웃까지 기다렸다가
  로봇을 SAFE_STOP 에 잠근다(CLAUDE.md §3).
"""

from __future__ import annotations

from collections import OrderedDict
import json
import logging
import queue
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from bridge import contract
from bridge.robot_driver import RobotDriver

logger = logging.getLogger(__name__)

# 발행 콜백 형태: (topic, payload_json) -> None
PublishFn = Callable[[str, str], None]

# 중복 검사용으로 기억하는 commandId 최대 개수. 브로커 재전송은 보통 직전
# 몇 건 안에서 일어나므로 크게 잡을 이유가 없다. 넘치면 오래된 것부터 잊는다.
#   올리면 -> 메모리 소폭 증가, 아주 늦은 재전송까지 잡는다.
#   내리면 -> 폭주 상황에서 오래된 중복을 놓칠 수 있다.
SEEN_COMMANDS_MAX = 256

# 워커 종료 신호(sentinel). 큐에 이 값이 들어오면 워커 루프가 끝난다.
_STOP = object()

# 드라이버 내부 상태 → (outcome, resultCode) 번역표. 결과 타입별로 resultCode
# 어휘가 다르므로 명령 종류마다 표가 하나씩 있다. reasonCode 는 실패 시
# 드라이버가 last_reason_code 로 알려주며, 없으면 INTERNAL_ERROR 로 둔다.
_NAVIGATE_STATUS_MAP = {
    contract.STATUS_ARRIVED: (contract.OUTCOME_SUCCEEDED, contract.CODE_ARRIVED),
    contract.STATUS_FAILED: (contract.OUTCOME_FAILED, contract.CODE_NOT_ARRIVED),
    contract.STATUS_CANCELLED: (
        contract.OUTCOME_CANCELLED,
        contract.CODE_NOT_ARRIVED,
    ),
}
_SPEAK_STATUS_MAP = {
    contract.STATUS_DONE: (contract.OUTCOME_SUCCEEDED, contract.CODE_SPOKEN),
    contract.STATUS_FAILED: (contract.OUTCOME_FAILED, contract.CODE_NOT_SPOKEN),
    contract.STATUS_CANCELLED: (
        contract.OUTCOME_CANCELLED,
        contract.CODE_NOT_SPOKEN,
    ),
}
_CANCEL_STATUS_MAP = {
    contract.STATUS_CANCELLED: (
        contract.OUTCOME_SUCCEEDED,
        contract.CODE_TARGET_CANCELLED,
    ),
    contract.STATUS_FAILED: (
        contract.OUTCOME_FAILED,
        contract.CODE_TARGET_UNCHANGED,
    ),
}

# 만료 회신에 쓰는 결과 타입별 resultCode. 만료는 "아무것도 안 했다"이므로
# 각 타입의 부정형 코드를 쓴다.
_EXPIRED_RESULT_CODE = {
    contract.CMD_NAVIGATE: (contract.RESULT_NAVIGATION, contract.CODE_NOT_ARRIVED),
    contract.CMD_SPEAK: (contract.RESULT_SPEAK, contract.CODE_NOT_SPOKEN),
    contract.CMD_CANCEL: (contract.RESULT_CANCEL, contract.CODE_TARGET_UNCHANGED),
    contract.CMD_FOLLOW_START: (contract.RESULT_FOLLOW, contract.CODE_UNCHANGED),
    contract.CMD_FOLLOW_STOP: (contract.RESULT_FOLLOW, contract.CODE_UNCHANGED),
}


class MqttBridge:
    """백엔드 MQTT 명령과 로봇 동작 사이의 통역 코어다.

    스레드 모델
        on_command 는 항상 수신 스레드(paho 콜백)에서 불린다. 파싱·만료·중복
        검사와 CANCEL 실행은 그 자리에서 하고, 시간이 걸리는 실행(NAVIGATE 등)은
        ``async_execution=True`` 일 때 워커 스레드 하나로 넘긴다. 워커는 하나뿐
        이므로 실행 순서는 도착 순서와 같다. 중복 검사 상태(_seen)는 수신
        스레드에서만 만지므로 락이 필요 없다.

    테스트는 ``async_execution=False``(기본값)로 만들어 모든 것이 호출 스레드
    에서 동기로 끝나게 한다 — 결과 발행을 바로 assert 할 수 있다.
    """

    def __init__(
        self,
        robot_id: str,
        driver: RobotDriver,
        publish: PublishFn,
        *,
        async_execution: bool = False,
        now: Callable[[], datetime] | None = None,
        on_arrival: Callable[[str], None] | None = None,
    ) -> None:
        self._robot_id = robot_id
        self._driver = driver
        self._publish = publish
        self._now = now or (lambda: datetime.now(timezone.utc))
        # 도착 직후 훅(선택). NAVIGATE 가 SUCCEEDED/ARRIVED 로 끝난 뒤 target
        # 문자열과 함께 불린다 — "도착 후 사람 접근"(CLAUDE.md §3a, 보미야 호출
        # 대본의 마지막 구간)이 이 훅에 얹힌다. 백엔드 계약과 무관한 로봇 내부
        # 행동이므로 결과 발행 '뒤'에 부른다: 훅이 아무리 오래 걸리거나 죽어도
        # 백엔드가 보는 시나리오는 이미 정상 종결돼 있다.
        self._on_arrival = on_arrival

        # 최근에 본 commandId. OrderedDict 를 LRU 처럼 쓴다(값은 무의미).
        self._seen: OrderedDict[str, None] = OrderedDict()

        self._async = async_execution
        self._queue: queue.Queue[Any] | None = None
        self._worker: threading.Thread | None = None
        if async_execution:
            self._queue = queue.Queue()
            self._worker = threading.Thread(
                target=self._worker_loop, name="bridge-executor", daemon=True
            )
            self._worker.start()

    @property
    def commands_topic(self) -> str:
        """이 로봇이 구독해야 하는 명령 토픽이다."""
        return contract.robot_commands_topic(self._robot_id)

    def stop(self) -> None:
        """워커 스레드를 정리한다. async_execution 이 아니면 아무 일도 안 한다."""
        if self._queue is not None:
            self._queue.put(_STOP)
        if self._worker is not None:
            self._worker.join(timeout=5.0)

    # ── status 발행 (v1 개편과 무관, 기존 유지) ────────────────────────────

    def publish_rest_state(self, rest_state: str) -> None:
        """로봇 휴식 상태 변화를 status 토픽으로 발행한다(REST_STATE_CHANGED)."""
        self._publish_status(
            contract.STATUS_TYPE_REST_STATE_CHANGED,
            {contract.REST_STATE_KEY: rest_state},
        )

    def publish_navigation_status(self, detail: dict) -> None:
        """주행 진행 상태를 status 토픽으로 발행한다(NAVIGATION_STATUS)."""
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

    # ── 명령 수신 (수신 스레드) ─────────────────────────────────────────────

    def on_command(self, raw_payload: str | bytes) -> None:
        """수신한 명령 하나를 처리한다.

        수신 스레드에서 하는 일: 파싱 → 대상 확인 → 중복 검사 → 만료 검사 →
        (CANCEL 이면 즉시 실행 / 그 외는 워커로 전달). 어떤 경로든 여기서
        오래 블로킹하지 않는다.
        """
        try:
            command = contract.parse_command(raw_payload)
        except contract.ContractError as error:
            logger.warning("계약 위반 명령: %s", error)
            # 무응답 금지: 상관관계 ID 를 건질 수 있으면 FAILED 라도 회신한다.
            # 백엔드가 응답 없이 20분을 기다리다 로봇을 SAFE_STOP 에 잠그는
            # 것보다, 즉시 실패를 알리는 편이 압도적으로 낫다.
            self._reply_failure_if_possible(raw_payload)
            return

        if command.robot_id != self._robot_id:
            logger.debug(
                "다른 로봇(%s)을 향한 명령이라 무시합니다", command.robot_id
            )
            return

        # 중복: 실행하지도, 다시 회신하지도 않는다. QoS 1 재전송은 정상이고
        # 백엔드는 같은 commandId 의 최종 상태를 이미 저장하고 있다.
        if command.command_id in self._seen:
            logger.info("중복 commandId 무시: %s", command.command_id)
            return
        self._remember(command.command_id)

        if contract.command_expired(command, now=self._now):
            logger.warning(
                "만료된 명령(commandId=%s, expiresAt=%s)을 실행하지 않습니다",
                command.command_id,
                command.expires_at,
            )
            self._publish_expired(command)
            return

        if command.type == contract.CMD_CANCEL:
            # ★ CANCEL 은 줄을 서지 않는다. 워커가 navigate 로 바쁜 동안에도
            #   수신 스레드에서 곧장 driver.cancel() 을 불러 진행 중인 목표를
            #   실제로 중단시킨다. (Nav2 드라이버의 cancel 은 스레드 안전 —
            #   취소 요청만 던지고 spin 은 하지 않는다.)
            self._handle_cancel(command)
            return

        if self._async and self._queue is not None:
            self._queue.put(command)
        else:
            self._execute(command)

    # ── 실행 (워커 스레드 또는 동기) ────────────────────────────────────────

    def _worker_loop(self) -> None:
        assert self._queue is not None
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            try:
                self._execute(item)
            except Exception:  # noqa: BLE001 - 워커가 죽으면 이후 명령 전부가 무응답이 된다
                logger.exception("명령 실행 중 예상하지 못한 오류")

    def _execute(self, command: contract.RobotCommand) -> None:
        # 큐에서 기다리는 동안 만료됐을 수 있다. 실행 직전에 한 번 더 본다.
        if contract.command_expired(command, now=self._now):
            logger.warning(
                "대기 중 만료된 명령(commandId=%s)을 실행하지 않습니다",
                command.command_id,
            )
            self._publish_expired(command)
            return

        if command.type == contract.CMD_NAVIGATE:
            self._handle_navigate(command)
        elif command.type == contract.CMD_SPEAK:
            self._handle_speak(command)
        elif command.type in (contract.CMD_FOLLOW_START, contract.CMD_FOLLOW_STOP):
            self._handle_follow_stub(command)
        else:  # parse_command 가 이미 걸러내지만 방어적으로 둔다
            logger.warning("처리할 수 없는 명령 타입입니다: %s", command.type)

    def _handle_navigate(self, command: contract.RobotCommand) -> None:
        target = command.target
        if not target:
            logger.warning("NAVIGATE 명령에 target이 없어 FAILED로 처리합니다")
            self._publish_result(
                contract.RESULT_NAVIGATION,
                command,
                contract.OUTCOME_FAILED,
                contract.CODE_NOT_ARRIVED,
                contract.REASON_UNKNOWN_TARGET,
            )
            return
        status = self._driver.navigate(target)
        outcome, code = _NAVIGATE_STATUS_MAP.get(
            status, (contract.OUTCOME_FAILED, contract.CODE_NOT_ARRIVED)
        )
        self._publish_result(
            contract.RESULT_NAVIGATION, command, outcome, code,
            self._reason_for(outcome),
        )
        # 도착 훅은 결과 발행 뒤에, 성공했을 때만. 실패한 주행 뒤에 사람 접근을
        # 시작하면 로봇이 어디 있는지도 모르는 채 움직인다.
        if outcome == contract.OUTCOME_SUCCEEDED and self._on_arrival is not None:
            try:
                self._on_arrival(target)
            except Exception:  # noqa: BLE001 - 접근 훅 실패가 명령 처리를 죽이면 안 된다
                logger.exception("도착 훅 실행 중 오류 (target=%s)", target)

    def _handle_speak(self, command: contract.RobotCommand) -> None:
        status = self._driver.speak(command.text or "")
        outcome, code = _SPEAK_STATUS_MAP.get(
            status, (contract.OUTCOME_FAILED, contract.CODE_NOT_SPOKEN)
        )
        self._publish_result(
            contract.RESULT_SPEAK, command, outcome, code,
            self._reason_for(outcome),
        )

    def _handle_cancel(self, command: contract.RobotCommand) -> None:
        status = self._driver.cancel()
        outcome, code = _CANCEL_STATUS_MAP.get(
            status, (contract.OUTCOME_FAILED, contract.CODE_TARGET_UNCHANGED)
        )
        self._publish_result(
            contract.RESULT_CANCEL, command, outcome, code,
            self._reason_for(outcome),
        )

    def _handle_follow_stub(self, command: contract.RobotCommand) -> None:
        """산책(FOLLOW) 은 시연 범위 밖 — 즉시 실패를 회신하는 스텁이다.

        무응답이 아니라 실패 회신인 이유: 백엔드의 FOLLOW ACK 타임아웃은
        10초다. 조용히 버리면 10초 뒤 시나리오가 TIMED_OUT 으로 죽고 로봇이
        SAFE_STOP 에 잠긴다. 즉시 FAILED 를 돌려주면 시나리오는 FAILED 로
        깔끔하게 닫힌다(어느 쪽이든 SAFE_STOP 이지만, 원인이 로그에 남고
        10초를 기다리지 않는다). 산책을 구현하는 날 이 스텁을 지운다.
        """
        logger.warning(
            "FOLLOW 명령(%s)은 아직 미구현이라 FAILED 스텁으로 회신합니다",
            command.type,
        )
        self._publish_result(
            contract.RESULT_FOLLOW,
            command,
            contract.OUTCOME_FAILED,
            contract.CODE_UNCHANGED,
            contract.REASON_INTERNAL_ERROR,
        )

    # ── 발행 보조 ───────────────────────────────────────────────────────────

    def _reason_for(self, outcome: str) -> str | None:
        """실패/취소 outcome 에 붙일 reasonCode 를 드라이버에게 묻는다.

        드라이버는 실패 직전에 last_reason_code 를 남길 수 있다(선택).
        없으면 INTERNAL_ERROR. SUCCEEDED 면 계약상 반드시 None 이다.
        """
        if outcome == contract.OUTCOME_SUCCEEDED:
            return None
        if outcome == contract.OUTCOME_CANCELLED:
            # 취소는 원인이 명확하다 — 안전 정지 계열로 보고한다. 백엔드
            # 테스트도 CANCELLED 결과에 SAFETY_STOP 을 쓴다.
            return contract.REASON_SAFETY_STOP
        return self._driver.last_reason_code or contract.REASON_INTERNAL_ERROR

    def _publish_expired(self, command: contract.RobotCommand) -> None:
        result_type, code = _EXPIRED_RESULT_CODE[command.type]
        self._publish_result(
            result_type,
            command,
            contract.OUTCOME_FAILED,
            code,
            contract.REASON_COMMAND_EXPIRED,
        )

    def _publish_result(
        self,
        result_type: str,
        command: contract.RobotCommand,
        outcome: str,
        result_code: str,
        reason_code: str | None,
    ) -> None:
        envelope = contract.build_result_envelope(
            self._robot_id,
            result_type,
            command.scenario_id,
            command.command_id,
            outcome,
            result_code,
            reason_code,
            now=self._now,
        )
        self._publish(
            contract.robot_results_topic(self._robot_id),
            json.dumps(envelope, ensure_ascii=False),
        )
        logger.info(
            "결과 발행: type=%s, scenarioId=%s, commandId=%s, outcome=%s/%s/%s",
            result_type,
            command.scenario_id,
            command.command_id,
            outcome,
            result_code,
            reason_code,
        )

    def _reply_failure_if_possible(self, raw_payload: str | bytes) -> None:
        """계약 위반 명령에서 상관관계 ID 를 건져 FAILED 를 회신해 본다.

        JSON 이 아예 깨졌거나 필수 ID 가 없으면 회신할 방법이 없으므로
        조용히 포기한다(그 경우는 로그가 유일한 흔적이다).
        """
        try:
            if isinstance(raw_payload, bytes):
                raw_payload = raw_payload.decode("utf-8")
            body = json.loads(raw_payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(body, dict):
            return
        scenario_id = body.get("scenarioId")
        command_id = body.get("commandId")
        command_type = body.get("type")
        if not (
            isinstance(scenario_id, str) and scenario_id
            and isinstance(command_id, str) and command_id
            and command_type in _EXPIRED_RESULT_CODE
        ):
            return
        # 다른 로봇을 향한 위반 메시지에 회신하면 안 된다.
        if body.get("robotId") != self._robot_id:
            return
        result_type, code = _EXPIRED_RESULT_CODE[command_type]
        envelope = contract.build_result_envelope(
            self._robot_id,
            result_type,
            scenario_id,
            command_id,
            contract.OUTCOME_FAILED,
            code,
            contract.REASON_INTERNAL_ERROR,
            now=self._now,
        )
        self._publish(
            contract.robot_results_topic(self._robot_id),
            json.dumps(envelope, ensure_ascii=False),
        )
        logger.info(
            "계약 위반 명령에 FAILED 회신: commandId=%s", command_id
        )

    def _remember(self, command_id: str) -> None:
        self._seen[command_id] = None
        while len(self._seen) > SEEN_COMMANDS_MAX:
            self._seen.popitem(last=False)
