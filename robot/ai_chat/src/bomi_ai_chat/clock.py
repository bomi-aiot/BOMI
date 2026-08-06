"""주입 가능한 시간 소스 — 이 프로젝트에서 실제 시계를 읽는 유일한 파일.

어디에 위치하는가
    타임스탬프를 비교하는 모든 코드가 이 파일을 거친다. 게이트의 쿨다운과
    quiet hours 판정, 발화 후보(SpeechProposal)의 TTL, 침묵 사다리,
    루틴 베이스라인 학습, 기억의 최신성 감쇠, 현관 이벤트 시각 정규화.

왜 존재하는가
    두 가지 이유가 있고, 두 번째가 더 중요하다.

    1. 테스트 가능성. 침묵 사다리를 실시간으로 검증하려면 테스트 한 번에 몇 시간을
       기다려야 한다. 일간 요약은 하루가 걸린다. 압축 시계가 있으면 10초에 하루가
       흐르고, 둘 다 평범한 단위 테스트가 된다.

    2. 시연 생존. 평가 때 "하루 종일 응답이 없으면 어떻게 되나요"를 반드시 묻는다.
       이 모듈이 없으면 답은 "네 시간 뒤에 다시 오세요"다. 있으면 다이얼만 돌리면 된다.

    나중에 넣는 건 훨씬 어렵다. 그때는 이미 수십 곳에서 시계를 직접 읽고 있고
    그걸 전부 찾아내야 한다. 그래서 이 파일이 가장 먼저 들어간다.

절대 규칙
    이 파일 밖에서 time.time() 이나 datetime.now() 를 호출하지 않는다.
    CLAUDE.md §15 와 §23 안티패턴 목록 참고. `clock` 을 import 해서 clock.now() 를 쓴다.

참고
    CLAUDE.md §15 (가짜 시계), §18 (APScheduler 에 수동 틱 경로가 필요한 이유)
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone


class Clock:
    """실제 시간. 운영 환경에서 쓰는 것.

    무엇을 하는가
        time.time() 을 감싸서, 호출하는 쪽이 "교체 가능한 객체"에 의존하게 만든다.

    누가 호출하는가
        모듈 하단의 `clock` 싱글톤을 통해 사실상 모든 코드가 간접 호출한다.

    반환값
        now() -> POSIX 타임스탬프(초, float). UTC 기준.

    주의사항
        타임스탬프는 UTC다. 어르신의 "하루 경계"는 app_user.time_zone 으로 계산하며
        이 값과 다르다. quiet hours 와 "오늘 메시지"는 로컬 시간 개념이므로,
        UTC 로 착각하면 몇 시간씩 틀리고 일부 사용자에게만 버그가 나타난다.
    """

    def now(self) -> float:
        return time.time()

    def now_dt(self) -> datetime:
        """같은 시점을 timezone 정보가 있는 datetime 으로. 날짜 계산용."""
        return datetime.fromtimestamp(self.now(), tz=timezone.utc)


class SimClock(Clock):
    """압축·조작 가능한 시간. 테스트와 시연 전용.

    무엇을 하는가
        실제 시간보다 빠르게 흐르는 가상 시점을 보고하며, 수동으로 점프시킬 수도 있다.

    왜 두 가지 방식인가
        `speed` 는 시연용이다. 그냥 켜두면 10초에 하루가 흘러서 발표 화면에서
        설득력이 있다. `advance()` 는 단위 테스트용이다. 기다림이 아예 없고,
        검증하고 싶은 순간으로 정확히 점프한다.

    인자
        start: 시작할 가상 POSIX 타임스탬프.
        speed: 배율. 1.0 이면 실시간. 8640.0 이면 하루가 10초.
        time_source: 실제 시간을 읽는 함수. 기본값이 정답이고, 테스트만 교체한다.
            speed 배율의 정확성을 검증할 때 실제로 10초를 기다리면 테스트가 10초
            느려지고 머신 부하에 따라 흔들린다. 이 이음새가 있으면 "실제 10초가
            지났다면"을 즉시, 결정적으로 재현할 수 있다. http.py 와 stt/client.py 가
            monotonic 을 주입받는 것과 같은 관례다.

    주의사항
        - APScheduler 는 여전히 '실제' 시간에 발동한다. SimClock 을 빠르게 해도
          스케줄 작업이 빨라지지 않는다. 테스트는 jobs/ticks.py 의 틱 함수를 직접
          호출해야 한다. CLAUDE.md §15 참고.
        - 다른 기계에서 온 타임스탬프(예: 현관 라즈베리파이)와 섞지 않는다.
          들어오는 이벤트는 도착 시점에 clock.now() 로 정규화한다. 그러지 않으면
          두 개의 다른 시간축이 한 계산에 섞인다.
    """

    def __init__(
        self,
        start: float,
        speed: float = 1.0,
        time_source: Callable[[], float] = time.time,
    ):
        self._time_source = time_source
        self._real_start = time_source()
        self._sim_start = start
        self.speed = speed

    def now(self) -> float:
        elapsed_real = self._time_source() - self._real_start
        return self._sim_start + elapsed_real * self.speed

    def advance(self, seconds: float) -> None:
        """가상 시계를 앞으로 점프시킨다. 즉시, sleep 없음."""
        self._sim_start += seconds


# 실제로 시간을 읽는 객체. install_clock() 이 교체하는 대상은 이 변수다.
# 밖에서 직접 참조하지 않는다. 아래 clock 프록시를 통해서만 접근한다.
_active: Clock = Clock()


class _ClockProxy(Clock):
    """항상 '지금 설치된' 시계로 위임하는 얇은 껍데기.

    왜 이 껍데기가 필요한가  ★ 이게 없으면 시계 주입이 조용히 작동하지 않는다
        소비자 모듈은 `from bomi_ai_chat.clock import clock` 으로 시계를 가져온다.
        파이썬의 이 구문은 '객체에 대한 참조를 그 모듈의 이름공간으로 복사'한다.
        따라서 install_clock() 이 이 파일의 전역 이름만 다시 묶으면, 이미 import 를
        끝낸 gate·ingress·triage·ticks 는 여전히 예전 객체를 들고 있다.

        결과는 최악의 형태다. 테스트가 SimClock 을 설치하고 통과했다고 믿지만
        실제로는 실제 시계가 쓰인다. 예외도 경고도 없다. 침묵 사다리를 압축 시계로
        검증했다는 확신만 남고 검증은 일어나지 않는다.

        그래서 소비자에게는 이 프록시를 넘긴다. 프록시는 절대 교체되지 않으므로
        복사된 참조도 항상 유효하고, 매 호출마다 현재 _active 로 위임한다.

    누가 호출하는가
        모든 소비자 모듈이 clock.now() / clock.now_dt() 형태로 간접 호출한다.

    주의사항
        SimClock 고유 메서드(advance, speed)는 __getattr__ 로 위임된다. 다만
        테스트에서는 SimClock 인스턴스를 직접 들고 sim.advance() 를 부르는 편이
        의도가 분명하다.
    """

    def now(self) -> float:
        return _active.now()

    def now_dt(self) -> datetime:
        return _active.now_dt()

    def __getattr__(self, name: str):
        # Clock 에 없는 이름(SimClock 의 advance, speed 등)만 여기까지 온다.
        return getattr(_active, name)


# 다른 모든 모듈이 import 하는 싱글톤.
#
# 프로세스 시작 시(또는 테스트 맨 앞에서) install_clock() 으로 교체한다.
# 함수마다 clock 을 인자로 넘기지 않고 모듈 전역 객체를 쓰는 이유는, 그 대안이
# 약 40개 호출 지점에 인자를 관통시켜서 뼈대를 읽을 수 없게 만들기 때문이다.
# 여기서 감수하는 대가는 "테스트가 끝나고 실제 시계를 복원해야 한다"는 점이다.
clock: Clock = _ClockProxy()


def install_clock(new_clock: Clock) -> Clock:
    """전역 시계를 교체한다. 이전 시계를 반환하므로 테스트가 복원할 수 있다.

    무엇을 하는가
        프록시가 위임하는 대상(_active)을 바꾼다. 이미 clock 을 import 해 둔
        모듈까지 즉시 영향을 받는다. 그게 프록시를 두는 이유다.

    누가 호출하는가
        시작 시점의 main/bootstrap, 그리고 테스트 fixture.

    반환값
        직전에 설치되어 있던 시계. 테스트는 이 값으로 원상복구한다.

    주의사항
        프록시 자신을 설치하면 위임이 자기 자신을 향해 무한 재귀한다. 실수로
        install_clock(clock) 을 부르는 경우이므로 즉시 실패시킨다.

    사용 예
        previous = install_clock(SimClock(start=clock.now(), speed=8640))
        ...
        install_clock(previous)
    """
    global _active
    if isinstance(new_clock, _ClockProxy):
        raise ValueError(
            "install_clock() 에 프록시를 설치할 수 없습니다. "
            "Clock 또는 SimClock 인스턴스를 넘기세요."
        )
    previous, _active = _active, new_clock
    return previous
