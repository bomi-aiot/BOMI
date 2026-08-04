"""성능 저하 순서 — 압박이 올 때 무엇을 먼저 버리는가. (S15P11E102-212)

왜 존재하는가
    §18 이 저하 순서를 미리 정해 두라고 요구한다. 순서를 미리 못 정해 두면 압박이
    올 때 즉흥적으로 버리게 되고, 즉흥적으로 버리면 하필 안전 경로를 버린다.

    ★ 212 전까지 policy.DEGRADATION_ORDER 는 '문자열 네 개짜리 목록'이었고, 그것을
      읽는 코드가 하나도 없었다. 주석에는 "압박 상황에서는 낮춘 값이 들어온다"고
      적혀 있었지만 넣는 사람이 없었다. 이 모듈이 그 넣는 사람이다.

무엇을 버리는가 (policy.DEGRADATION_ORDER 순서)
    1  reduce_memory_top_k   맥락이 얕아진다. 대화는 계속된다
    2  disable_document_rag  복지제도 조회 중단. info 턴이 얕아진다
    3  disable_ambient       잡담 중단. 기능적 발화만 남는다
    4  simplify_probes       생성 대신 캐시된 음성

    4번은 이미 기본 동작이다. 침묵 사다리의 프로브는 처음부터 고정 문구 + 캐시
    오디오이고 생성을 쓰지 않는다(jobs/ticks.py `_PROBES`). 그래서 이 모듈은 1~3만
    실제로 조작하고, 4번은 '이미 그렇다'는 사실을 확인만 한다.

★ 절대 저하되지 않는 것
    침묵 사다리, 안전 트리아지, 발신 큐(outbox). 이 모듈은 그 세 경로를 아예
    쳐다보지 않는다 — 조회 함수도 제공하지 않는다. 제공하면 언젠가 누가 쓴다.
    "압박이 심하니 안전 감시를 줄이자"는 이 제품에서 성립할 수 없는 문장이다.

무엇으로 판단하는가  ★ 이것은 이 티켓의 가정이며 리뷰 대상이다
    턴 지연이다. §18 은 "자원 또는 네트워크 압박"이라고만 쓰여 있고, 우리가 실제로
    가지고 있는 신호는 두 개다 — 턴 왕복 시간(TurnTimer)과 백엔드 도달 실패
    (ctx_is_cached). 메모리·CPU 는 아직 재는 곳이 없다.

    턴 지연을 고른 이유는 그것이 어르신이 실제로 느끼는 것이기 때문이다. 8GB 램이
    얼마나 찼는지는 어르신에게 아무 의미가 없고, 대답이 4초 뒤에 오는 것은 의미가 있다.

상태는 메모리에만 있다
    재부팅하면 0 단계로 돌아간다. 의도한 것이다 — 저하는 '지금 느린 상황'에 대한
    반응이고, 어제 느렸다는 사실이 오늘의 첫 턴을 얕게 만들 이유는 없다.

참고
    CLAUDE.md §18(성능 저하 순서), policy.DEGRADATION_ORDER
"""

from __future__ import annotations

import logging
import threading

from bomi_ai_chat import policy

logger = logging.getLogger(__name__)

# 저하 단계. 0 은 정상이고, policy.DEGRADATION_ORDER 의 길이가 최대다.
_level = 0

# 연속 카운터. 한 번 느린 턴으로 단계를 올리지 않는다 — 네트워크는 자주 한 번씩 튄다.
_slow_streak = 0
_fast_streak = 0

# 틱 스레드(스케줄러)와 대화 스레드가 함께 읽고 쓴다. 경합 자체는 치명적이지 않지만
# (단계가 한 칸 늦게 반영될 뿐), 카운터가 엉키면 단계가 오르내리기를 반복한다.
_lock = threading.Lock()


def level() -> int:
    """현재 저하 단계. 0 이면 정상."""
    return _level


def active_steps() -> list[str]:
    """지금 적용 중인 저하 항목들. 로그와 테스트를 위한 것이다."""
    return policy.DEGRADATION_ORDER[:_level]


def reset() -> None:
    """정상으로 되돌린다. 테스트와 기동 시에 쓴다."""
    global _level, _slow_streak, _fast_streak
    with _lock:
        _level = 0
        _slow_streak = 0
        _fast_streak = 0


def note_turn_latency(seconds: float) -> None:
    """턴 하나의 왕복 시간을 알려준다. 단계가 오르거나 내려갈 수 있다.

    누가 호출하는가
        graph/turn.py 의 run_user_turn. 턴이 끝날 때마다.

    왜 연속으로 세는가
        네트워크는 자주 한 번씩 튄다. 한 번 느렸다고 맥락을 얕게 만들면, 어르신은
        와이파이가 잠깐 흔들린 대가로 그날의 기억을 잃는다.

    왜 내려가는 것도 세는가
        올라간 단계가 스스로 내려오지 않으면, 잠깐의 혼잡 때문에 재부팅까지 계속
        얕은 대화를 하게 된다. 저하는 상태가 아니라 반응이어야 한다.
    """
    global _level, _slow_streak, _fast_streak

    over_budget = seconds > policy.TURN_LATENCY_BUDGET_SEC
    with _lock:
        if over_budget:
            _fast_streak = 0
            _slow_streak += 1
            if _slow_streak >= policy.DEGRADE_AFTER_SLOW_TURNS:
                _slow_streak = 0
                _escalate(f"{seconds:.2f}s turns")
        else:
            _slow_streak = 0
            _fast_streak += 1
            if _fast_streak >= policy.RECOVER_AFTER_FAST_TURNS:
                _fast_streak = 0
                _deescalate()


def _escalate(reason: str) -> None:
    """한 칸 내려간다. 호출자가 _lock 을 잡고 있어야 한다."""
    global _level
    if _level >= len(policy.DEGRADATION_ORDER):
        return
    _level += 1
    # 조용히 저하되면 "왜 로봇이 옛날 얘기를 안 하지"를 나중에 추적할 수 없다.
    logger.warning("degrading to level %d (%s): dropping %s",
                   _level, reason, policy.DEGRADATION_ORDER[_level - 1])


def _deescalate() -> None:
    """한 칸 올라온다. 호출자가 _lock 을 잡고 있어야 한다."""
    global _level
    if _level == 0:
        return
    restored = policy.DEGRADATION_ORDER[_level - 1]
    _level -= 1
    logger.info("recovered to level %d: restoring %s", _level, restored)


# ─────────────────────────────────────────────────────────────────────────────
# 조회 — 각 단계가 실제로 무엇을 바꾸는가
# ─────────────────────────────────────────────────────────────────────────────


def _dropped(step: str) -> bool:
    return step in active_steps()


def memory_top_k() -> int:
    """이번 턴에 요청할 기억 개수.

    1단계에서 줄어든다. 대화가 얕아지지만 계속된다 — 가장 먼저 버리는 이유다.
    """
    return (policy.MEMORY_TOP_K_DEGRADED if _dropped("reduce_memory_top_k")
            else policy.MEMORY_TOP_K)


def documents_allowed() -> bool:
    """문서 코퍼스(복지제도·FAQ)를 조회해도 되는가.

    2단계에서 끊는다. 기억보다 나중인 이유: 기억은 매 턴 쓰이고 문서는 info 턴에서만
    쓰인다. 덜 자주 쓰이는 것을 나중에 버리는 것이 아니라, **더 자주 쓰이는 것을
    먼저 얕게** 만드는 것이다 — 기억은 줄여도 남고, 문서는 끊으면 없다.
    """
    return not _dropped("disable_document_rag")


def ambient_allowed() -> bool:
    """잡담을 꺼내도 되는가.

    3단계에서 끊는다. 기능적 발화(복약·안전)는 그대로 남는다.
    """
    return not _dropped("disable_ambient")


def probes_simplified() -> bool:
    """프로브가 생성 대신 캐시 음성을 쓰는가.

    ★ 항상 True 다. 침묵 사다리의 프로브는 처음부터 고정 문구 + 캐시 오디오이고
      생성을 쓰지 않는다. DEGRADATION_ORDER 의 4번째 항목은 '저하 시 그렇게 하라'가
      아니라 '이미 그렇다'는 확인이다.

      그래서 저하 단계와 무관하게 True 다. False 를 돌려줄 수 있게 만들면, 언젠가
      누가 "평상시에는 프로브도 생성하자"로 읽는다 — 그러면 네트워크가 끊긴 순간
      생존 확인이 나가지 않는다.
    """
    return True
