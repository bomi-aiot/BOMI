"""자연스러움 회귀 세트 — S15P11E102-212.

이 파일이 하는 일
    CLAUDE.md §17 의 10개 항목을 '분위기'가 아니라 '다시 돌릴 수 있는 검사'로 고정한다.
    시나리오(어르신 발화)는 tests/scenarios/naturalness_v1.json 에 있고, 여기서는
    그것을 실제 그래프에 태워 결과를 확인한다.

왜 이 파일이 필요한가  ★
    §17 의 항목들은 이미 프롬프트 템플릿과 게이트에 들어가 있다. 그런데 **그것을
    지켜주는 것이 없다.** 누군가 system.md 에서 "못 알아들었으면 되묻습니다" 한 줄을
    지워도, 지금은 어떤 테스트도 실패하지 않는다. 예외도 나지 않는다. 로봇이 조금 더
    자신 있게 틀린 답을 하기 시작할 뿐이고, 그 변화는 실기에서 우연히 발견된다.

    프롬프트 문구는 이 제품의 동작이다. 동작은 테스트가 지킨다.

이 파일이 검증하지 '못하는' 것
    "따뜻한가", "자연스러운가"는 기계가 못 본다. 대역 LLM 은 우리가 정한 문장만
    돌려주므로, 여기서 확인하는 것은 **모델에게 무엇이 주어졌는가**와 **출력이 규칙을
    지켰는가**다. 실제 문장의 질은 233(실기)에서 사람이 듣고 판단한다.

    2번(이어짐), 10번(회상)은 의미 검색이 필요해 여기서 잴 수 없다. 조용히 빠지지
    않도록 test_blocked_criteria_are_declared_not_forgotten 이 그 사실을 고정한다.

참고
    CLAUDE.md §17(10개 항목), §14(발화 규칙), §16(프롬프트 조립)
    tests/scenarios/naturalness_v1.json (시나리오 데이터와 미측정 항목 선언)
"""

import json
from pathlib import Path

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.backend_client import ContextResult
from bomi_ai_chat.graph import build, gate, handlers, output
from bomi_ai_chat.graph import context as context_node
from bomi_ai_chat.graph.build import build_graph
from bomi_ai_chat.graph.turn import run_user_turn
from bomi_ai_chat.localstore import db

SENIOR = "senior-1"

SCENARIO_FILE = Path(__file__).parent / "scenarios" / "naturalness_v1.json"
SCENARIOS = json.loads(SCENARIO_FILE.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# 리플레이 하네스
# ─────────────────────────────────────────────────────────────────────────────


class ScriptedContextClient:
    """시나리오가 지정한 문맥을 그대로 돌려준다."""

    def __init__(self, ctx):
        self.ctx = ctx

    def fetch_context(self, senior_id, **kwargs):
        return ContextResult(ctx=self.ctx, is_cached=False)


class ScriptedLLM:
    """정해진 문장을 돌려주고, 받은 프롬프트를 전부 모은다.

    프롬프트를 모으는 것이 이 대역의 핵심이다. 출력의 질은 여기서 알 수 없지만,
    '모델이 무엇을 알고 있었는가'는 정확히 알 수 있다.
    """

    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def generate(self, text, weather_data=None):
        self.prompts.append(text)
        return self.reply


class NullHandle:
    def cancel(self):
        pass

    def remaining_sentences(self):
        return []


class CollectingPlayer:
    def __init__(self):
        self.spoken = []

    def speak_async(self, sentences):
        self.spoken.append(list(sentences))
        return NullHandle()


class NullConversationClient:
    def record_turn(self, senior_id, **fields):
        # (conversationId, messageId) 튜플 계약은 S15P11E102-306 이 세웠다.
        # 단일 문자열을 돌려주면 build.py._record_turn 의 튜플 언패킹이
        # "too many values to unpack" 으로 죽는다 — 그러면 memory_write 가
        # 터지고, 정작 이 파일이 재려는 '자연스러움'과 무관한 이유로 실패한다.
        return "conversation-1", "message-1"


DEFAULT_REPLY = "그러셨어요. 좀 더 말씀해 주시겠어요?"


def replay(scenario, tmp_path):
    """시나리오 하나를 실제 그래프에 태우고, 관찰한 것을 돌려준다.

    반환값
        (prompts, states) — 모델이 받은 프롬프트들과 각 턴의 최종 상태.

    주의사항
        외부 의존(백엔드·LLM·오디오)만 대역으로 바꾼다. 게이트·트리아지·인텐트 분류·
        정제는 전부 실제 코드가 돈다. 그것들이 이 파일이 지키려는 대상이다.
    """
    monkey_dir = tmp_path / "localstore"
    db.close_all()

    client = ScriptedContextClient(scenario.get("ctx") or {})
    llm = ScriptedLLM(scenario.get("llmReply") or DEFAULT_REPLY)
    player = CollectingPlayer()

    context_node.set_client(client)
    handlers.set_llm(llm)
    output.set_player(player)
    build.set_conversation_client(NullConversationClient())

    try:
        app = build_graph(checkpoint_path=str(tmp_path / "checkpoint.sqlite"))
        states = []
        repeats = scenario.get("repeatTurns", 1)
        proactive = scenario.get("proactive")
        for _ in range(repeats):
            if proactive:
                states.append(_run_proactive_turn(app, proactive))
            else:
                for utterance in scenario["turns"]:
                    states.append(run_user_turn(app, SENIOR, utterance))
        return llm.prompts, states
    finally:
        context_node.set_client(None)
        handlers.set_llm(None)
        output.set_player(None)
        build.set_conversation_client(None)
        db.close_all()
        assert monkey_dir or True  # noqa: PT018 - tmp_path 사용을 명시적으로 남긴다


def _run_proactive_turn(app, proactive: dict) -> dict:
    """능동 제안 하나를 실제 게이트에 태운다 (S15P11E102-256).

    무엇을 하는가
        jobs/ticks._invoke_proactive 와 같은 모양으로 trigger_type "proactive" 로
        그래프를 직접 부른다. proactive_gate 는 state["proposals"] 를 읽으므로
        localstore 에 미리 큐잉할 필요가 없다(graph/gate.py 참고).

    왜 이전에는 핸들러를 직접 불렀는가, 그리고 왜 이제 안 그러는가
        recent_phrasings 는 능동 턴에서 게이트 다음 context_read 가 채우는 값이다
        (graph/context.py._lookup_recent_phrasings). 예전에는 그 조회 코드가
        없었으므로 handle_companion 을 직접 불러 state 에 값을 수동으로 심어야
        했다. 배선이 끝난 지금 그 우회는 "이미 되어 있다"는 잘못된 인상을 남긴다
        — 실제로는 게이트가 그 값을 넣지 않았다(옛 docstring이 틀렸던 지점).
        이제는 그래프 전체(게이트 -> context_read -> handle_companion ->
        response_shaper -> memory_write)를 태워서 실제 배선을 검증한다.
    """
    proposal = {
        "intent": proactive.get("intent", "companion"),
        "priority": proactive.get("priority", "high"),
        "seed": proactive.get("seed", ""),
        "origin": proactive.get("origin", ""),
    }
    return app.invoke(
        {"trigger_type": "proactive", "senior_id": SENIOR, "proposals": [proposal]},
        {"configurable": {"thread_id": SENIOR}},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 시나리오 리플레이
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "scenario", SCENARIOS["scenarios"], ids=[s["id"] for s in SCENARIOS["scenarios"]])
def test_scenario(scenario, tmp_path, monkeypatch):
    """시나리오 하나를 돌리고 expect 를 확인한다.

    실패 메시지에 시나리오의 why 를 넣는다. "왜 이게 중요한가"를 테스트 코드에서
    찾아야 하면, 고치는 사람이 그냥 기대값을 낮추는 쪽을 고른다.
    """
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    prompts, states = replay(scenario, tmp_path)

    expect = scenario["expect"]
    why = scenario["why"]
    assert prompts, f"[{scenario['id']}] 모델이 한 번도 호출되지 않았다"

    if "intent" in expect:
        assert states[-1].get("intent") == expect["intent"], (
            f"[{scenario['id']}] 인텐트가 달라졌다. {why}")

    if "maxSentences" in expect:
        sentences = states[-1].get("sentences") or []
        assert len(sentences) <= expect["maxSentences"], (
            f"[{scenario['id']}] 문장이 {len(sentences)}개다. {why}")

    if expect.get("allPromptsIdentical"):
        # ★ 4번 항목의 실제 검사. 반복 횟수가 프롬프트에 새면 턴마다 달라진다.
        #   금지 문자열로 잡으려 하면 system.md 의 '금지 예시' 문장에 걸린다 —
        #   처음 작성했을 때 실제로 그렇게 실패했다.
        unique = set(prompts)
        assert len(unique) == 1, (
            f"[{scenario['id']}] {len(prompts)}번 물었는데 프롬프트가 "
            f"{len(unique)}종류다. 반복 횟수가 새고 있다. {why}")

    for needle in expect.get("promptContains", []):
        assert any(needle in prompt for prompt in prompts), (
            f"[{scenario['id']}] 프롬프트에 {needle!r} 가 없다. {why}")

    for needle in expect.get("promptExcludes", []):
        for index, prompt in enumerate(prompts):
            assert needle not in prompt, (
                f"[{scenario['id']}] {index + 1}번째 프롬프트에 {needle!r} 가 들어갔다. {why}")

    for needle in expect.get("responseExcludes", []):
        utterance = states[-1].get("final_utterance") or ""
        assert needle not in utterance, (
            f"[{scenario['id']}] 발화에 {needle!r} 가 들어갔다. {why}")


def test_the_scenario_file_covers_every_criterion_or_says_why_not():
    """★ 10개 항목이 전부 '측정' 또는 '왜 못 하는지'로 설명되어야 한다.

    이 확인이 없으면 항목이 조용히 사라진다. 시나리오를 하나 지우면 커버리지가
    줄어드는데, 테스트는 그대로 통과한다 — 남은 것들만 돌기 때문이다.
    """
    measured = {s["criterion"] for s in SCENARIOS["scenarios"]}
    declared = {b["criterion"] for b in SCENARIOS["notMeasurableHere"]}

    assert measured | declared == set(range(1, 11)), (
        f"§17 의 10개 항목 중 {sorted(set(range(1, 11)) - (measured | declared))} 번이 "
        "측정도 안 되고 '왜 못 하는지'도 적혀 있지 않다")


def test_blocked_criteria_are_declared_not_forgotten():
    """★ 막힌 항목은 사유와 선행 티켓을 함께 적어야 한다.

    "나중에 하자"만 적힌 항목은 나중에 아무도 찾지 못한다.
    """
    for blocked in SCENARIOS["notMeasurableHere"]:
        assert blocked["blockedBy"], f"항목 {blocked['criterion']} 에 선행이 비어 있다"
        assert len(blocked["why"]) > 40, (
            f"항목 {blocked['criterion']} 의 사유가 너무 짧다. "
            "무엇이 없어서 못 하는지 구체적으로 적는다")


def test_the_file_says_it_is_authored_not_recorded():
    """★ 이 세트가 실제 녹취가 아니라는 사실이 파일 안에 남아 있어야 한다.

    지어낸 문장으로 통과한 검사를 실측으로 읽으면, 실기에서 처음 드러난다.
    """
    note = " ".join(SCENARIOS["honestNote"])
    assert "실제 녹취" in note and "아닙니다" in note


# ─────────────────────────────────────────────────────────────────────────────
# 항목 6: 말 안 할 때를 안다
#
# 발화가 '없는' 것을 확인하는 항목이라 시나리오 파일로 표현할 수 없다. 게이트를
# 직접 돌린다.
# ─────────────────────────────────────────────────────────────────────────────


def _proposal(priority, **extra):
    return {"intent": "companion", "priority": priority, "seed": "심심하시죠", **extra}


# 서울 시각 03:00 / 14:00 에 해당하는 epoch. quiet hours 판정은 어르신의 '로컬'
# 시각으로 이뤄지므로(clock.now() 는 UTC), 시계를 이 값으로 세워야 의미가 있다.
KST_0300 = 1785693600.0
KST_1400 = 1785733200.0

# quiet hours 는 상태 키가 아니라 ctx.profile 로 들어온다(app_user 에서 온 값).
QUIET_PROFILE = {"quietHoursStart": "22:00", "quietHoursEnd": "07:00",
                 "timeZone": "Asia/Seoul"}


def test_small_talk_stays_quiet_at_night(frozen_clock):
    """★ 잘 맞춘 침묵이 어떤 문구보다 자연스럽다 (§17.6).

    새벽 3시에 잡담을 꺼내는 로봇은 다음 날 콘센트가 빠진다.
    """
    frozen_clock(start=KST_0300)

    decision = gate.proactive_gate({
        "senior_id": SENIOR,
        "ctx": {"profile": QUIET_PROFILE},
        "proposals": [_proposal("ambient")],
    })

    assert decision["gate_decision"] == "silent", (
        "잡담이 새벽에 통과했다. 침묵은 실패가 아니라 기능이다")


def test_the_same_small_talk_is_allowed_in_the_afternoon(frozen_clock):
    """★ 침묵이 '항상' 나오면 게이트가 아니라 벽이다.

    같은 제안이 낮에는 통과해야 한다. 그러지 않으면 위 테스트는 "잡담이 아예
    안 나간다"는 사실을 통과로 읽고 있는 것이다.
    """
    frozen_clock(start=KST_1400)

    decision = gate.proactive_gate({
        "senior_id": SENIOR,
        "ctx": {"profile": QUIET_PROFILE},
        "proposals": [_proposal("ambient")],
    })

    assert decision["gate_decision"] == "speak"


def test_a_liveness_probe_speaks_even_at_night(frozen_clock):
    """★ 반대 방향의 실수도 막는다. critical 은 밤에도 나가야 한다.

    침묵을 '항상 안전한 선택'으로 만들면, 응급 상황에서도 조용해진다.
    """
    frozen_clock(start=KST_0300)

    decision = gate.proactive_gate({
        "senior_id": SENIOR,
        "ctx": {"profile": QUIET_PROFILE},
        "proposals": [{"intent": "companion", "priority": "critical",
                       "seed": "어르신, 괜찮으세요?"}],
    })

    assert decision["gate_decision"] == "speak"


# ─────────────────────────────────────────────────────────────────────────────
# 임계치는 policy.py 만 고쳐서 바꿀 수 있어야 한다 (완료 조건)
# ─────────────────────────────────────────────────────────────────────────────


def test_the_sentence_limit_is_a_policy_dial_not_a_literal(monkeypatch, tmp_path):
    """★ 완료 조건: 임계치 변경이 로직 수정 없이 policy.py 만으로 가능하다.

    이 테스트는 policy 값을 바꿨을 때 동작이 실제로 따라오는지 본다. 상수가
    함수 본문에 복사돼 있으면 여기서 드러난다 — 그때는 policy.py 를 고쳐도
    아무 일도 일어나지 않는다.
    """
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    monkeypatch.setattr(policy, "MAX_SENTENCES", 1)

    long_reply = "첫 문장입니다. 둘째 문장입니다. 셋째 문장입니다."
    prompts, states = replay(
        {"id": "dial", "why": "dial", "turns": ["안녕"], "llmReply": long_reply,
         "expect": {}},
        tmp_path)

    assert len(states[-1]["sentences"]) == 1
    assert "1문장 이내" in prompts[0], (
        "프롬프트의 문장 수도 같은 상수를 읽어야 한다. 따로 박혀 있으면 프롬프트와 "
        "정제기가 서로 다른 한도를 말하게 된다")

# ─────────────────────────────────────────────────────────────────────────────
# 고아 다이얼 — policy.py 에 있는데 아무도 읽지 않는 상수
# ─────────────────────────────────────────────────────────────────────────────

# 212 티켓이 튜닝 대상으로 나열한 다이얼들. 각각을 '읽는 사람'이 있어야 한다.
TICKET_DIALS = [
    "SILENCE_LADDER_SEC",
    "RESTING_PATIENCE_MULTIPLIER",
    "BACKCHANNELS",
    "BACKCHANNEL_MAX_SEC",
    "MEMORY_TOP_K",
    "MEMORY_TOP_K_DEGRADED",
    "COOLDOWN_SEC",
    "ECHO_GUARD_SEC",
    "ECHO_VAD_THRESHOLD_MULTIPLIER",
    "DEGRADATION_ORDER",
    "MEAL_REMINDER_TIMES",
    "WATER_REMINDER_TIMES",
    "MAX_SENTENCES",
    "TURN_LATENCY_BUDGET_SEC",
]

SRC = Path(__file__).parent.parent / "src" / "bomi_ai_chat"


@pytest.mark.parametrize("dial", TICKET_DIALS)
def test_every_tuning_dial_has_a_reader(dial):
    """★★ policy.py 에 있는데 아무도 읽지 않는 상수를 잡는다.

    212 가 실제로 발견한 실패가 이것이다. `DEGRADATION_ORDER` 는 문자열 네 개짜리
    목록으로 존재했고, 그것을 읽는 코드가 하나도 없었다. `context.py` 주석은
    "압박 상황에서는 낮춘 값이 들어온다"고 말했지만 넣는 사람이 없었다.

    이 실패가 위험한 이유: 상수와 주석이 있으면 사람들은 그것이 동작한다고 믿는다.
    "저하 순서는 정해져 있습니다"라고 말할 수 있고, 그 문장이 사실이 아니다.
    그리고 아무 테스트도 실패하지 않는다 — 아무 코드도 그것을 부르지 않으니까.

    완료 조건 "임계치 변경이 로직 수정 없이 policy.py 만으로 가능함"의 최소 조건이
    이것이다. 읽는 사람이 없으면 policy 를 고쳐도 아무 일도 일어나지 않는다.
    """
    assert hasattr(policy, dial), f"policy.py 에 {dial} 이 없다"

    readers = [
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if path.name != "policy.py" and f"policy.{dial}" in path.read_text(encoding="utf-8")
    ]

    assert readers, (
        f"policy.{dial} 을 읽는 코드가 없다. 이 값을 바꿔도 아무 일도 일어나지 않는다. "
        f"쓰이지 않는 다이얼이면 policy.py 에서 지우고, 쓰려던 것이면 배선한다")
