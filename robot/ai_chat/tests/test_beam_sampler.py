"""소리 방향 이력 수집을 검증한다."""

import pytest

from bomi_ai_chat.audio_io.beam_sampler import BeamDirectionSampler


class _FakeClock:
    """수동으로 흘릴 수 있는 단조 시계."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _sampler(values, clock, **kwargs) -> BeamDirectionSampler:
    stream = iter(values)

    def read() -> float:
        return next(stream)

    return BeamDirectionSampler(read, clock=clock, **kwargs)


def test_recent_returns_only_samples_inside_the_window() -> None:
    clock = _FakeClock()
    sampler = _sampler([10.0, 20.0, 30.0], clock)

    sampler.sample_once()
    clock.advance(1.0)
    sampler.sample_once()
    clock.advance(1.0)
    sampler.sample_once()

    # 최근 1.5초 안에는 마지막 두 개만 들어온다.
    assert sampler.recent(1.5) == [20.0, 30.0]


def test_old_samples_are_dropped_from_history() -> None:
    clock = _FakeClock()
    sampler = _sampler([10.0, 20.0], clock, history_sec=1.0)

    sampler.sample_once()
    clock.advance(5.0)
    sampler.sample_once()

    assert sampler.recent(10.0) == [20.0]


def test_read_failures_are_skipped_without_raising() -> None:
    clock = _FakeClock()

    def read() -> float:
        raise RuntimeError("xvf_host 없음")

    sampler = BeamDirectionSampler(read, clock=clock)
    sampler.sample_once()

    assert sampler.recent(10.0) == []


def test_recent_is_empty_for_a_non_positive_window() -> None:
    clock = _FakeClock()
    sampler = _sampler([10.0], clock)
    sampler.sample_once()

    assert sampler.recent(0.0) == []


def test_rejects_invalid_intervals() -> None:
    with pytest.raises(ValueError):
        BeamDirectionSampler(lambda: 0.0, interval_sec=0.0)
    with pytest.raises(ValueError):
        BeamDirectionSampler(lambda: 0.0, history_sec=0.0)


def test_stop_is_safe_without_start() -> None:
    BeamDirectionSampler(lambda: 0.0).stop()
