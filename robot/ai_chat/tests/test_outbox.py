"""보호자 알림 발신 큐 검증.

이 파일이 검증하는 완료 조건
    네트워크 차단 상태에서 알림 3건을 적재하고, 복구 후 전부 전송되며 지연 표시가
    포함된다.

왜 이걸 테스트로 만드는가
    이 큐의 실패 모양은 조용하다. 알림이 그냥 안 가고, 로그를 뒤지지 않으면 아무도
    모른다. 그리고 안 가는 그 알림이 T1 일 수 있다. 그래서 "네트워크가 끊겼다가
    돌아온다"를 시나리오로 재현해 둔다.

참고
    CLAUDE.md §9 (티어), §18 (오프라인은 안전 문제다), §19 (Outbox)
"""

import pytest

from bomi_ai_chat import policy
from bomi_ai_chat.localstore import db, outbox
from bomi_ai_chat.notify import NotifyError


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()


class FakeChannel:
    """네트워크를 끊고 붙일 수 있는 대역 채널.

    online 을 False 로 두면 NotifyError 를 던진다. 실제 채널이 아직 없으므로
    (구현은 후속 티켓) 이 대역이 유일한 검증 수단이다.
    """

    def __init__(self, *, online: bool = True):
        self.online = online
        self.delivered: list[tuple[str, dict]] = []

    def notify_guardian(self, tier: str, payload: dict) -> None:
        if not self.online:
            raise NotifyError("network unreachable")
        self.delivered.append((tier, payload))


def test_offline_alerts_queue_then_all_deliver_after_recovery(frozen_clock):
    """(완료 조건) 차단 중 3건 적재 → 복구 후 전부 전송 + 지연 표시.

    이 테스트가 이 티켓의 핵심이다. 큐가 없으면 이 3건은 전부 사라진다.
    """
    sim = frozen_clock(start=10_000.0)
    channel = FakeChannel(online=False)

    # ── 네트워크 차단 상태에서 3건이 발생한다 ──
    outbox.enqueue("T1", {"reason": "no_response", "n": 1})
    outbox.enqueue("T1", {"reason": "no_response", "n": 2})
    outbox.enqueue("T2", {"reason": "daily_summary", "n": 3})

    # 저장은 성공해야 한다. 전송 실패가 적재를 막으면 안 된다.
    assert outbox.pending_count() == 3

    # 이 시점의 flush 는 전부 실패한다. 다만 '버려지지는' 않는다.
    result = outbox.flush(channel)
    assert result == {"sent": 0, "failed": 3, "gave_up": 0}
    assert outbox.pending_count() == 3
    assert channel.delivered == []

    # ── 네트워크가 돌아온다 ──
    channel.online = True
    # 백오프 때문에 바로는 못 나간다. 상한만큼 지나면 반드시 나가야 한다.
    sim.advance(policy.OUTBOX_BACKOFF_MAX_SEC + 1)

    result = outbox.flush(channel)

    assert result["sent"] == 3
    assert outbox.pending_count() == 0
    assert len(channel.delivered) == 3

    # 지연 표시: 사건 시각으로부터 임계치를 넘겨 도착했으므로 전부 표시된다.
    for _tier, payload in channel.delivered:
        assert payload["delayed"] is True
        assert payload["occurred_at"] == pytest.approx(10_000.0)
        assert payload["delayed_by_sec"] > policy.OUTBOX_DELAYED_THRESHOLD_SEC

    # 순서: 큐의 순서가 사건의 순서다. 보호자가 역순으로 읽으면 안 된다.
    assert [payload["n"] for _, payload in channel.delivered] == [1, 2, 3]


def test_prompt_delivery_is_not_marked_delayed(frozen_clock):
    """바로 나간 알림에는 지연 표시가 붙지 않는다.

    전부 '지연됨'으로 표시하면 표시가 의미를 잃는다.
    """
    frozen_clock(start=10_000.0)
    channel = FakeChannel()

    outbox.enqueue("T1", {"reason": "chest_pain"})
    outbox.flush(channel)

    _, payload = channel.delivered[0]
    assert "delayed" not in payload


def test_enqueue_is_durable_across_restart():
    """적재된 알림은 재시작을 넘어 살아남는다.

    이 큐만 synchronous=FULL 인 이유가 이것이다. 전원이 끊겨도 남아야 한다.
    """
    outbox.enqueue("T1", {"reason": "no_response"})

    db.close_all()  # 재시작

    assert outbox.pending_count() == 1


def test_t1_is_never_given_up(frozen_clock):
    """T1 은 시도 횟수로 버리지 않는다.

    생명 안전 알림이다. 오래 실패하더라도 큐에 남아 있어야 하고, 남아 있다는 사실
    자체가 운영자가 알아야 할 상태다.
    """
    sim = frozen_clock(start=0.0)
    channel = FakeChannel(online=False)

    outbox.enqueue("T1", {"reason": "self_harm"})

    # T2 의 포기 기준을 훌쩍 넘겨 재시도한다.
    for _ in range(policy.OUTBOX_MAX_ATTEMPTS["T2"] + 5):
        sim.advance(policy.OUTBOX_BACKOFF_MAX_SEC + 1)
        outbox.flush(channel)

    assert outbox.pending_count() == 1, "T1 은 포기 대상이 아니다"


def test_t2_gives_up_after_max_attempts(frozen_clock):
    """T2 는 정해진 횟수 뒤에 포기한다.

    어제의 일일 요약을 영원히 재시도할 이유는 없다. 단 포기는 기록으로 남는다.
    """
    sim = frozen_clock(start=0.0)
    channel = FakeChannel(online=False)

    outbox.enqueue("T2", {"reason": "daily_summary"})

    for _ in range(policy.OUTBOX_MAX_ATTEMPTS["T2"]):
        sim.advance(policy.OUTBOX_BACKOFF_MAX_SEC + 1)
        outbox.flush(channel)

    assert outbox.pending_count() == 0


def test_backoff_prevents_immediate_retry(frozen_clock):
    """실패 직후에는 재시도하지 않는다.

    백오프가 없으면 끊긴 네트워크를 틱마다 두드려 배터리를 쓴다.
    """
    frozen_clock(start=0.0)
    channel = FakeChannel(online=False)

    outbox.enqueue("T1", {"reason": "x"})
    outbox.flush(channel)

    channel.online = True
    # 아직 백오프 중이므로 꺼내지 않아야 한다.
    result = outbox.flush(channel)

    assert result["sent"] == 0
    assert channel.delivered == []


def test_t4_cannot_be_enqueued():
    """T4 는 큐에 들어갈 수 없다.

    '절대 보내지 않음'이므로 발신 큐에 있을 수 없다. 조용히 무시하면 "보냈다고
    믿는" 코드가 남으므로 요란하게 실패한다. T4 는 기억의 공개범위로 표현된다.
    """
    with pytest.raises(ValueError, match="T4"):
        outbox.enqueue("T4", {"content": "그냥 우리 둘만의 얘기"})


def test_unknown_tier_is_rejected():
    """정의되지 않은 티어를 성공으로 처리하지 않는다."""
    with pytest.raises(ValueError, match="알 수 없는 tier"):
        outbox.enqueue("T9", {})


def test_flush_batch_size_limits_one_pass():
    """한 번의 flush 가 큐를 다 비우지 않는다.

    오래 끊겼다 복구되면 수십 건이 한꺼번에 나가서 보호자 화면을 도배한다.
    """
    channel = FakeChannel()
    for index in range(5):
        outbox.enqueue("T2", {"n": index})

    result = outbox.flush(channel, limit=2)

    assert result["sent"] == 2
    assert outbox.pending_count() == 3
