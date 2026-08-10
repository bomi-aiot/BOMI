"""발화 정제 회귀 — 프롬프트 부산물이 음성으로 새는 것을 막는다.

2026-08-10 실기에서 로봇이 실제로 말한 것들이 근거다. 로컬 추출 큐에 원문이
남아 있었고, 그중 두 가지가 기존 그물을 통과했다:

    "보미: 혹시 유진 님께서 민방위 훈련에 대해 말씀하신 건가요?"
    "없음⏎⏎어르신, 어떤 유명한 트로트 말씀이세요?"

_ECHOED_SPEAKER 는 어르신/사용자만 잡았고, 자리표시 토큰을 버리는 규칙은
아예 없었다.
"""

from __future__ import annotations

from bomi_ai_chat.graph.output import strip_prompt_scaffolding


def test_robot_name_prefix_is_stripped_but_content_survives():
    """'보미:' 는 라벨이지 말이 아니다. 다만 뒤의 내용은 진짜 말이다."""
    out = strip_prompt_scaffolding("보미: 오늘 날씨가 좋네요.")
    assert out == "오늘 날씨가 좋네요."


def test_elder_label_still_drops_the_whole_sentence():
    """어르신 라벨은 반대다 — 라벨만 떼면 어르신의 말이 로봇의 말이 된다."""
    assert strip_prompt_scaffolding("어르신: 밥 먹었어.") == ""


def test_placeholder_only_sentence_is_dropped():
    """모델이 빈 슬롯에 답한 '없음' 이 음성으로 나가면 안 된다."""
    out = strip_prompt_scaffolding("없음\n\n어르신, 어떤 트로트 말씀이세요?")
    assert "없음" not in out
    assert "어떤 트로트 말씀이세요?" in out


def test_placeholder_inside_a_real_sentence_survives():
    """부분 일치로 지우면 진짜 말을 잃는다 — 문장 전체가 자리표시일 때만 버린다."""
    text = "불편하신 데는 없음이 확인됐어요."
    assert strip_prompt_scaffolding(text) == text


def test_prefix_and_placeholder_together():
    """'보미: 없음' 처럼 겹쳐 와도 걸러야 한다 — 접두사를 뗀 뒤에 판정하기 때문."""
    assert strip_prompt_scaffolding("보미: 없음") == ""


def test_ordinary_speech_is_untouched():
    """정제기는 평범한 말을 건드리지 않는다."""
    text = "순자님, 오늘 기분은 어떠세요?"
    assert strip_prompt_scaffolding(text) == text
