"""안전 트리아지와 T1 에스컬레이션 — 210 완료 조건 회귀.

이 파일이 검증하는 완료 조건
    1. 부정/시제 3종 케이스 ("안 아파" / "어제 아팠어" / "아파")
    2. T1 발생 시 outbox 적재 + 어르신에게 차분한 응답
    3. 네트워크 차단 중 T1 이 유실되지 않음
    4. 트리아지 미구현 경고 로그가 더 이상 나오지 않음

가장 중요한 네 가지
    test_a_sore_knee_is_not_an_emergency
        "무릎이 아파"는 독거노인에게 가장 흔한 말이다. 그것마다 보호자를 부르면
        보호자는 곧 알림을 읽지 않게 되고, **그때부터 "가슴이 아파"를 놓친다.**

    test_denying_the_symptom_does_not_escalate
        "안 아파"에는 "아파"가 들어 있다. 순서를 뒤집으면 괜찮다고 말한 어르신
        때문에 보호자가 호출된다.

    test_silence_after_a_symptom_escalates
        증상을 말한 뒤의 침묵은 안심할 이유가 아니라 더 나쁜 신호다.

    test_an_ambiguous_reply_escalates
        계약 대화와 정반대다. 애매하면 부른다.

참고
    CLAUDE.md §9 (티어), §10 (약한 신호), docs/carebot/PROGRESS.md §2.2 (자해 목록은 사람이 검토)
"""

import json

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.graph import triage
from bomi_ai_chat.jobs import ticks
from bomi_ai_chat.localstore import context_cache, db, outbox
from bomi_ai_chat.localstore import runtime as runtime_store

SENIOR = "senior-1"
MORNING_UTC = 1785542400.0  # 2026-08-01 00:00 UTC = 서울 09:00

SEOUL_PROFILE = {
    "profile": {
        "timeZone": "Asia/Seoul",
        "quietHoursStart": "22:00",
        "quietHoursEnd": "07:00",
    }
}


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()


class CollectingChannel:
    """보호자 채널 대역. 전송된 알림을 누적한다."""

    def __init__(self):
        self.delivered: list[tuple[str, dict]] = []

    def notify_guardian(self, tier: str, payload: dict) -> None:
        self.delivered.append((tier, payload))


@pytest.fixture
def guardian():
    return CollectingChannel()


def alerts(guardian, reason=None):
    outbox.flush(guardian)
    if reason is None:
        return list(guardian.delivered)
    return [(t, p) for t, p in guardian.delivered if p.get("reason") == reason]


def turn(text, **extra):
    """한 번의 반응형 턴에 대한 트리아지 결과."""
    state = {"senior_id": SENIOR, "user_input": text}
    state.update(extra)
    return triage.safety_triage(state)


# ── 완료 조건 1: 부정과 시제 ─────────────────────────────────────────────────


def test_present_tense_pain_is_an_emergency(frozen_clock):
    """(3종 중 1) "아파" — 부위를 말하지 않았다. 물어본다."""
    frozen_clock(start=MORNING_UTC)

    assert turn("아파")["safety_level"] == "confirm"


def test_denying_the_symptom_does_not_escalate(frozen_clock):
    """★ (3종 중 2) "안 아파" 에는 "아파" 가 그대로 들어 있다.

    부정을 나중에 보면 정반대로 판정하고, 괜찮다고 말한 어르신 때문에 보호자가
    호출된다. 206 의 `_is_completion_report`("약 안 먹었어")와 같은 함정이다.
    """
    frozen_clock(start=MORNING_UTC)

    assert turn("안 아파")["safety_level"] == "none"
    assert turn("이제 괜찮아")["safety_level"] == "none"
    assert turn("가슴이 아프지 않아요")["safety_level"] == "none"


def test_past_tense_with_a_time_word_does_not_escalate(frozen_clock):
    """(3종 중 3) "어제 아팠어" 는 지금의 일이 아니다."""
    frozen_clock(start=MORNING_UTC)

    assert turn("어제 가슴이 아팠어")["safety_level"] == "none"
    assert turn("지난주에 어지러웠어")["safety_level"] == "none"


def test_ongoing_since_yesterday_still_escalates(frozen_clock):
    """★ "어제부터 아파" 는 어제 일이 아니라 지금도 아픈 것이다.

    시각 표현만 보고 억제하면 이틀째 아픈 어르신이 조용히 걸러진다.
    """
    frozen_clock(start=MORNING_UTC)

    assert turn("어제부터 가슴이 아파")["safety_level"] == "confirm"


def test_tense_endings_alone_do_not_suppress(frozen_clock):
    """★ 시제 어미로 판정하지 않는 이유.

    한국어는 완료된 사건이 지금 중요할 때에도 과거형을 쓴다. "넘어졌어요"는
    과거형이지만 방금 넘어진 것이고 명백한 응급이다. 어미로 억제하면 이것을 놓친다.
    """
    frozen_clock(start=MORNING_UTC)

    assert turn("넘어졌어요")["safety_level"] == "confirm"
    assert turn("쓰러질 것 같아")["safety_level"] == "confirm"


# ── 통증은 부위로 갈린다 ─────────────────────────────────────────────────────


def test_a_sore_knee_is_not_an_emergency(frozen_clock):
    """★★ "무릎이 아파" 는 독거노인에게 가장 흔한 말 중 하나다.

    그것마다 "아드님께 연락드릴까요?" 를 묻는 로봇은 무섭고, 보호자는 곧 알림을
    읽지 않게 된다. 그리고 그때부터 "가슴이 아파" 를 놓친다.
    """
    frozen_clock(start=MORNING_UTC)

    for text in ["무릎이 아파", "허리가 아파요", "어깨가 쑤셔", "삭신이 쑤시네"]:
        assert turn(text)["safety_level"] == "none", text


def test_chest_pain_is_an_emergency(frozen_clock):
    frozen_clock(start=MORNING_UTC)

    assert turn("가슴이 아파")["safety_level"] == "confirm"
    assert turn("머리가 너무 아파요")["safety_level"] == "confirm"


def test_a_high_risk_part_wins_over_a_chronic_one(frozen_clock):
    """"무릎도 아프고 가슴도 아파" 를 만성으로 처리하면 안 된다."""
    frozen_clock(start=MORNING_UTC)

    assert turn("무릎도 아프고 가슴도 아파")["safety_level"] == "confirm"


def test_ordinary_talk_is_not_triaged(frozen_clock):
    frozen_clock(start=MORNING_UTC)

    for text in ["오늘 날씨가 좋네", "손자가 왔다 갔어", "밥 먹었어"]:
        assert turn(text)["safety_level"] == "none", text


# ── 확인 턴: 키워드 한 번에 부르지 않는다 ────────────────────────────────────


def test_a_symptom_asks_before_it_calls(frozen_clock):
    """★ 증상 표현은 애매하다. 질문 하나가 그것을 명확한 응답으로 바꾼다."""
    frozen_clock(start=MORNING_UTC)

    out = turn("가슴이 아파")

    assert out["safety_level"] == "confirm"
    assert out["pending_safety_check"]["reason"] == "emergency"
    # 아직 보호자를 부르지 않았다.
    assert outbox.pending_count() == 0


def test_the_confirming_question_says_nothing_clinical(frozen_clock):
    """진단하지 않고, 티어를 말하지 않고, 겁을 주지 않는다."""
    frozen_clock(start=MORNING_UTC)

    spoken = triage.safety_confirm({})["response"]

    assert spoken
    for forbidden in ["T1", "응급", "심장", "진단", "위험"]:
        assert forbidden not in spoken


def test_saying_you_are_fine_cancels_the_escalation(frozen_clock):
    frozen_clock(start=MORNING_UTC)
    pending = {"reason": "emergency", "asked_at": MORNING_UTC,
               "expires_at": MORNING_UTC + 90}

    out = turn("아니야 괜찮아", pending_safety_check=pending)

    assert out["safety_level"] == "none"
    assert outbox.pending_count() == 0


def test_an_ambiguous_reply_escalates(frozen_clock):
    """★★ 계약 대화와 정반대다. 애매하면 부른다.

    동의 판정에서는 애매하면 기록하지 않는다 — 잘못 기록하면 신뢰를 잃기 때문이다.
    안전에서는 애매하면 부른다 — 놓치면 사람을 잃기 때문이다.
    같은 '애매함'이 한쪽에서는 '하지 않음'이고 다른 쪽에서는 '함'이다.
    """
    frozen_clock(start=MORNING_UTC)
    pending = {"reason": "emergency", "asked_at": MORNING_UTC,
               "expires_at": MORNING_UTC + 90}

    for reply in ["글쎄", "몰라", "음...", "어제 손자가 왔었는데"]:
        out = turn(reply, pending_safety_check=pending)
        assert out["safety_level"] == "T1", reply


def test_an_explicit_request_skips_the_confirming_question(frozen_clock):
    """어르신이 연락해 달라고 말했는데 "정말요?" 라고 되묻는 로봇은 도움이 안 된다."""
    frozen_clock(start=MORNING_UTC)

    out = turn("아들한테 전화해줘")

    assert out["safety_level"] == "T1"
    assert out["escalation"]["reason"] == "explicit_request"


def test_119_is_an_explicit_request(frozen_clock):
    frozen_clock(start=MORNING_UTC)

    assert turn("119 불러줘")["safety_level"] == "T1"


# ── 자해: 동의를 무시하고, 확인 턴도 없다 ────────────────────────────────────


def test_self_harm_escalates_immediately(frozen_clock):
    """확인 턴을 넣지 않는다. 되묻는 것은 말을 취소할 기회를 주는 것이고,
    그 기회는 여기서 도움이 되지 않는다."""
    frozen_clock(start=MORNING_UTC)

    out = turn("이제 그만 살고 싶어")

    assert out["safety_level"] == "T1"
    assert out["escalation"]["reason"] == "self_harm_override"


def test_self_harm_overrides_a_request_for_secrecy(frozen_clock):
    """★ "아무한테도 말하지 마" 라고 해도 올린다. T3 동의 요건을 의도적으로
    무시하는 유일한 지점이다 (CLAUDE.md §9)."""
    frozen_clock(start=MORNING_UTC)

    out = turn("아무한테도 말하지 마, 그냥 죽고 싶어")

    assert out["safety_level"] == "T1"
    assert out["escalation"]["reason"] == "self_harm_override"


def test_self_harm_beats_a_pending_confirmation(frozen_clock):
    """확인을 기다리는 중에 자해 신호가 오면 그쪽이 이긴다."""
    frozen_clock(start=MORNING_UTC)
    pending = {"reason": "emergency", "asked_at": MORNING_UTC,
               "expires_at": MORNING_UTC + 90}

    out = turn("살기 싫어", pending_safety_check=pending)

    assert out["escalation"]["reason"] == "self_harm_override"


def test_common_korean_intensifiers_are_not_self_harm(frozen_clock):
    """"죽겠다", "미치겠다" 는 한국어에서 대개 강조 표현이다.

    엉뚱한 자해 알림을 받은 가족은 그 뒤로 알림을 다르게 대한다.
    """
    frozen_clock(start=MORNING_UTC)

    for text in ["아이고 힘들어 죽겠네", "더워 죽겠어", "심심해 미치겠어"]:
        assert turn(text)["safety_level"] != "T1", text


# ── 완료 조건 2·3: outbox 적재와 유실 없음 ───────────────────────────────────


def test_escalation_queues_a_t1_and_answers_calmly(frozen_clock, guardian):
    """(완료 조건) T1 발생 시 outbox 적재 + 어르신에게 차분한 응답."""
    frozen_clock(start=MORNING_UTC)

    out = triage.escalation({
        "senior_id": SENIOR,
        "escalation": {"reason": "emergency", "ts": MORNING_UTC},
        "occupancy": "HOME",
        "rest_state": "AWAKE",
    })

    assert out["response"]
    tier, payload = alerts(guardian)[0]
    assert tier == "T1"
    assert payload["reason"] == "emergency"
    # 약한 신호를 함께 싣는다. 판단 근거가 있어야 보호자와 사후 튜닝이 볼 수 있다.
    assert payload["occupancy"] == "HOME"


def test_the_calm_answer_never_names_the_machinery(frozen_clock):
    """어르신에게는 감시 시스템이 아니라 말벗으로 들려야 한다 (CLAUDE.md §17.9)."""
    frozen_clock(start=MORNING_UTC)

    for reason in ["emergency", "explicit_request", "self_harm_override", "no_response"]:
        spoken = triage.escalation({
            "senior_id": SENIOR, "escalation": {"reason": reason},
        })["response"]
        for forbidden in ["T1", "티어", "escalation", "outbox", "분류"]:
            assert forbidden not in spoken, (reason, spoken)


def test_the_self_harm_answer_does_not_play_counselor(frozen_clock):
    """상담을 시도하지 않는다. 짧게 반응하고 사람에게 넘긴다.

    자살 대화를 챗봇이 붙잡고 있는 것은 도움을 부르는 것보다 나쁜 결과다.
    """
    frozen_clock(start=MORNING_UTC)

    spoken = triage.escalation({
        "senior_id": SENIOR, "escalation": {"reason": "self_harm_override"},
    })["response"]

    # 사람에게 넘긴다는 말이 들어 있어야 한다.
    assert "연락" in spoken
    # 캐묻지 않는다.
    assert "왜" not in spoken


def test_a_t1_survives_a_network_outage(frozen_clock, guardian):
    """(완료 조건) 네트워크 차단 중에도 T1 이 유실되지 않는다.

    전송보다 저장이 먼저다. 끊긴 연결로 발사된 알림은 그냥 사라지고, 하필 그 순간이
    알림이 가장 중요한 순간이다.
    """
    sim = frozen_clock(start=MORNING_UTC)

    triage.escalation({
        "senior_id": SENIOR, "escalation": {"reason": "emergency"},
    })
    assert outbox.pending_count() == 1

    # 네트워크가 죽어 있는 동안 flush 해도 버려지지 않는다.
    class Dead:
        def notify_guardian(self, tier, payload):
            from bomi_ai_chat.notify import NotifyError

            raise NotifyError("network unreachable")

    outbox.flush(Dead())
    assert outbox.pending_count() == 1

    # 복구되면 그대로 나간다.
    sim.advance(policy.OUTBOX_BACKOFF_BASE_SEC + 1)
    assert len(alerts(guardian)) == 1


def test_the_alert_does_not_carry_the_seniors_words(frozen_clock, guardian):
    """★ 발화 원문을 보내지 않는다.

    보호자에게 필요한 것은 "가서 봐 주세요"이지 원문이 아니다. 원문을 실으면
    T4("우리끼리 얘기")가 T1 알림에 묻어 나가는 경로가 생긴다 (CLAUDE.md §9).
    """
    frozen_clock(start=MORNING_UTC)

    triage.escalation({
        "senior_id": SENIOR,
        "user_input": "아무한테도 말하지 말고, 사실 남편 얘기가 나오면 힘들어",
        "escalation": {"reason": "emergency"},
    })

    _tier, payload = alerts(guardian)[0]
    assert "남편" not in json.dumps(payload, ensure_ascii=False)


# ── 대답이 없을 때: 확인이 잊히지 않는다 ─────────────────────────────────────


def test_silence_after_a_symptom_escalates(frozen_clock, guardian):
    """★★ 어르신이 확인 질문에 아예 대답하지 않으면 그 턴은 오지 않는다.

    이 검사가 없으면 "가슴이 아파" 라고 말하고 쓰러진 어르신이 확인 질문만 받고
    잊힌다 — 이 시스템이 막으려는 바로 그 실패다.
    """
    sim = frozen_clock(start=MORNING_UTC)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    runtime_store.save(SENIOR, last_user_interaction_at=MORNING_UTC, occupancy="HOME")
    turn("가슴이 아파")

    sim.advance(policy.SAFETY_CONFIRMATION_TIMEOUT_SEC + 1)
    ticks.silence_tick(SENIOR, None)

    tier, payload = alerts(guardian)[0]
    assert tier == "T1"
    assert payload["confirmed_by"] == "no_reply_to_safety_check"


def test_the_pending_check_is_not_filtered_by_quiet_hours(frozen_clock, guardian):
    """★ 새벽 3시에 "숨이 안 쉬어져" 라고 말한 뒤의 침묵은 수면이 아니다.

    _is_absence_expected 를 먼저 태우면 증상을 말한 어르신이 밤이라는 이유로
    조용히 걸러진다.
    """
    # 서울 새벽 2시 = 전날 17:00 UTC
    night = MORNING_UTC + 17 * 3600
    sim = frozen_clock(start=night)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    runtime_store.save(SENIOR, last_user_interaction_at=night, occupancy="HOME")
    turn("숨이 안 쉬어져")

    sim.advance(policy.SAFETY_CONFIRMATION_TIMEOUT_SEC + 1)
    ticks.silence_tick(SENIOR, None)

    assert len(alerts(guardian)) == 1


def test_answering_in_time_clears_the_deadline(frozen_clock, guardian):
    """대답했으면 마감을 지운다. 안 지우면 괜찮다고 말한 뒤에도 알림이 나간다."""
    sim = frozen_clock(start=MORNING_UTC)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    runtime_store.save(SENIOR, last_user_interaction_at=MORNING_UTC, occupancy="HOME")
    out = turn("가슴이 아파")

    sim.advance(10)
    turn("아니야 괜찮아", pending_safety_check=out["pending_safety_check"])

    sim.advance(policy.SAFETY_CONFIRMATION_TIMEOUT_SEC + 1)
    ticks.silence_tick(SENIOR, None)

    assert alerts(guardian) == []
    assert runtime_store.load(SENIOR)["safety_check_until"] == 0.0


def test_no_pending_check_means_the_tick_does_nothing_extra(frozen_clock, guardian):
    sim = frozen_clock(start=MORNING_UTC)
    context_cache.save(SENIOR, SEOUL_PROFILE)
    runtime_store.save(SENIOR, last_user_interaction_at=MORNING_UTC, occupancy="HOME")

    sim.advance(60)
    ticks.silence_tick(SENIOR, None)

    assert alerts(guardian) == []


# ── 완료 조건 4: 미구현 경고가 사라졌다 ──────────────────────────────────────


def test_the_not_implemented_warning_is_gone(frozen_clock, caplog):
    """(완료 조건) 트리아지 미구현 경고 로그가 더 이상 나오지 않는다."""
    frozen_clock(start=MORNING_UTC)

    with caplog.at_level("WARNING"):
        turn("가슴이 아파")
        turn("오늘 날씨 좋네")

    assert "NOT IMPLEMENTED" not in caplog.text


def test_the_unreviewed_marker_list_is_announced_once(frozen_clock, caplog):
    """★ 다른 경고는 남아 있다. 자해 표현 목록이 아직 사람의 검토를 받지 않았다.

    판별기는 동작한다. 검토 여부를 코드 밖에서만 관리하면 잊히므로 런타임으로 끌어낸다
    (docs/carebot/PROGRESS.md §2.2). 검토가 끝나면 policy.SELF_HARM_MARKERS_REVIEWED 를
    True 로 바꾼다.
    """
    frozen_clock(start=MORNING_UTC)
    triage._REVIEW_WARNED = False

    with caplog.at_level("WARNING"):
        turn("안녕")
        turn("잘 잤어")

    assert caplog.text.count("has not been human-reviewed") == 1


# ── 중복 알림 억제  (233 실기 점검에서 터진 구멍) ────────────────────────────


def test_the_same_alert_is_not_sent_twice_in_a_row(frozen_clock, guardian):
    """★ 같은 사유의 T1 이 연달아 나면 두 번째부터는 보호자에게 보내지 않는다.

    왜 이 테스트가 있는가
        233 실기 점검에서 로봇의 응급 응답이 마이크로 되돌아와(에코) 그 문장 안의
        응급 표현이 다시 감지되는 자기증식 루프가 생겼다. 3분 만에 동일한 T1 이
        15회 배달됐다. 에코는 따로 고쳤지만, 어떤 이유로든 같은 판정이 반복되면
        보호자 화면이 도배되는 구멍은 그것과 별개다 (CLAUDE.md §9 알림 피로).
    """
    frozen_clock(start=MORNING_UTC)
    state = {
        "senior_id": SENIOR,
        "escalation": {"reason": "emergency"},
        "occupancy": "HOME",
    }

    triage.escalation(state)
    triage.escalation(state)
    triage.escalation(state)

    assert len(alerts(guardian, reason="emergency")) == 1


def test_the_senior_still_gets_an_answer_while_the_alert_is_suppressed(
    frozen_clock, guardian
):
    """★ 억제되는 것은 보호자 알림뿐이다. 어르신에게는 매번 대답한다.

    두 번째로 "가슴이 아파"라고 하신 분에게 로봇이 침묵하면 그건 다른 종류의
    실패다. 보호자는 이미 알고 있지만 어르신은 여전히 대답을 기다린다.
    """
    frozen_clock(start=MORNING_UTC)
    state = {"senior_id": SENIOR, "escalation": {"reason": "emergency"}}

    first = triage.escalation(state)["response"]
    second = triage.escalation(state)["response"]

    assert first and second
    assert len(alerts(guardian, reason="emergency")) == 1


def test_a_different_reason_is_never_suppressed(frozen_clock, guardian):
    """★ 사유가 다르면 중복이 아니라 '악화'다. 무조건 보낸다.

    emergency 직후의 self_harm_override 를 억제하면, 억제 로직이 가장 위험한
    신호를 삼키게 된다.
    """
    frozen_clock(start=MORNING_UTC)

    triage.escalation({"senior_id": SENIOR, "escalation": {"reason": "emergency"}})
    triage.escalation(
        {"senior_id": SENIOR, "escalation": {"reason": "self_harm_override"}}
    )

    assert len(alerts(guardian, reason="emergency")) == 1
    assert len(alerts(guardian, reason="self_harm_override")) == 1


def test_the_alert_is_sent_again_once_the_window_passes(frozen_clock, guardian):
    """★ 억제는 영구가 아니다. 창이 지나면 다시 보낸다.

    첫 알림을 보호자가 놓쳤을 수 있고, 그 상태가 이어지고 있다면 두 번째 기회가
    있어야 한다. 억제가 영구라면 그것은 알림을 삼키는 것이다.
    """
    sim = frozen_clock(start=MORNING_UTC)
    state = {"senior_id": SENIOR, "escalation": {"reason": "emergency"}}

    triage.escalation(state)
    sim.advance(policy.T1_DUPLICATE_SUPPRESSION_SEC + 1)
    triage.escalation(state)

    assert len(alerts(guardian, reason="emergency")) == 2


# ── T1 상태 고착과 확인 질문의 시효  (233 실기 폭주의 남은 반쪽) ──────────────


def test_a_reactive_turn_resets_last_turns_t1(frozen_clock):
    """★★ 지난 턴의 T1 이 checkpoint 로 넘어와도 이번 턴을 오염시키지 않는다.

    233 실기에서 T1 한 번 뒤 모든 발화가 — "괜찮아요"조차 — 분류 없이 T1 로
    직행해 같은 문장이 6분간 14번 반복됐고, 재시작 후 첫 발화까지 즉시 T1 이
    됐다. safety_level/escalation 은 reducer 없는 채널이라 지난 턴의 값이
    그대로 넘어오는데, safety_triage 의 첫 분기가 그것을 '사전 세팅'으로
    오인한 것이다. note_interaction 의 매 턴 리셋이 그 루프의 차단막이다.
    """
    frozen_clock(start=MORNING_UTC)
    from bomi_ai_chat.graph import ingress

    out = ingress.note_interaction({
        "senior_id": SENIOR,
        "user_input": "오늘은 날이 좋네",
        "safety_level": "T1",
        "escalation": {"reason": "emergency", "ts": MORNING_UTC - 60},
    })

    assert out["safety_level"] == "none"
    assert out["escalation"] is None


def test_a_stale_confirmation_is_not_treated_as_an_answer(frozen_clock):
    """★ 한참 전에 던진 확인 질문의 답으로 지금 발화를 판정하지 않는다.

    _resolve_pending_check 는 "명확한 부정 외에는 전부 T1" 이다. 시효를 보지
    않으면 재시작 뒤 첫 인사("점심 뭐 먹을까")가 보호자 호출이 된다. 답이 오지
    않은 확인의 에스컬레이션은 silence_tick 이 마감 시점에 이미 처리했다.
    """
    frozen_clock(start=MORNING_UTC)
    asked = MORNING_UTC - 3600
    pending = {"reason": "emergency", "asked_at": asked,
               "expires_at": asked + policy.SAFETY_CONFIRMATION_TIMEOUT_SEC}

    out = turn("점심에 뭐 먹을까", pending_safety_check=pending)

    assert out["safety_level"] == "none"
    assert out["pending_safety_check"] is None
    assert outbox.pending_count() == 0


def test_a_stale_confirmation_still_hears_a_new_symptom(frozen_clock):
    """시효가 지났어도 새 발화 자체가 증상이면 새 확인 질문으로 이어진다."""
    frozen_clock(start=MORNING_UTC)
    asked = MORNING_UTC - 3600
    pending = {"reason": "emergency", "asked_at": asked,
               "expires_at": asked + policy.SAFETY_CONFIRMATION_TIMEOUT_SEC}

    out = turn("가슴이 아파", pending_safety_check=pending)

    assert out["safety_level"] == "confirm"
    assert out["pending_safety_check"]["reason"] == "emergency"


def test_a_pending_check_without_a_deadline_is_stale(frozen_clock):
    """과거 빌드가 남긴 expires_at 없는 checkpoint 를 답 판정에 쓰지 않는다."""
    frozen_clock(start=MORNING_UTC)

    out = turn("글쎄", pending_safety_check={"reason": "emergency"})

    assert out["safety_level"] == "none"


# ── 반복 T1 의 응답 품질  (같은 약속을 되풀이하지 않는다) ────────────────────


def test_a_suppressed_duplicate_speaks_differently(frozen_clock, guardian):
    """★ 억제 창 안의 두 번째 T1 은 연락을 '새로' 약속하지 않는다.

    "제가 가족분께 연락드릴게요"를 6분간 14번 들은 것이 233 실기에서 가장
    기계적으로 들린 부분이다. 이미 연락된 상태라면 그 사실을 말하는 것이
    정직하고 덜 무섭다.
    """
    frozen_clock(start=MORNING_UTC)
    state = {"senior_id": SENIOR, "escalation": {"reason": "emergency"}}

    first = triage.escalation(state)["response"]
    second = triage.escalation(state)["response"]

    assert first != second
    assert "조금 전" in second or "이미" in second
    assert len(alerts(guardian, reason="emergency")) == 1


def test_safety_wording_does_not_assume_a_son(frozen_clock):
    """★ 보호자가 아들이라는 가정을 문구에 박지 않는다.

    보호자는 딸일 수도, 형제일 수도, 돌봄 담당자일 수도 있다. 아들이 없는
    어르신에게 "아드님"은 로봇이 자기를 모른다는 증거로 들린다 (CLAUDE.md §17.3).
    """
    frozen_clock(start=MORNING_UTC)

    assert "아드님" not in triage.safety_confirm({})["response"]
    for responses in (triage._RESPONSES, triage._RESPONSES_ALREADY_SENT):
        for spoken in responses.values():
            assert "아드님" not in spoken
