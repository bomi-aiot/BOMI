"""드라이버 선택 로직(create_driver)을 검증하는 단위 테스트다.

실제 드라이버 대신 Fake 팩터리를 주입하므로 ROS 2 없이 실행한다. Nav2 팩터리는
nav2를 골랐을 때만 호출되어야 한다(잘못된 값에서 Nav2 자원을 만들지 않는지 확인).
"""

from bridge.robot_driver import (
    DRIVER_TYPE_FORWARD_TEST,
    DRIVER_TYPE_MOCK,
    DRIVER_TYPE_NAV2,
    create_driver,
)
import pytest


class _Recorder:
    """호출 여부를 기록하고 정해진 값을 돌려주는 Fake 팩터리다."""

    def __init__(self, produced: str) -> None:
        self.called = False
        self._produced = produced

    def __call__(self) -> str:
        self.called = True
        return self._produced


def test_mock_type_creates_mock_and_skips_nav2() -> None:
    create_mock = _Recorder("mock-driver")
    create_nav2 = _Recorder("nav2-driver")

    result = create_driver(
        DRIVER_TYPE_MOCK,
        create_mock=create_mock,
        create_nav2=create_nav2,
        create_forward_test=_Recorder("forward-driver"),
    )

    assert result == "mock-driver"
    assert create_mock.called is True
    assert create_nav2.called is False


def test_nav2_type_creates_nav2_and_skips_mock() -> None:
    create_mock = _Recorder("mock-driver")
    create_nav2 = _Recorder("nav2-driver")

    result = create_driver(
        DRIVER_TYPE_NAV2,
        create_mock=create_mock,
        create_nav2=create_nav2,
        create_forward_test=_Recorder("forward-driver"),
    )

    assert result == "nav2-driver"
    assert create_nav2.called is True
    assert create_mock.called is False


def test_default_behaviour_uses_mock() -> None:
    # 노드 기본 파라미터가 mock이므로, mock 선택이 기존 동작을 유지하는지 확인.
    create_mock = _Recorder("mock-driver")
    create_nav2 = _Recorder("nav2-driver")

    result = create_driver(
        DRIVER_TYPE_MOCK,
        create_mock=create_mock,
        create_nav2=create_nav2,
        create_forward_test=_Recorder("forward-driver"),
    )

    assert result == "mock-driver"


def test_unknown_type_raises_and_creates_nothing() -> None:
    create_mock = _Recorder("mock-driver")
    create_nav2 = _Recorder("nav2-driver")

    with pytest.raises(ValueError):
        create_driver(
            "bogus",
            create_mock=create_mock,
            create_nav2=create_nav2,
            create_forward_test=_Recorder("forward-driver"),
        )

    assert create_mock.called is False
    assert create_nav2.called is False


def test_forward_test_type_creates_only_forward_driver() -> None:
    create_mock = _Recorder("mock-driver")
    create_nav2 = _Recorder("nav2-driver")
    create_forward = _Recorder("forward-driver")

    result = create_driver(
        DRIVER_TYPE_FORWARD_TEST,
        create_mock=create_mock,
        create_nav2=create_nav2,
        create_forward_test=create_forward,
    )

    assert result == "forward-driver"
    assert create_forward.called is True
    assert create_mock.called is False
    assert create_nav2.called is False
