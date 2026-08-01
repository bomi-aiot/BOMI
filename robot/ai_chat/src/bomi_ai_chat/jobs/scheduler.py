"""주기 작업 배선 — 스케줄러는 '제안'만 넣고 직접 말하지 않는다.

이 파일의 단 하나의 규칙
    여기 등록된 어떤 작업도 발화를 만들지 않는다. 전부 큐에 제안을 넣을 뿐이고,
    말할지 여부는 게이트가 정한다 (CLAUDE.md §7).

    이 규칙이 없으면 "왜 로봇이 새벽 3시에 말했는가"에 답할 수 없다. 스케줄러가
    직접 말하기 시작하면 quiet hours 도 쿨다운도 우회되고, 그 우회는 코드 어디에도
    적히지 않는다.

왜 수동 틱 경로가 따로 있는가  ★ 중요
    APScheduler 는 '실제' 시간에 발동한다. SimClock(speed=8640) 을 끼워도 스케줄
    작업이 빨라지지 않는다. 그래서 압축 시계로 하루를 흘리는 시연·테스트에서는
    스케줄러를 쓰지 않고 tick 함수를 직접 부른다.

    두 경로를 처음부터 함께 설계해야 한다. 나중에 끼워 넣는 것은 훨씬 어렵다
    (CLAUDE.md §15).

참고
    CLAUDE.md §7 (게이트), §15 (시계 주입), §18 (틱 주기가 곧 전력)
"""

from __future__ import annotations

import logging

from bomi_ai_chat import policy
from bomi_ai_chat.jobs import ticks

logger = logging.getLogger(__name__)


def build_scheduler(senior_id: str, app=None):
    """APScheduler 를 만들고 주기 작업을 등록한다. 시작하지는 않는다.

    인자
        app: 컴파일된 그래프. 침묵 사다리와 현관 감시가 능동 턴을 돌릴 때 쓴다.
            None 이면 틱들이 제안을 큐에 넣어두기만 하고, 다음 능동 턴에서
            게이트가 집어간다.

    무엇을 하는가
        틱 함수들을 policy 의 주기로 등록한다. 주기는 함수에 박지 않고 policy 에서
        읽는다 — 배터리 구동이라 틱 주기가 곧 전력이고, 튜닝 대상이기 때문이다.

    누가 호출하는가
        부트스트랩. 테스트는 부르지 않는다(아래 run_all_ticks_once 를 쓴다).

    반환값
        시작되지 않은 BackgroundScheduler.

    주의사항
        - APScheduler 를 선택적 의존으로 둔다. 이 모듈을 import 하는 것만으로
          실패하면, 스케줄러가 필요 없는 테스트까지 끌려 들어간다.
        - 작업이 예외를 던져도 스케줄러가 그 작업을 죽이지 않게 한다. 틱 하나가
          죽으면 그 이후로 그 감시가 영원히 멈추는데, 멈춘 것이 침묵 사다리라면
          아무도 모르는 사이에 안전 감시가 꺼진다.
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        _guard(ticks.silence_tick, senior_id, app),
        "interval",
        seconds=policy.SILENCE_TICK_INTERVAL_SEC,
        id="silence_tick",
        # 밀린 실행을 몰아서 돌리지 않는다. 절전이나 일시 정지 후 사다리가 한꺼번에
        # 세 칸 올라가면 멀쩡한 어르신에게 프로브가 연달아 나간다.
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        _guard(ticks.door_watch_tick, senior_id, app),
        "interval",
        seconds=policy.SILENCE_TICK_INTERVAL_SEC,
        id="door_watch_tick",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        _guard(ticks.outbox_flush),
        "interval",
        seconds=policy.OUTBOX_FLUSH_INTERVAL_SEC,
        id="outbox_flush",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        _guard(ticks.schedule_tick, senior_id),
        "interval",
        seconds=policy.SILENCE_TICK_INTERVAL_SEC,
        id="schedule_tick",
        coalesce=True,
        max_instances=1,
    )

    logger.info(
        "scheduler built: silence/door=%ds outbox=%ds",
        policy.SILENCE_TICK_INTERVAL_SEC,
        policy.OUTBOX_FLUSH_INTERVAL_SEC,
    )
    return scheduler


def _guard(func, *args):
    """틱이 예외로 죽지 않게 감싼다.

    스케줄러에서 예외가 올라가면 그 작업이 제거되거나 로그 한 줄만 남고 조용히
    멈춘다. 멈춘 것이 침묵 사다리면 안전 감시가 꺼진 채로 계속 돌아간다.
    """

    def run():
        try:
            func(*args)
        except Exception:  # noqa: BLE001 - 틱이 죽으면 그 감시가 영원히 멈춘다
            logger.exception("scheduled tick failed: %s", getattr(func, "__name__", func))

    return run


def run_all_ticks_once(senior_id: str, app=None) -> None:
    """모든 틱을 한 번씩 직접 실행한다. 압축 시계 경로.

    왜 필요한가
        APScheduler 는 실제 시간에 발동하므로 SimClock 을 빠르게 해도 소용이 없다.
        하루를 10초에 흘리는 시연에서는 시계를 advance() 하고 이 함수를 부른다.

    누가 호출하는가
        테스트, 그리고 압축 시계 시연 스크립트.

    사용 예
        sim = SimClock(start=..., speed=0.0)
        install_clock(sim)
        for _ in range(24):
            sim.advance(3600)
            run_all_ticks_once("senior-1")
    """
    _guard(ticks.schedule_tick, senior_id)()
    for tick in (ticks.silence_tick, ticks.door_watch_tick):
        _guard(tick, senior_id, app)()
    _guard(ticks.outbox_flush)()
