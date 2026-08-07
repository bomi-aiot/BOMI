"""expiresAt/occurredAt 타임스탬프 파싱 — 백엔드가 실제로 보내는 형식들.

왜 이 파일이 있는가 (2026-08-07 실기)
    백엔드는 Java ``Instant`` 라 나노초 9자리 + ``Z`` 로 보낸다
    (``2026-08-06T15:32:32.163415068Z``). 젯슨의 Python 3.10
    ``fromisoformat`` 은 소수부가 3 또는 6자리일 때만 파싱하므로,
    실기에서 **백엔드가 보낸 NAVIGATE 가 전부 계약 위반으로 거절**됐다.
    이동이 한 번도 시작되지 못한 원인이라 회귀 테스트로 못박는다.
"""

from __future__ import annotations

import pytest

from bridge.contract import _parse_iso_datetime


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-06T15:32:32.163415068Z",   # ★ 백엔드 실제 형식 (나노초 9자리)
        "2026-08-06T15:32:32.163415Z",       # 마이크로초 6자리
        "2026-08-06T15:32:32.163Z",          # 밀리초 3자리
        "2026-08-06T15:32:32.1Z",            # 1자리
        "2026-08-06T15:32:32Z",              # 소수부 없음
        "2026-08-07T00:32:32.163415068+09:00",  # 오프셋 표기 + 나노초
        "2026-08-07T00:32:32+09:00",
    ],
)
def test_parses_every_shape_the_backend_sends(value: str) -> None:
    parsed = _parse_iso_datetime(value)
    assert parsed is not None, f"파싱 실패: {value}"
    assert parsed.tzinfo is not None


def test_nanoseconds_are_truncated_not_rounded() -> None:
    """9자리를 6자리로 자른다 — 반올림하면 만료 판정이 1마이크로초 흔들린다."""
    parsed = _parse_iso_datetime("2026-08-06T15:32:32.163415968Z")

    assert parsed is not None
    assert parsed.microsecond == 163415


def test_short_fraction_is_padded_to_microseconds() -> None:
    parsed = _parse_iso_datetime("2026-08-06T15:32:32.5Z")

    assert parsed is not None
    assert parsed.microsecond == 500000


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-06T15:32:32",          # ★ 오프셋 없음 — 시계 비교가 무의미하다
        "2026-08-06T15:32:32.163415",   # 소수부는 있으나 오프셋 없음
        "not-a-timestamp",
        "",
    ],
)
def test_rejects_values_without_a_usable_offset(value: str) -> None:
    assert _parse_iso_datetime(value) is None


@pytest.mark.parametrize("value", [None, 123, {}, []])
def test_rejects_non_strings(value: object) -> None:
    assert _parse_iso_datetime(value) is None
