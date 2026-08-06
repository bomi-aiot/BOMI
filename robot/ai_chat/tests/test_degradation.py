"""성능 저하 순서 — S15P11E102-212 완료 조건.

무엇을 검증하는가
    §18 이 정한 저하 순서가 실제로 동작하는가. 그리고 **안전 경로가 절대 저하되지
    않는가.**

이 파일이 존재하는 이유  ★
    212 전까지 `policy.DEGRADATION_ORDER` 는 문자열 네 개짜리 목록이었고, 그것을
    읽는 코드가 하나도 없었다. `context.py` 주석은 "압박 상황에서는 낮춘 값이
    들어온다"고 말했지만 넣는 사람이 없었다. 티켓은 "동작 검증"을 요구했는데,
    검증할 동작 자체가 없었다.

    이런 실패가 위험한 이유: 문서와 상수가 있으면 사람들은 그것이 동작한다고 믿는다.
    "저하 순서는 정해져 있습니다"라고 말할 수 있고, 그 문장은 사실이 아니다.

참고
    CLAUDE.md §18(성능 저하 순서), src/bomi_ai_chat/degradation.py
"""

import pytest

from bomi_ai_chat import degradation, policy


@pytest.fixture(autouse=True)
def clean_slate():
    degradation.reset()
    yield
    degradation.reset()


def slow_turns(count):
    for _ in range(count):
        degradation.note_turn_latency(policy.TURN_LATENCY_BUDGET_SEC + 1.0)


def fast_turns(count):
    for _ in range(count):
        degradation.note_turn_latency(0.2)


# ── 순서 ────────────────────────────────────────────────────────────────────


def test_the_order_is_the_one_policy_declares():
    """★ 저하 순서는 코드가 아니라 policy.DEGRADATION_ORDER 가 정한다.

    순서를 함수 안에 박으면, 순서를 바꾸려는 사람이 policy 를 고치고 아무 일도
    일어나지 않는 것을 보게 된다.
    """
    for step in range(1, len(policy.DEGRADATION_ORDER) + 1):
        degradation.reset()
        slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS * step)
        assert degradation.active_steps() == policy.DEGRADATION_ORDER[:step]


def test_memory_shallows_first_and_conversation_continues():
    """1단계 — 맥락이 얕아진다. 대화는 계속된다. 그래서 가장 먼저 버린다."""
    assert degradation.memory_top_k() == policy.MEMORY_TOP_K

    slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS)

    assert degradation.level() == 1
    assert degradation.memory_top_k() == policy.MEMORY_TOP_K_DEGRADED
    assert degradation.memory_top_k() < policy.MEMORY_TOP_K, (
        "저하 값이 평상시 값보다 크거나 같으면 저하가 아니다")
    # 아직 문서도 잡담도 살아 있다.
    assert degradation.documents_allowed() is True
    assert degradation.ambient_allowed() is True


def test_documents_go_before_small_talk():
    """2단계 — 문서 RAG 를 끊는다. 잡담은 아직 남는다."""
    slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS * 2)

    assert degradation.documents_allowed() is False
    assert degradation.ambient_allowed() is True


def test_small_talk_is_the_third_thing_to_go():
    """3단계 — 잡담을 끊는다. 기능적 발화는 남는다."""
    slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS * 3)

    assert degradation.ambient_allowed() is False


def test_the_level_never_runs_past_the_end_of_the_list():
    """계속 느려도 목록 밖으로 나가지 않는다. IndexError 로 턴을 죽일 수 없다."""
    slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS * 20)

    assert degradation.level() == len(policy.DEGRADATION_ORDER)
    assert degradation.active_steps() == policy.DEGRADATION_ORDER


# ── ★ 안전 경로는 저하되지 않는다 ───────────────────────────────────────────


def test_probes_are_always_simplified_never_generated():
    """★★ 4번 항목은 '저하 시 그렇게 하라'가 아니라 '이미 그렇다'는 확인이다.

    침묵 사다리의 프로브는 처음부터 고정 문구 + 캐시 오디오다. 여기서 False 가
    나올 수 있게 만들면 언젠가 누가 "평상시에는 프로브도 생성하자"로 읽고,
    그러면 네트워크가 끊긴 순간 생존 확인이 나가지 않는다 — 하필 가장 필요한 때.
    """
    assert degradation.probes_simplified() is True

    slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS * 20)

    assert degradation.probes_simplified() is True


def test_the_module_offers_no_way_to_weaken_safety():
    """★★★ 이 모듈은 안전 경로를 쳐다보지도 않는다.

    조회 함수를 제공하면 언젠가 누가 쓴다. "압박이 심하니 안전 감시를 줄이자"는
    이 제품에서 성립할 수 없는 문장이므로, 그 문장을 쓸 수 있는 도구를 두지 않는다.

    이 테스트는 API 표면을 고정한다. 여기에 함수를 추가하려면 이 테스트를 먼저
    고쳐야 하고, 그때 이 주석을 읽게 된다.
    """
    public = {name for name in dir(degradation) if not name.startswith("_")}
    # 모듈이 import 한 것들은 제외한다.
    public -= {"logging", "threading", "policy", "annotations", "logger"}

    assert public == {
        "level", "active_steps", "reset", "note_turn_latency",
        "memory_top_k", "documents_allowed", "ambient_allowed", "probes_simplified",
    }, ("저하 모듈에 새 조회가 생겼다. 그것이 침묵 사다리·트리아지·outbox 중 하나를 "
        "약하게 만드는 것이면 안 된다")


# ── 오르내림 ────────────────────────────────────────────────────────────────


def test_one_slow_turn_does_not_shallow_the_conversation():
    """★ 네트워크는 자주 한 번씩 튄다.

    한 번 느렸다고 맥락을 얕게 만들면, 어르신은 와이파이가 잠깐 흔들린 대가로
    그날의 기억을 잃는다.
    """
    slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS - 1)

    assert degradation.level() == 0


def test_a_fast_turn_resets_the_slow_streak():
    """느린 턴이 '연속'이어야 한다. 띄엄띄엄 느린 것은 저하 사유가 아니다."""
    slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS - 1)
    fast_turns(1)
    slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS - 1)

    assert degradation.level() == 0


def test_it_recovers_on_its_own():
    """★ 저하가 스스로 풀리지 않으면, 잠깐의 혼잡 때문에 재부팅까지 얕은 대화를 한다."""
    slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS)
    assert degradation.level() == 1

    fast_turns(policy.RECOVER_AFTER_FAST_TURNS)

    assert degradation.level() == 0
    assert degradation.memory_top_k() == policy.MEMORY_TOP_K


def test_recovery_is_slower_than_degradation():
    """★ 경계에서 오르내리기를 반복하면 로봇이 오늘따라 이상하다는 인상만 남는다.

    어떤 턴은 깊고 어떤 턴은 얕은 것이 계속 얕은 것보다 나쁘다 — 원인을 짐작할
    수 없기 때문이다.
    """
    assert policy.RECOVER_AFTER_FAST_TURNS > policy.DEGRADE_AFTER_SLOW_TURNS


def test_recovery_undoes_one_step_at_a_time():
    """한 번에 정상으로 뛰어오르지 않는다. 올라간 만큼 내려온다."""
    slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS * 3)
    assert degradation.level() == 3

    fast_turns(policy.RECOVER_AFTER_FAST_TURNS)
    assert degradation.level() == 2

    fast_turns(policy.RECOVER_AFTER_FAST_TURNS)
    assert degradation.level() == 1


def test_a_failed_turn_is_not_counted_as_a_fast_turn():
    """★ 예외로 0.1초에 끝난 턴이 '빠른 턴'으로 세어지면, 고장 중에 저하가 풀린다.

    turn.py 가 실패 경로에서 note_turn_latency 를 부르지 않는 것으로 지킨다.
    여기서는 그 계약을 문서화한다 — 부르기 시작하면 이 테스트가 근거가 된다.
    """
    import inspect

    from bomi_ai_chat.graph import turn

    source = inspect.getsource(turn.run_user_turn)
    before_error_return = source.split('intent="error"')[1].split("return {}")[0]

    assert "note_turn_latency" not in before_error_return, (
        "실패한 턴의 시간을 저하 판단에 넣으면 고장 중에 저하가 풀린다")


# ── 저하가 실제로 그래프에 반영되는가 ───────────────────────────────────────


def test_the_gate_stops_small_talk_when_degraded(frozen_clock):
    """★ 조회 함수가 True/False 를 잘 돌려주는 것만으로는 부족하다.

    게이트가 그것을 실제로 읽어야 한다. 212 전의 실패가 정확히 이 모양이었다 —
    상수는 있고 읽는 사람이 없었다.
    """
    from bomi_ai_chat.graph import gate

    frozen_clock(start=1_700_000_000.0)
    state = {
        "senior_id": "senior-1",
        "ctx": {},
        "proposals": [{"intent": "companion", "priority": "ambient", "seed": "심심하시죠"}],
    }

    assert gate.proactive_gate(state)["gate_decision"] == "speak"

    slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS * 3)

    assert gate.proactive_gate(state)["gate_decision"] == "silent"


def test_medication_still_speaks_when_small_talk_is_off(frozen_clock):
    """★ 저하는 잡담부터 버린다. 복약은 3단계에서도 나가야 한다.

    이것이 없으면 위 테스트는 "저하하면 아무 말도 안 한다"를 통과로 읽는다.
    """
    from bomi_ai_chat.graph import gate

    frozen_clock(start=1_700_000_000.0)
    slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS * 3)

    decision = gate.proactive_gate({
        "senior_id": "senior-1",
        "ctx": {},
        "proposals": [{"intent": "schedule", "priority": "medium", "seed": "약 드실 시간이에요"}],
    })

    assert decision["gate_decision"] == "speak"


def test_context_read_asks_for_fewer_memories_when_degraded(monkeypatch, tmp_path):
    """★ 1단계가 실제로 백엔드 호출의 top_k 를 바꾸는가."""
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))

    from bomi_ai_chat.backend_client import ContextResult
    from bomi_ai_chat.graph import context as context_node
    from bomi_ai_chat.localstore import db

    db.close_all()
    seen = []

    class Recording:
        def fetch_context(self, senior_id, **kwargs):
            seen.append(kwargs)
            return ContextResult(ctx={}, is_cached=False)

    context_node.set_client(Recording())
    try:
        context_node.context_read({"senior_id": "senior-1", "intent": "info"})
        assert seen[-1]["top_k"] == policy.MEMORY_TOP_K
        assert seen[-1]["documents"] is True

        slow_turns(policy.DEGRADE_AFTER_SLOW_TURNS * 2)

        context_node.context_read({"senior_id": "senior-1", "intent": "info"})
        assert seen[-1]["top_k"] == policy.MEMORY_TOP_K_DEGRADED
        assert seen[-1]["documents"] is False, (
            "2단계는 문서 조회를 끊는다. info 턴이 얕아지지만 대화는 계속된다")
    finally:
        context_node.set_client(None)
        db.close_all()
