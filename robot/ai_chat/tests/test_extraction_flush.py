"""추출 큐 flush(jobs/ticks.extraction_flush) 검증 (S15P11E102-255).

이 파일이 검증하는 것
    1. 대기 행마다 LLM 을 한 번 불러 사실을 뽑고, 있으면 fact_client 로 제출한다.
    2. 제출까지 성공한(또는 애초에 뽑을 것이 없던) 행만 큐에서 사라진다.
    3. LLM 실패/제출 실패는 그 행을 큐에 남겨 다음 flush 가 재시도하게 한다.
    4. 한 번의 flush 는 policy.EXTRACTION_FLUSH_BATCH_SIZE 건까지만 처리한다.
    5. 모델 출력이 상한(policy.EXTRACTION_MAX_FACTS_PER_UTTERANCE)을 넘겨도
       파이썬 쪽에서 다시 자른다.
    6. 킬스위치(정책 상수 + 환경변수) 둘 중 하나만 꺼져도 아무것도 하지 않는다.
    7. 스케줄러 양쪽(add_job, run_all_ticks_once)에 틱이 등록돼 있다.
    8. 어르신의 시간대로 본 '지금'이 프롬프트에 실린다. 시간대를 모르면 날짜를
       지어내지 않고 UTC 로도 떨어지지 않는다 (G4).
    9. 모델이 준 startsAt/title 은 파서를 살아서 통과하고, 계약에 없는 키는 못 한다.

왜 8번이 UTC 폴백이면 안 되는가
    야간 외출 판정(_local_now_from)에서는 시간대를 모를 때 UTC 로 떨어지는 것이
    "덜 정확한 판정"으로 끝난다. 여기서는 어르신이 말한 "다음 주 화요일 오후 두
    시"가 아홉 시간 어긋난 절대 시각이 되어 보호자 화면의 일정에 그대로 박힌다.
    그래서 이 경로만 별도 헬퍼(_extraction_now_local)를 쓰고, 모르면 None 이다.

참고
    CLAUDE.md §8, §16 / jobs/ticks.extraction_flush, backend_client/fact_client.py
"""

import re

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.backend_client.fact_client import FactSubmissionError
from bomi_ai_chat.jobs import scheduler as scheduler_module
from bomi_ai_chat.jobs import ticks
from bomi_ai_chat.localstore import context_cache, db, extraction

SENIOR = "senior-1"

# 서울 2026-08-07(금) 15:04. 같은 순간의 UTC 는 06:04 이라 시각으로 둘을 구분할 수 있다.
SEOUL_FRIDAY_1504 = 1_786_082_640.0

_LOOKS_LIKE_A_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()


class ScriptedLLM:
    """호출할 때마다 미리 정해둔 응답을 순서대로 돌려준다."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def generate(self, prompt, weather_data=None):
        self.prompts.append(prompt)
        if not self.replies:
            return "[]"
        return self.replies.pop(0)


class RecordingFactClient:
    """제출된 사실을 순서대로 모은다. 지정한 senior_id 에서는 실패한다."""

    def __init__(self, *, fail_for: set[str] | None = None):
        self.submissions = []
        self.fail_for = fail_for or set()

    def submit_fact_candidates(self, senior_id, *, conversation_id, source_message_id,
                               facts, now_local=None, utterance=None):
        if senior_id in self.fail_for:
            raise FactSubmissionError("backend rejected the batch")
        self.submissions.append({
            "senior_id": senior_id,
            "conversation_id": conversation_id,
            "source_message_id": source_message_id,
            "facts": facts,
            # 프롬프트에 실린 기준 시각과 검증에 쓰인 기준 시각이 같은지 확인할 수
            # 있어야 한다 — 둘이 갈리면 "모델은 발화 시각 기준으로 계산했는데 검증은
            # 지금 기준으로 과거라고 판정"하는 모순이 조용히 생긴다.
            "now_local": now_local,
            # 요일 검산의 채점 기준. 프롬프트에 실린 발화 원문과 같아야 한다 —
            # 모델이 만든 content 로 대조하면 채점이 성립하지 않는다.
            "utterance": utterance,
        })


def _enqueue(content="요즘 손자가 자주 놀러 와요", **overrides):
    fields = {
        "conversation_id": "conv-1",
        "source_message_id": "msg-1",
        "content": content,
    }
    fields.update(overrides)
    return extraction.enqueue(SENIOR, **fields)


# ── 1·2. 정상 경로 ───────────────────────────────────────────────────────────


def test_a_job_with_facts_is_submitted_and_removed_from_the_queue(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    _enqueue()
    llm = ScriptedLLM(['[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}]'])
    fact_client = RecordingFactClient()

    result = ticks.extraction_flush(SENIOR, llm=llm, fact_client=fact_client)

    assert result == {"processed": 1, "submitted": 1, "failed": 0, "given_up": 0}
    assert extraction.pending_count(SENIOR) == 0
    assert fact_client.submissions[0]["facts"] == [
        {"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}
    ]
    assert fact_client.submissions[0]["source_message_id"] == "msg-1"


def test_a_job_with_no_facts_is_still_marked_processed(frozen_clock):
    """뽑을 것이 없어도(빈 배열) 그 행은 처리 완료로 표시된다 — 영원히 재시도하지 않는다."""
    frozen_clock(start=1_700_000_000.0)
    _enqueue(content="네 알겠습니다 그렇게 할게요")
    llm = ScriptedLLM(["[]"])
    fact_client = RecordingFactClient()

    result = ticks.extraction_flush(SENIOR, llm=llm, fact_client=fact_client)

    assert result == {"processed": 1, "submitted": 0, "failed": 0, "given_up": 0}
    assert extraction.pending_count(SENIOR) == 0
    assert fact_client.submissions == []


def test_prompt_carries_the_preceding_robot_utterance(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    _enqueue(preceding_robot_utterance="요즘 가족들은 잘 지내세요?")
    llm = ScriptedLLM(["[]"])

    ticks.extraction_flush(SENIOR, llm=llm, fact_client=RecordingFactClient())

    assert "요즘 가족들은 잘 지내세요?" in llm.prompts[0]
    assert "요즘 손자가 자주 놀러 와요" in llm.prompts[0]


# ── 3. 실패는 재시도로 남는다 ────────────────────────────────────────────────


def test_an_llm_failure_leaves_the_job_pending(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    _enqueue()

    class BrokenLLM:
        def generate(self, prompt, weather_data=None):
            raise RuntimeError("gemini down")

    result = ticks.extraction_flush(SENIOR, llm=BrokenLLM(), fact_client=RecordingFactClient())

    assert result == {"processed": 0, "submitted": 0, "failed": 1, "given_up": 0}
    assert extraction.pending_count(SENIOR) == 1


def test_a_submission_failure_leaves_the_job_pending(frozen_clock):
    """fact_client 가 실패하면 그 행은 extracted=1 로 표시되지 '않는다'.

    표시해버리면 그 사실은 다시는 제출 시도되지 않는다
    (backend_client/fact_client.py 모듈 docstring 참고).
    """
    frozen_clock(start=1_700_000_000.0)
    _enqueue()
    llm = ScriptedLLM(['[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}]'])
    fact_client = RecordingFactClient(fail_for={SENIOR})

    result = ticks.extraction_flush(SENIOR, llm=llm, fact_client=fact_client)

    assert result == {"processed": 0, "submitted": 0, "failed": 1, "given_up": 0}
    assert extraction.pending_count(SENIOR) == 1


def test_an_unparseable_reply_is_treated_as_nothing_found(frozen_clock):
    """모델이 JSON 이 아닌 걸 돌려주면 뽑은 게 없다고 취급하고 넘어간다."""
    frozen_clock(start=1_700_000_000.0)
    _enqueue()
    llm = ScriptedLLM(["죄송해요, 잘 모르겠어요."])

    result = ticks.extraction_flush(SENIOR, llm=llm, fact_client=RecordingFactClient())

    assert result == {"processed": 1, "submitted": 0, "failed": 0, "given_up": 0}
    assert extraction.pending_count(SENIOR) == 0


# ── 4·5. 상한 ────────────────────────────────────────────────────────────────


def test_a_flush_processes_at_most_the_batch_size(frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    for _ in range(policy.EXTRACTION_FLUSH_BATCH_SIZE + 3):
        _enqueue()
    llm = ScriptedLLM(["[]"] * (policy.EXTRACTION_FLUSH_BATCH_SIZE + 3))

    result = ticks.extraction_flush(SENIOR, llm=llm, fact_client=RecordingFactClient())

    assert result["processed"] == policy.EXTRACTION_FLUSH_BATCH_SIZE
    assert extraction.pending_count(SENIOR) == 3


def test_facts_beyond_the_per_utterance_cap_are_trimmed(frozen_clock):
    """모델이 상한을 어겨도 파이썬 쪽에서 한 번 더 자른다."""
    frozen_clock(start=1_700_000_000.0)
    _enqueue()
    over_the_cap = ", ".join(
        f'{{"factType": "OTHER", "content": "사실{i}"}}' for i in range(5)
    )
    llm = ScriptedLLM([f"[{over_the_cap}]"])
    fact_client = RecordingFactClient()

    ticks.extraction_flush(SENIOR, llm=llm, fact_client=fact_client)

    assert len(fact_client.submissions[0]["facts"]) == policy.EXTRACTION_MAX_FACTS_PER_UTTERANCE


# ── 6. 킬스위치 ──────────────────────────────────────────────────────────────


def test_the_policy_kill_switch_blocks_the_flush(frozen_clock, monkeypatch):
    frozen_clock(start=1_700_000_000.0)
    _enqueue()
    monkeypatch.setattr(policy, "EXTRACTION_ENABLED", False)

    result = ticks.extraction_flush(
        SENIOR, llm=ScriptedLLM(["[]"]), fact_client=RecordingFactClient())

    assert result == {"processed": 0, "submitted": 0, "failed": 0, "given_up": 0}
    assert extraction.pending_count(SENIOR) == 1


def test_the_env_kill_switch_blocks_the_flush(frozen_clock, monkeypatch):
    frozen_clock(start=1_700_000_000.0)
    _enqueue()
    monkeypatch.setenv("EXTRACTION_ENABLED", "false")
    from bomi_ai_chat.config import clear_settings_cache

    clear_settings_cache()
    try:
        result = ticks.extraction_flush(
            SENIOR, llm=ScriptedLLM(["[]"]), fact_client=RecordingFactClient())
        assert result == {"processed": 0, "submitted": 0, "failed": 0, "given_up": 0}
        assert extraction.pending_count(SENIOR) == 1
    finally:
        clear_settings_cache()


# ── 8. 프롬프트에 실리는 '어르신의 지금' ─────────────────────────────────────


def _seed_time_zone(zone_name):
    """context_cache 에 어르신 프로필을 심는다. None 이면 timeZone 키 자체가 없다."""
    profile = {"name": "김순자"}
    if zone_name is not None:
        profile["timeZone"] = zone_name
    context_cache.save(SENIOR, {"profile": profile})


def test_the_prompt_carries_the_seniors_local_now(frozen_clock):
    """"다음 주 화요일"을 절대 시각으로 옮기려면 모델이 기준점을 알아야 한다."""
    frozen_clock(start=SEOUL_FRIDAY_1504)
    _seed_time_zone("Asia/Seoul")
    _enqueue(content="다음 주 화요일 세 시에 병원 가")
    llm = ScriptedLLM(["[]"])

    ticks.extraction_flush(SENIOR, llm=llm, fact_client=RecordingFactClient())

    assert "2026-08-07T15:04:00+09:00" in llm.prompts[0]
    assert "금요일" in llm.prompts[0]


def test_the_anchor_is_when_it_was_said_not_when_the_flush_runs(frozen_clock):
    """★ 큐가 밀려도 "내일"의 기준은 말한 날이다 (리뷰 지적).

    extraction_job 은 밀린다 — 네트워크가 끊기면 그 행은 pending 으로 남아 다음
    flush 로 넘어간다. 기준점을 "틱이 도는 지금"으로 잡으면 이렇게 된다.

        월요일 저녁 "내일 세 시에 병원 가"  →  큐잉  →  밤새 단절
        화요일 아침 flush  →  프롬프트에 "지금은 화요일"  →  모델이 '내일'을 수요일로 계산

    APPOINTMENT 는 사람 확인 없이 자동 반영되므로 아무도 못 보고, 하루 밀린 일정이
    그대로 박힌다. 어르신은 화요일 진료를 놓친다. created_at 은 enqueue 가 이미
    적어 두었고 pending() 이 행에 실어 준다 — 쓰지 않고 있었을 뿐이다.
    """
    # 발화는 금요일 15:04 에 큐잉된다.
    clock_handle = frozen_clock(start=SEOUL_FRIDAY_1504)
    _seed_time_zone("Asia/Seoul")
    _enqueue(content="내일 세 시에 병원 가")

    # flush 는 이틀 뒤에야 돈다(백로그가 밀린 상황).
    clock_handle.advance(2 * 24 * 60 * 60)
    llm = ScriptedLLM(["[]"])

    ticks.extraction_flush(SENIOR, llm=llm, fact_client=RecordingFactClient())

    # 프롬프트의 기준점은 말한 날(금요일)이어야 한다. 처리한 날(일요일)이 아니다.
    assert "2026-08-07T15:04:00+09:00" in llm.prompts[0]
    assert "금요일" in llm.prompts[0]
    assert "2026-08-09" not in llm.prompts[0]


def test_the_verification_anchor_matches_the_prompt_anchor(frozen_clock):
    """검증에 쓰는 기준 시각이 프롬프트에 실은 것과 같아야 한다.

    둘이 갈리면 "모델은 발화 시각 기준으로 계산했는데 검증은 지금 기준으로 과거라고
    판정"하는 모순이 생기고, 정상적인 약속이 조용히 기억으로 강등된다.
    """
    clock_handle = frozen_clock(start=SEOUL_FRIDAY_1504)
    _seed_time_zone("Asia/Seoul")
    _enqueue(content="내일 세 시에 병원 가")
    clock_handle.advance(2 * 24 * 60 * 60)

    fact_client = RecordingFactClient()
    ticks.extraction_flush(
        SENIOR,
        llm=ScriptedLLM(['[{"factType": "FAMILY", "content": "손자가 놀러 온다."}]']),
        fact_client=fact_client,
    )

    assert fact_client.submissions[0]["now_local"].isoformat() == "2026-08-07T15:04:00+09:00"


def test_the_weekday_check_scores_against_the_raw_utterance(frozen_clock):
    """요일 검산의 채점 기준은 어르신 발화 **원문**이어야 한다 (S15P11E102-392).

    검산이 존재하는 이유는 모델의 날짜 계산이 비결정적이기 때문이다. 그런데
    대조 대상까지 모델의 출력(추출된 content)으로 삼으면, 같은 모델의 답을 같은
    모델의 답으로 채점하는 셈이라 검산이 성립하지 않는다. 그래서 프롬프트에 실은
    것과 같은 원문이 검증까지 내려가는지를 배선으로 고정한다.
    """
    frozen_clock(start=SEOUL_FRIDAY_1504)
    _seed_time_zone("Asia/Seoul")
    _enqueue(content="다음 주 화요일 세 시에 병원 가")

    fact_client = RecordingFactClient()
    ticks.extraction_flush(
        SENIOR,
        llm=ScriptedLLM(['[{"factType": "FAMILY", "content": "손자가 놀러 온다."}]']),
        fact_client=fact_client,
    )

    assert fact_client.submissions[0]["utterance"] == "다음 주 화요일 세 시에 병원 가"


def test_without_a_time_zone_no_date_is_invented(frozen_clock):
    """★ 시간대를 모르면 UTC 로 떨어지지 않는다 — 날짜를 아예 주지 않는다.

    UTC 로 떨어뜨리면 어르신이 말한 "오후 두 시"가 아홉 시간 어긋난 절대 시각이
    되고, 그 값은 사람 확인 없이 보호자 화면의 일정이 된다. 기능이 무음이 되는
    쪽이 틀린 일정이 생기는 쪽보다 낫다.
    """
    frozen_clock(start=SEOUL_FRIDAY_1504)
    _seed_time_zone(None)
    _enqueue(content="다음 주 화요일 세 시에 병원 가")
    llm = ScriptedLLM(["[]"])

    ticks.extraction_flush(SENIOR, llm=llm, fact_client=RecordingFactClient())

    assert "오늘이 며칠인지 알 수 없습니다" in llm.prompts[0]
    # UTC 날짜(2026-08-07)든 무엇이든, 날짜처럼 보이는 문자열이 하나도 없어야 한다.
    assert _LOOKS_LIKE_A_DATE.search(llm.prompts[0]) is None


def test_an_unknown_time_zone_does_not_kill_the_tick(frozen_clock):
    """젯슨에 tzdata 가 없으면 ZoneInfo 가 던진다. 그 예외가 틱을 죽이면 큐가 멈춘다."""
    frozen_clock(start=SEOUL_FRIDAY_1504)
    _seed_time_zone("Mars/Olympus")
    _enqueue(content="다음 주 화요일 세 시에 병원 가")
    llm = ScriptedLLM(["[]"])

    result = ticks.extraction_flush(SENIOR, llm=llm, fact_client=RecordingFactClient())

    assert result == {"processed": 1, "submitted": 0, "failed": 0, "given_up": 0}
    assert "오늘이 며칠인지 알 수 없습니다" in llm.prompts[0]


def test_the_time_zone_is_read_once_per_senior_not_once_per_row(frozen_clock, monkeypatch):
    """행마다 문맥 캐시를 다시 읽지 않는다. 다만 어르신이 섞이면 각자의 시간대를 쓴다.

    시간대만 캐시하고 '시각'은 행마다 따로 계산한다 — 기준점이 발화가 말해진
    시각(created_at)이라 행마다 다르기 때문이다.
    """
    frozen_clock(start=SEOUL_FRIDAY_1504)
    _seed_time_zone("Asia/Seoul")
    for _ in range(3):
        _enqueue()

    calls = []
    original = ticks._extraction_zone

    def counting(senior_id):
        calls.append(senior_id)
        return original(senior_id)

    monkeypatch.setattr(ticks, "_extraction_zone", counting)

    ticks.extraction_flush(SENIOR, llm=ScriptedLLM(["[]"] * 3),
                           fact_client=RecordingFactClient())

    assert calls == [SENIOR]


# ── 9. 약속의 선택 키가 파서를 통과한다 ──────────────────────────────────────


def test_starts_at_and_title_survive_the_parser(frozen_clock):
    """★ 이 화이트리스트가 없으면 startsAt 이 여기서 조용히 버려진다.

    파서가 항목을 factType/content 두 키로 재조립하므로, 목록을 넓히지 않으면
    약속은 언제나 '시각 없음'으로 강등된다 — 아무도 모르는 조용한 실패다.
    """
    frozen_clock(start=SEOUL_FRIDAY_1504)
    _seed_time_zone("Asia/Seoul")
    _enqueue(content="다음 주 화요일 세 시에 병원 가")
    llm = ScriptedLLM([
        '[{"factType": "APPOINTMENT", "content": "다음 주 화요일 오후 세 시에 병원에 간다.",'
        ' "title": "병원 진료", "startsAt": "2026-08-11T15:00:00+09:00"}]'
    ])
    fact_client = RecordingFactClient()

    ticks.extraction_flush(SENIOR, llm=llm, fact_client=fact_client)

    assert fact_client.submissions[0]["facts"] == [{
        "factType": "APPOINTMENT",
        "content": "다음 주 화요일 오후 세 시에 병원에 간다.",
        "title": "병원 진료",
        "startsAt": "2026-08-11T15:00:00+09:00",
    }]


def test_keys_outside_the_contract_do_not_survive_the_parser(frozen_clock):
    """서버는 proposedValue 의 임의 키를 그대로 care_record.details 에 넣는다.

    모델이 붙인 아무 키나 통과시키면 그것이 보호자 화면까지 샌다.
    """
    frozen_clock(start=SEOUL_FRIDAY_1504)
    _seed_time_zone("Asia/Seoul")
    _enqueue()
    llm = ScriptedLLM([
        '[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다.",'
        ' "confidence": 0.9, "note": "모델이 지어 붙인 키", "endsAt": "2026-08-11T16:00:00+09:00"}]'
    ])
    fact_client = RecordingFactClient()

    ticks.extraction_flush(SENIOR, llm=llm, fact_client=fact_client)

    assert fact_client.submissions[0]["facts"] == [
        {"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}
    ]


def test_a_blank_optional_key_is_dropped_rather_than_sent_empty(frozen_clock):
    """빈 문자열 startsAt 을 실어 보내면 서버가 그것을 못 읽고 '지금'으로 채운다."""
    frozen_clock(start=SEOUL_FRIDAY_1504)
    _seed_time_zone("Asia/Seoul")
    _enqueue()
    llm = ScriptedLLM([
        '[{"factType": "APPOINTMENT", "content": "병원에 간다.", "title": "", "startsAt": "  "}]'
    ])
    fact_client = RecordingFactClient()

    ticks.extraction_flush(SENIOR, llm=llm, fact_client=fact_client)

    assert fact_client.submissions[0]["facts"] == [
        {"factType": "APPOINTMENT", "content": "병원에 간다."}
    ]


# ── 7. 스케줄러 등록 ─────────────────────────────────────────────────────────


def test_extraction_flush_is_registered_in_the_scheduler():
    pytest.importorskip("apscheduler")
    scheduler = scheduler_module.build_scheduler(SENIOR)
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "extraction_flush" in job_ids


def test_extraction_flush_runs_inside_run_all_ticks_once(monkeypatch, frozen_clock):
    frozen_clock(start=1_700_000_000.0)
    calls = []
    monkeypatch.setattr(ticks, "extraction_flush", lambda senior_id: calls.append(senior_id))

    scheduler_module.run_all_ticks_once(SENIOR)

    assert calls == [SENIOR]
