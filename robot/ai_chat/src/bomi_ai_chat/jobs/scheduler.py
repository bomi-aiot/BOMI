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
from bomi_ai_chat.localstore import runtime as runtime_store
from bomi_ai_chat.notify import BackendGuardianNotifier

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
        # ★ 실제 채널을 여기서 붙인다 (S15P11E102-232).
        #
        #   기본값은 LoggingGuardianNotifier 라 T1 이 로그로만 나가고 아무에게도
        #   도달하지 않는다. 그 상태로 배포하면 큐는 정상으로 보이고 보호자는
        #   아무것도 못 받는다 — 조용한 실패의 교과서적인 모양이다.
        _guard(ticks.outbox_flush, BackendGuardianNotifier(senior_id)),
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
    scheduler.add_job(
        # ticks.contract_tick 을 바로 넘기지 않는다 — 아래 _contract_tick_job 참고.
        # add_job 에 넘긴 인자는 '등록 시점'에 고정되므로, senior_id 를 바로 넘기는 건
        # 괜찮아도(바뀌지 않는다) conversation_id 를 등록 시점에 넘기면 그 뒤로 열리는
        # 새 대화를 영원히 못 본다 (S15P11E102-306).
        _guard(_contract_tick_job, senior_id),
        "interval",
        # 침묵 틱보다 훨씬 뜸하다. 계약 대화는 급하지 않고, 매 분 백엔드에
        # "물을 것 있나요"를 묻는 것은 네트워크와 배터리 낭비다.
        seconds=policy.CONTRACT_TICK_INTERVAL_SEC,
        id="contract_tick",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        # T3 동의 질문도 급하지 않다 — contract_tick 과 같은 주기를 쓴다
        # (S15P11E102-253). conversation_id 문제는 없다 — consent_tick 은
        # runtime_store 에서 '지금' 값을 직접 읽는다(contract_tick 과 달리
        # 인자로 받지 않는다).
        _guard(ticks.consent_tick, senior_id),
        "interval",
        seconds=policy.CONTRACT_TICK_INTERVAL_SEC,
        id="consent_tick",
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        # 사실 추출도 급하지 않다 (S15P11E102-255). 어제 나눈 이야기가 오늘
        # 기억이 되어도 문제 없고, 이 틱마다 LLM 호출이 최대
        # policy.EXTRACTION_FLUSH_BATCH_SIZE 번 붙으므로 침묵 틱(60초)만큼
        # 자주 돌릴 이유가 없다.
        _guard(ticks.extraction_flush, senior_id),
        "interval",
        seconds=policy.EXTRACTION_FLUSH_INTERVAL_SEC,
        id="extraction_flush",
        coalesce=True,
        max_instances=1,
    )

    logger.info(
        "scheduler built: silence/door=%ds outbox=%ds",
        policy.SILENCE_TICK_INTERVAL_SEC,
        policy.OUTBOX_FLUSH_INTERVAL_SEC,
    )
    return scheduler


def _contract_tick_job(senior_id: str) -> None:
    """contract_tick 을 부르되, '지금' 열려 있는 대화 id 를 매 호출마다 새로 읽는다.

    왜 등록 시점에 한 번만 넘기면 안 되는가  (S15P11E102-306)
        scheduler.add_job 에 넘기는 함수 인자는 등록 시점에 고정된다. 대화는
        시간이 흐르며 열리고 닫히므로(policy.CONVERSATION_BOUNDARY_IDLE_SEC), 등록
        시점의 conversation_id 를 그대로 굳히면 그 뒤에 새로 열린 대화에는 "한
        대화에 활성 후보 하나" 규칙(CLAUDE.md §12)이 영영 적용되지 않는다.

    왜 그래프 checkpoint 가 아니라 runtime_store 를 읽는가
        스케줄러는 별도 스레드에서 돌고 그래프 state 를 직접 볼 수 없다.
        graph/ingress._conversation_boundary 와 graph/build.memory_write 가 매 턴
        conversation_id 를 runtime_store 에도 찍어 둔다(last_spoke_at 과 같은 이유,
        build.py 참고) — 여기서는 그 사본을 읽는다.

    누가 호출하는가
        build_scheduler 가 등록한 contract_tick 작업, 그리고 run_all_ticks_once
        (압축 시계 경로).
    """
    conversation_id = runtime_store.load(senior_id).get("conversation_id")
    ticks.contract_tick(senior_id, conversation_id=conversation_id)


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
    _guard(_contract_tick_job, senior_id)()
    _guard(ticks.consent_tick, senior_id)()
    _guard(ticks.extraction_flush, senior_id)()
    for tick in (ticks.silence_tick, ticks.door_watch_tick):
        _guard(tick, senior_id, app)()
    _guard(ticks.outbox_flush)()
