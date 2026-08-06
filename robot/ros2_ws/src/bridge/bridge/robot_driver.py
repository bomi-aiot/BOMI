"""로봇의 실제 주행/발화 실행을 격리하는 경계(RobotDriver)를 정의한다.

브릿지 코어는 이 인터페이스만 알고, 실제 구현이 Mock인지 실물인지 모른다.
그래서 하드웨어와 Nav2가 준비되면 주입하는 구현 **한 곳만** 바꾸면 실물로
전환된다. 이것이 이 프로젝트의 핵심 설계 제약이다.

현재 고를 수 있는 구현은 넷이다 — ``mock``(하드웨어 없음), ``nav2``(실주행),
``timed``(지도 없이 정해진 시간 직진), ``forward_test``(MQTT 전진 통신 테스트).
구현별 ROS 2 자원은 각 모듈에 두고 이 파일은 공통 경계와 선택 규칙만 담당한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from bridge import contract


class RobotDriver(ABC):
    """명령을 실제 로봇 동작으로 실행하고 결과 상태 문자열을 반환하는 경계다.

    last_reason_code
        실패/취소 직후 브릿지가 v1 결과의 reasonCode 로 읽어 가는 선택
        속성이다(``getattr`` 로 조회하므로 없어도 동작은 하지만, 그러면
        reasonCode 가 항상 INTERNAL_ERROR 로 뭉개진다). 값은 반드시
        ``contract.REASON_*`` 중 하나여야 한다 — 백엔드는 그 enum 밖 문자열을
        조용히 폐기한다. 각 실패 분기마다 **명시적으로** 설정할 것: 이전
        호출이 남긴 값이 새어 나가는 버그가 실제로 있었다(speak() 가
        초기화를 빼먹어 직전 navigate() 의 reason 을 물려받은 사례).
    """

    #: 서브클래스가 매 실패 분기에서 갱신한다. 기본값 None = INTERNAL_ERROR.
    last_reason_code: str | None = None

    @abstractmethod
    def navigate(self, target: str) -> str:
        """목적지로 이동하고 결과 상태(ARRIVED/FAILED)를 반환한다."""

    @abstractmethod
    def speak(self, text: str) -> str:
        """문장을 발화하고 결과 상태(DONE)를 반환한다."""

    @abstractmethod
    def cancel(self) -> str:
        """진행 중인 동작을 취소하고 결과 상태(CANCELLED)를 반환한다."""

    def shutdown(self) -> None:
        """드라이버가 보유한 자원을 정리한다.

        기본 구현은 아무 것도 하지 않는다. Nav2 드라이버처럼 ROS 2 노드나 액션
        클라이언트를 보유하는 구현이 이 메서드를 재정의해 종료 시 자원을
        해제한다. 상위 실행 노드가 종료 시 한 번 호출한다.
        """


class MockRobotDriver(RobotDriver):
    """하드웨어 없이 명령 결과만 흉내 내는 테스트용 구현이다.

    실제 주행/발화 대신 정해진 성공 상태를 반환한다. 통신·상태 전이 검증이
    목적이므로 기본 지연은 0이며, 필요하면 ``delay_seconds`` 로 이동 시간을
    흉내 낼 수 있다.

    ★ 단, 알 수 없는 target 은 Mock 도 FAILED 로 처리한다. 과거에는 아무
      target 에나 ARRIVED 를 돌려줬는데, 그러면 백엔드가 존재하지 않는
      목적지에 대해 "도착했다"는 거짓 성공을 받는다 — mock 검증(V1·V2 단계)
      전체가 무의미해지는 구멍이라 실물과 같은 판정 기준을 쓴다.
    """

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds = delay_seconds
        # 브릿지가 실패 결과의 reasonCode 로 읽어 가는 값(선택 규약).
        self.last_reason_code: str | None = None

    def navigate(self, target: str) -> str:
        """지원 목적지면 도착을 흉내 내고 ARRIVED, 아니면 FAILED 를 반환한다."""
        if target not in contract.NAVIGATION_TARGETS:
            self.last_reason_code = contract.REASON_UNKNOWN_TARGET
            return contract.STATUS_FAILED
        self.last_reason_code = None
        self._wait()
        return contract.STATUS_ARRIVED

    def speak(self, text: str) -> str:
        """발화 완료를 흉내 내고 DONE을 반환한다."""
        self._wait()
        return contract.STATUS_DONE

    def cancel(self) -> str:
        """취소 처리를 흉내 내고 CANCELLED를 반환한다."""
        return contract.STATUS_CANCELLED

    def _wait(self) -> None:
        if self._delay_seconds > 0:
            import time

            time.sleep(self._delay_seconds)


# 드라이버 선택 파라미터(driver_type)가 가질 수 있는 값이다. 잘못된 값이 조용히
# Mock으로 넘어가지 않도록, 허용값을 여기서 명시적으로 제한한다.
DRIVER_TYPE_MOCK = "mock"
DRIVER_TYPE_NAV2 = "nav2"
# 지도·좌표 없이 "정해진 시간 직진"으로 이동을 대체하는 임시 드라이버.
# Nav2 병목을 우회해 계약 왕복·대화·DB 종결을 검증하기 위한 것이며,
# 주행 품질은 보장하지 않는다(bridge/timed_drive_driver.py 참고).
DRIVER_TYPE_TIMED = "timed"
# 백엔드 → MQTT → 모터 배선만 확인하는 통신 테스트용. timed 와 목적은 비슷하지만
# 전용 토픽(/cmd_vel_backend_test)으로 발행해 twist_mux 우선순위 아래에 둔다
# (bridge/forward_test_robot_driver.py, launch/backend_drive_test.launch.py 참고).
DRIVER_TYPE_FORWARD_TEST = "forward_test"


def create_driver(
    driver_type: str,
    *,
    create_mock: Callable[[], RobotDriver],
    create_nav2: Callable[[], RobotDriver],
    create_timed: Callable[[], RobotDriver] | None = None,
    create_forward_test: Callable[[], RobotDriver] | None = None,
) -> RobotDriver:
    """driver_type 값에 따라 알맞은 드라이버를 생성한다.

    역할: 실행 환경이 고른 driver_type에 맞춰 드라이버를 만든다. 실제 생성은
        주입된 팩터리가 담당한다. 덕분에 이 함수 자체는 ROS 2에 의존하지 않아
        단위 테스트할 수 있고, Nav2 드라이버는 nav2가 선택된 경우에만 생성된다.
    입력값: driver_type - "mock", "nav2", "timed", "forward_test".
        create_mock/create_nav2/create_timed/create_forward_test - 각 드라이버를
        만들어 돌려주는 인자 없는 함수. create_timed 와 create_forward_test 는
        선택이며, 주입하지 않은 실행 경로에서 그 driver_type 을 고르면
        ValueError 로 거절한다(조용히 다른 드라이버로 대체하지 않는다).
    반환값: 선택된 RobotDriver 구현.
    실패: 허용하지 않는 driver_type이면 ValueError를 던진다. 조용히 Mock으로
        대체하지 않는다.
    """
    if driver_type == DRIVER_TYPE_MOCK:
        return create_mock()
    if driver_type == DRIVER_TYPE_NAV2:
        return create_nav2()
    if driver_type == DRIVER_TYPE_TIMED:
        if create_timed is None:
            raise ValueError(
                f"driver_type '{DRIVER_TYPE_TIMED}' is not available on this "
                "run path (no factory was provided)"
            )
        return create_timed()
    if driver_type == DRIVER_TYPE_FORWARD_TEST:
        if create_forward_test is None:
            raise ValueError(
                f"driver_type '{DRIVER_TYPE_FORWARD_TEST}' is not available on "
                "this run path (no factory was provided)"
            )
        return create_forward_test()
    raise ValueError(
        f"unknown driver_type '{driver_type}'; use "
        f"'{DRIVER_TYPE_MOCK}', '{DRIVER_TYPE_NAV2}', '{DRIVER_TYPE_TIMED}', or "
        f"'{DRIVER_TYPE_FORWARD_TEST}'"
    )
