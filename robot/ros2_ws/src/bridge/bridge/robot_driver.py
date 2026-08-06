"""로봇의 실제 주행/발화 실행을 격리하는 경계(RobotDriver)를 정의한다.

브릿지 코어는 이 인터페이스만 알고, 실제 구현이 Mock인지 실물인지 모른다.
그래서 하드웨어와 Nav2가 준비되면 주입하는 구현 **한 곳만** 바꾸면 실물로
전환된다. 이것이 이 프로젝트의 핵심 설계 제약이다.

현재 필요한 구현은 ``MockRobotDriver`` 하나다. 실물 구현(가칭 Nav2RobotDriver)은
하드웨어와 Nav2가 준비된 시점에 이 파일에 함께 추가한다. 실물은 강현의
``NavigateToPose`` 액션 클라이언트 패턴(S15P11E102-79)을 이식해 Nav2를 직접
호출한다(``docs/decisions/0001-nav2-driver-owns-action-client.md`` 참고).
미리 빈 골격을 두지 않는다(로봇 ``AGENTS.md`` 규칙).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from bridge import contract


class RobotDriver(ABC):
    """명령을 실제 로봇 동작으로 실행하고 결과 상태 문자열을 반환하는 경계다."""

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
    """

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self._delay_seconds = delay_seconds

    def navigate(self, target: str) -> str:
        """목적지 도착을 흉내 내고 ARRIVED를 반환한다."""
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


def create_driver(
    driver_type: str,
    *,
    create_mock: Callable[[], RobotDriver],
    create_nav2: Callable[[], RobotDriver],
) -> RobotDriver:
    """driver_type 값에 따라 알맞은 드라이버를 생성한다.

    역할: 실행 환경이 고른 driver_type에 맞춰 Mock 또는 Nav2 드라이버를 만든다.
        실제 생성은 주입된 팩터리(create_mock/create_nav2)가 담당한다. 덕분에 이
        함수 자체는 ROS 2에 의존하지 않아 단위 테스트할 수 있고, Nav2 드라이버는
        nav2가 선택된 경우에만 생성된다.
    입력값: driver_type - "mock" 또는 "nav2". create_mock/create_nav2 - 각각
        Mock, Nav2 드라이버를 만들어 돌려주는 인자 없는 함수.
    반환값: 선택된 RobotDriver 구현.
    실패: 허용하지 않는 driver_type이면 ValueError를 던진다. 조용히 Mock으로
        대체하지 않는다.
    """
    if driver_type == DRIVER_TYPE_MOCK:
        return create_mock()
    if driver_type == DRIVER_TYPE_NAV2:
        return create_nav2()
    raise ValueError(
        f"unknown driver_type '{driver_type}'; "
        f"use '{DRIVER_TYPE_MOCK}' or '{DRIVER_TYPE_NAV2}'"
    )
