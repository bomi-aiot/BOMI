"""마이크 방향 읽기 파싱을 검증한다."""

import pytest

from bomi_ai_chat.audio_io.beam_control import (
    azimuth_agreement,
    parse_azimuth_radians,
    parse_speaker_direction_deg,
    robust_azimuth_deg,
)

BANNER = (
    "Device (USB)::device_init() -- Found device "
    "VID: 10374 PID: 26 interface: 3"
)
VALUES = (
    "AEC_AZIMUTH_VALUES 0.45748 (26.21 deg) 1.48333 (84.99 deg) "
    "2.72276 (156.00 deg) 1.48333 (84.99 deg)"
)


def test_banner_numbers_do_not_shift_the_values() -> None:
    """★ 배너의 VID/PID 숫자가 섞이면 고정 빔 각도를 읽어 방향이 굳는다."""
    assert parse_azimuth_radians(f"{BANNER}\n{VALUES}") == [
        0.45748,
        1.48333,
        2.72276,
        1.48333,
    ]


def test_parses_output_without_banner() -> None:
    assert parse_azimuth_radians(VALUES) == [
        0.45748,
        1.48333,
        2.72276,
        1.48333,
    ]


def test_returns_none_when_the_line_is_missing() -> None:
    assert parse_azimuth_radians(BANNER) is None


def test_returns_none_when_values_are_incomplete() -> None:
    assert parse_azimuth_radians(
        "AEC_AZIMUTH_VALUES 0.45748 (26.21 deg) 1.48333 (84.99 deg)"
    ) is None


# ── 튀는 값 걸러내기 (2026-08-09 실측) ───────────────────────────────────────

# 왼쪽에 서서 15초간 말했을 때 실제로 읽힌 값들(절대각). 대부분 155도 부근에
# 모이지만 298·302·303 처럼 전혀 다른 값이 섞인다.
REAL_SAMPLES = [
    154.9, 303.9, 154.9, 298.0, 154.6, 154.5, 154.9, 154.2, 155.7, 155.3,
]


def test_outliers_do_not_move_the_result() -> None:
    result = robust_azimuth_deg(REAL_SAMPLES)

    assert result is not None
    assert abs(result - 155.0) < 3.0


def test_wraps_around_zero_correctly() -> None:
    result = robust_azimuth_deg([359.0, 1.0, 2.0])

    assert result is not None
    assert abs(((result + 180.0) % 360.0) - 180.0) < 3.0


def test_returns_none_without_samples() -> None:
    assert robust_azimuth_deg([]) is None


def test_single_sample_passes_through() -> None:
    assert robust_azimuth_deg([64.5]) == pytest.approx(64.5)


# ── 신뢰도 판정 (2026-08-09 실기: 뒤에서 불렀는데 +90도로 읽음) ──────────────


def test_agreement_counts_the_largest_cluster() -> None:
    angle, agreed = azimuth_agreement(
        [287.9, 288.1, 290.0, 290.8, 288.9, 287.5, 90.0, 90.0, 90.0])

    assert agreed == 6
    assert angle is not None
    assert abs(angle - 288.9) < 2.0


def test_agreement_is_low_when_samples_scatter() -> None:
    # 뒤편에서 부른 실측 — 어디에도 모이지 않는다.
    _, agreed = azimuth_agreement(
        [323.7, 90.8, 179.6, 356.9, 84.6, 322.4, 270.0, 179.6])

    assert agreed <= 3


def test_agreement_without_samples() -> None:
    assert azimuth_agreement([]) == (None, 0)


# ── 화자 방향(처리된 DoA) 파싱 ───────────────────────────────────────────────


def test_speaker_direction_is_converted_to_degrees() -> None:
    result = parse_speaker_direction_deg(
        "AUDIO_MGR_SELECTED_AZIMUTHS 5.98216 1.57080")

    assert result is not None
    assert abs(result - 342.8) < 0.5


def test_nan_means_the_device_has_no_direction() -> None:
    """★ NaN 은 "모름"이다. 숫자로 넘기면 로봇이 엉뚱하게 확신한다."""
    assert parse_speaker_direction_deg(
        "AUDIO_MGR_SELECTED_AZIMUTHS nan 5.61") is None


def test_missing_line_returns_none() -> None:
    assert parse_speaker_direction_deg("Device (USB)::device_init()") is None
