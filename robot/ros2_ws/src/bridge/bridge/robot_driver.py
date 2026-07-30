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
