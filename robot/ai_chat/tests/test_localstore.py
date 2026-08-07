"""로컬 운영 상태 저장소 검증 — 특히 '재부팅을 넘어 살아남는가'.

이 파일이 검증하는 완료 조건
    프로세스 재시작 후 silence_level·occupancy·대기 중인 발화 제안이 복원된다.

'재시작'을 어떻게 흉내내는가
    db.py 가 연결을 프로세스 안에서 캐시하므로, 그냥 다시 읽으면 같은 연결이 나온다.
    close_all() 로 연결을 전부 닫으면 다음 접근이 파일을 새로 열고, 그게 재부팅 후
    첫 읽기와 같은 경로다. 파일에 실제로 남았는지를 확인하는 유일한 방법이다.

참고
    CLAUDE.md §5 (소유권), §10 (침묵 사다리), §18 (SD카드 제약)
"""

import pytest

from bomi_ai_chat.localstore import audio_cache, db, proposals, runtime

SENIOR = "senior-1"


@pytest.fixture(autouse=True)
def isolated_localstore(monkeypatch, tmp_path):
    """테스트마다 빈 저장소 디렉터리를 쓰고, 끝나면 연결을 닫는다.

    연결을 닫지 않으면 다음 테스트가 이전 테스트의 열린 파일을 물려받는다.
    """
    monkeypatch.setenv("LOCALSTORE_DIR", str(tmp_path / "localstore"))
    db.close_all()
    yield
    db.close_all()


def restart() -> None:
    """프로세스 재시작을 흉내낸다. 연결을 닫아 다음 접근이 파일을 새로 열게 한다."""
    db.close_all()


# ── 런타임 상태 ────────────────────────────────────────────────────────────


def test_cold_start_defaults_are_conservative():
    """한 번도 저장한 적 없으면 보수적인 기본값이 나온다.

    occupancy 가 HOME 이 아니라 UNKNOWN 인 것이 핵심이다. 집에 있다고 가정하면
    어쩌면 빈 집을 상대로 침묵 사다리가 돌아가고 보호자에게 오탐이 간다.
    """
    state = runtime.load(SENIOR)

    assert state["occupancy"] == "UNKNOWN"
    assert state["rest_state"] == "UNKNOWN"
    assert state["silence_level"] == 0


def test_runtime_state_survives_restart():
    """(완료 조건) 재시작 후 silence_level 과 occupancy 가 복원된다.

    이게 깨지면 사다리가 재부팅마다 0 으로 돌아가고, 응답 없는 어르신에 대한 시계가
    처음부터 다시 흐른다. 에스컬레이션이 그만큼 늦어지는 조용한 실패다.
    """
    runtime.save(SENIOR, silence_level=2, occupancy="HOME", last_spoke_at=1234.5)

    restart()

    state = runtime.load(SENIOR)
    assert state["silence_level"] == 2
    assert state["occupancy"] == "HOME"
    assert state["last_spoke_at"] == pytest.approx(1234.5)


def test_save_rejects_unknown_field():
    """모르는 필드는 조용히 무시하지 않고 실패한다.

    조용히 무시하면 오타 하나 때문에 사다리 값이 저장되지 않는데도 아무도 모른다.
    """
    with pytest.raises(ValueError, match="unknown runtime_state fields"):
        runtime.save(SENIOR, silence_levle=3)  # 의도적 오타


def test_reset_silence_clears_level_and_stamps_interaction(frozen_clock):
    """어르신이 반응하면 사다리와 상호작용 시각이 '함께' 갱신된다."""
    frozen_clock(start=5_000.0)

    runtime.save(SENIOR, silence_level=3)
    runtime.reset_silence(SENIOR)

    state = runtime.load(SENIOR)
    assert state["silence_level"] == 0
    assert state["last_user_interaction_at"] == pytest.approx(5_000.0)


# ── 발화 제안 큐 ───────────────────────────────────────────────────────────


def test_pending_proposals_survive_restart():
    """(완료 조건) 재시작 후 대기 중인 발화 제안이 복원된다.

    09:00 복약 알림이 큐에 든 뒤 08:59 에 재시작되면, 메모리 큐였다면 그 알림은
    사라진다. 복약 알림이 조용히 사라지는 것은 품질 문제가 아니라 안전 문제다.
    """
    proposals.enqueue(
        SENIOR,
        {"intent": "schedule", "priority": "medium", "seed": "약 드셨어요?", "origin": "sched"},
    )

    restart()

    pending = proposals.pending(SENIOR)
    assert len(pending) == 1
    assert pending[0]["intent"] == "schedule"
    assert pending[0]["priority"] == "medium"
    assert pending[0]["seed"] == "약 드셨어요?"


def test_pending_returns_expired_proposals_too(frozen_clock):
    """만료된 제안도 돌려준다. 폐기 여부는 게이트의 판단이다.

    저장소가 미리 지워버리면 "인사는 버리고 복약은 남긴다"를 게이트가 표현할 수 없다.
    """
    sim = frozen_clock(start=1_000.0)
    proposals.enqueue(
        SENIOR,
        {"intent": "greeting", "priority": "event", "expires_at": 1_045.0},
    )
    sim.advance(100)  # TTL 을 한참 넘김

    assert len(proposals.pending(SENIOR)) == 1


def test_discard_expired_removes_only_expired(frozen_clock):
    """만료 정리는 TTL 이 있는 것만 지운다. TTL 없는 복약 알림은 남아야 한다."""
    sim = frozen_clock(start=1_000.0)
    proposals.enqueue(
        SENIOR, {"intent": "greeting", "priority": "event", "expires_at": 1_045.0}
    )
    # 복약은 expires_at 이 없다. 사라지는 대신 나중에 다시 와야 한다.
    proposals.enqueue(SENIOR, {"intent": "schedule", "priority": "medium"})
    sim.advance(100)

    removed = proposals.discard_expired(SENIOR)

    assert removed == 1
    remaining = proposals.pending(SENIOR)
    assert len(remaining) == 1
    assert remaining[0]["intent"] == "schedule"


def test_discard_removes_single_proposal():
    """게이트가 이긴 제안을 지울 수 있다."""
    proposals.enqueue(SENIOR, {"intent": "companion", "priority": "ambient"})
    row_id = proposals.pending(SENIOR)[0]["meta"]["_row_id"]

    proposals.discard(row_id)

    assert proposals.pending(SENIOR) == []


def test_proposals_are_isolated_per_senior():
    """두 어르신의 큐가 섞이지 않는다.

    섞이면 한 사람에게 할 말이 다른 사람에게 나간다.
    """
    proposals.enqueue(SENIOR, {"intent": "companion", "priority": "low"})
    proposals.enqueue("senior-2", {"intent": "schedule", "priority": "high"})

    assert len(proposals.pending(SENIOR)) == 1
    assert len(proposals.pending("senior-2")) == 1


def test_runtime_state_is_isolated_per_senior():
    """두 어르신의 사다리가 섞이지 않는다.

    섞이면 한 사람의 발화가 다른 사람의 에스컬레이션을 억제한다.
    """
    runtime.save(SENIOR, silence_level=3)
    runtime.save("senior-2", silence_level=0)

    assert runtime.load(SENIOR)["silence_level"] == 3
    assert runtime.load("senior-2")["silence_level"] == 0


# ── 캐시 오디오 ────────────────────────────────────────────────────────────


def test_cached_audio_survives_restart():
    """오프라인 프로브용 오디오가 재시작 후에도 찾아진다."""
    audio_cache.register("probe.critical.1", b"RIFF-fake-wav", "어르신, 괜찮으세요?")

    restart()

    path = audio_cache.lookup("probe.critical.1")
    assert path is not None
    assert path.read_bytes() == b"RIFF-fake-wav"


def test_cached_audio_lookup_returns_none_when_file_vanished():
    """등록부에 있어도 파일이 없으면 None 이다.

    없는 경로를 돌려주면 호출부는 오프라인 상황에서 두 번 실패한다.
    """
    path = audio_cache.register("probe.critical.2", b"x", "괜찮으세요?")
    path.unlink()

    assert audio_cache.lookup("probe.critical.2") is None


def test_cached_audio_rejects_path_separators():
    """cache_key 가 파일명이 되므로 경로 탈출을 막는다."""
    with pytest.raises(ValueError, match="경로 구분자"):
        audio_cache.register("../escape", b"x", "text")
