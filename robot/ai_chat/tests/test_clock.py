"""주입 가능한 시계와 압축 시계(SimClock) 검증.

무엇을 확인하는가
    1. install_clock() 이 '이미 import 를 끝낸' 모듈까지 실제로 영향을 주는가.
    2. SimClock(speed=8640) 이 실제 10초에 하루를 흘리는가.
    3. advance() 로 기다림 없이 원하는 시점으로 점프할 수 있는가.

왜 1번이 가장 중요한가
    소비자 모듈은 `from bomi_ai_chat.clock import clock` 으로 시계를 가져오는데,
    이 구문은 객체 참조를 복사한다. 그래서 전역 이름만 다시 묶는 순진한 구현은
    테스트가 SimClock 을 설치해도 실제 시계가 쓰이게 만든다. 예외도 경고도 없이
    "압축 시계로 검증했다"는 착각만 남는다. clock.py 의 프록시가 그것을 막는다.

참고
    CLAUDE.md §15 (가짜 시계), §23 (안티패턴 목록)
"""

import pytest

from bomi_ai_chat.clock import Clock, SimClock, clock, install_clock
from bomi_ai_chat.graph import gate

# 하루를 10초에 흘리는 배율. 86400초 / 10초 = 8640.
DAY_SEC = 86_400.0
DEMO_SPEED = 8640.0


@pytest.fixture
def restore_clock():
    """테스트가 바꾼 전역 시계를 반드시 원상복구한다.

    시계는 모듈 전역이므로 복원하지 않으면 이후 테스트가 가짜 시계를 물려받는다.
    """
    # install_clock 은 '직전에 설치되어 있던 시계'를 반환한다. 그것이 현재 시계를
    # 알아낼 수 있는 유일한 경로라서, 한 번 설치했다가 곧바로 되돌려 원본을 확보한다.
    original = install_clock(Clock())
    install_clock(original)
    yield
    install_clock(original)  # 테스트가 무엇을 설치했든 되돌린다


class FrozenRealTime:
    """SimClock 이 읽는 '실제 시간'을 테스트가 통제하기 위한 대역.

    왜 필요한가
        speed 배율의 정확성을 실제로 10초 기다려서 확인하면 테스트가 10초 느려지고,
        머신 부하에 따라 흔들린다. 실제 시간 소스만 고정하면 같은 계산을 즉시,
        그리고 결정적으로 검증할 수 있다.
    """

    def __init__(self, start: float):
        self._value = start

    def __call__(self) -> float:
        return self._value

    def elapse(self, seconds: float) -> None:
        self._value += seconds


def test_install_clock_reaches_modules_that_already_imported_it(restore_clock):
    """이미 import 를 끝낸 소비자도 교체된 시계를 본다.

    이 테스트가 깨지면 시계 주입 전체가 무의미해진다. 다른 모든 시간 관련
    테스트가 조용히 실제 시계로 돌아간다.
    """
    install_clock(SimClock(start=1_000.0, speed=1.0))

    # 이 파일이 import 한 clock 도, gate 모듈이 자기 이름공간에 복사해 둔 clock 도
    # 같은 가상 시점을 봐야 한다.
    assert clock.now() == pytest.approx(1_000.0, abs=1.0)
    assert gate.clock.now() == pytest.approx(1_000.0, abs=1.0)


def test_sim_clock_flows_one_day_in_ten_real_seconds(restore_clock):
    """SimClock(speed=8640) 은 실제 10초에 하루를 흘린다. (완료 조건)

    실제로 10초를 기다리지 않는다. SimClock 이 읽는 실제 시간 소스만 주입해서
    "실제 10초가 지났다면"을 즉시, 결정적으로 재현한다.
    """
    real_time = FrozenRealTime(start=50_000.0)
    start = 1_700_000_000.0

    sim = SimClock(start=start, speed=DEMO_SPEED, time_source=real_time)
    install_clock(sim)

    assert clock.now() == pytest.approx(start)
    day_before = clock.now_dt().date()

    real_time.elapse(10.0)  # 실제 10초 경과

    elapsed_sim = clock.now() - start
    assert elapsed_sim == pytest.approx(DAY_SEC), (
        f"실제 10초에 하루(86400초)가 흘러야 하는데 {elapsed_sim}초가 흘렀다"
    )

    # 날짜 경계도 정확히 하루 넘어가야 한다. 타임스탬프만 맞고 날짜 계산이 어긋나면
    # 일일 요약이 엉뚱한 날짜에 묶인다.
    assert (clock.now_dt().date() - day_before).days == 1


def test_sim_clock_speed_scales_proportionally(restore_clock):
    """중간 시점도 배율대로 흐른다 — 끝점만 맞는 구현을 걸러낸다."""
    real_time = FrozenRealTime(start=0.0)
    start = 1_700_000_000.0

    sim = SimClock(start=start, speed=DEMO_SPEED, time_source=real_time)
    install_clock(sim)

    real_time.elapse(2.5)  # 실제 2.5초 = 하루의 1/4

    assert clock.now() - start == pytest.approx(DAY_SEC / 4)


def test_advance_jumps_without_waiting(restore_clock):
    """advance() 는 sleep 없이 원하는 시점으로 즉시 점프한다.

    단위 테스트에서는 speed 보다 이 방식이 낫다. 실제 경과 시간에 의존하지 않아
    결과가 머신 부하에 흔들리지 않는다.
    """
    sim = SimClock(start=1_700_000_000.0)
    install_clock(sim)
    before = clock.now()

    sim.advance(3 * 3600)  # 침묵 사다리 1단계 임계치만큼 점프

    assert clock.now() - before == pytest.approx(3 * 3600, abs=1.0)


def test_cooldown_gate_follows_the_injected_clock(restore_clock):
    """실제 소비자(쿨다운 게이트)가 압축 시계를 따라 판정을 바꾼다.

    시계 주입이 '값을 바꾸는 것'에서 멈추지 않고 실제 판단까지 흐르는지 확인한다.
    이것이 이후 침묵 사다리·일일 요약 검증의 토대가 된다.
    """
    from bomi_ai_chat import policy

    sim = SimClock(start=1_700_000_000.0)
    install_clock(sim)

    state = {"last_spoke_at": clock.now()}
    assert gate.is_in_cooldown(state) is True, "방금 말했으므로 쿨다운 중이어야 한다"

    # 쿨다운이 끝나는 시점을 넘겨서 점프한다. 임계치는 policy 에서 읽는다.
    # 함수 본문이나 테스트에 숫자를 박으면 정책을 바꿀 때 여기가 조용히 틀어진다.
    sim.advance(policy.COOLDOWN_SEC + 1.0)

    assert gate.is_in_cooldown(state) is False, "쿨다운이 지났으므로 통과해야 한다"


def test_installing_the_proxy_itself_fails_loudly(restore_clock):
    """프록시를 설치하려는 시도는 즉시 실패한다.

    위임이 자기 자신을 향하면 무한 재귀가 되고, 스택 오버플로는 원인을 짚기 어렵다.
    """
    with pytest.raises(ValueError, match="프록시를 설치할 수 없습니다"):
        install_clock(clock)
