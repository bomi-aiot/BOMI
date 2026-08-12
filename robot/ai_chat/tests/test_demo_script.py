"""demo_script.ScriptedResponder — 시연 영상 대본 매칭 로직.

무엇을 지키는가
    영상 촬영 중에 확인할 수 없는 것들이다: 우선순위(응급이 통증 잡담을
    이기는가), 체인(응급 2단·병원 2단·산책 맥락), chain_only 격리("분"이
    전역에서 오탐하지 않는가), 폴백 두 종, TTS 사전 합성 캐시.
"""

from bomi_ai_chat.demo_script import (
    FALLBACK_RESPONSE,
    FAREWELL_FALLBACK_RESPONSE,
    ScriptedResponder,
    build_scripted_responder,
)


def _responder() -> ScriptedResponder:
    return ScriptedResponder()


# ── 전역 매칭 ────────────────────────────────────────────────────────────


def test_walk_utterance_matches_daily_chat():
    r = _responder()
    assert "산책" in r.respond("공원 산책하고 왔어")


def test_emergency_wins_over_chronic_pain():
    r = _responder()
    # "가슴이 답답하고"와 "숨이 안" 둘 다 응급 검사어다. 통증("허리") 항목이
    # 아니라 응급 확인 질문이 나와야 한다 — triage 와 같은 우선순위.
    assert r.respond("가슴이 너무 답답하고 숨이 안 쉬어져") == (
        "많이 불편하세요? 가족분께 연락드릴까요?"
    )


def test_chronic_pain_is_a_normal_sympathy_turn():
    r = _responder()
    assert "허리" in r.respond("허리가 너무 아파")


def test_forget_request_gets_privacy_answer():
    r = _responder()
    assert "기억" in r.respond("오늘 이야기는 기억하지 마")


def test_unmatched_utterance_falls_back():
    r = _responder()
    assert r.respond("어제 텔레비전에서 드라마를 봤어") == FALLBACK_RESPONSE


# ── 체인 (force_next / next_ids) ────────────────────────────────────────


def test_emergency_escalates_on_any_next_utterance():
    r = _responder()
    r.respond("숨이 안 쉬어져")
    # 실제 triage 규칙이 "명확한 부정 외 전부 에스컬레이션"이므로, 대본도
    # 다음 발화의 내용과 무관하게 연락 문장이 나간다.
    assert r.respond("응, 너무 답답해") == (
        "제가 가족분께 연락드릴게요. 잠깐만 이대로 계세요."
    )
    # 체인이 소진된 뒤에는 평소 매칭으로 돌아온다.
    assert "고마워" in r.respond("고마워")


def test_clinic_search_is_two_turns_like_real_logic():
    r = _responder()
    first = r.respond("근처 정형외과 찾아줘")
    assert "어느 지역" in first
    # 지역명은 임의 문자열이라 키워드로 못 잡는다 — force_next 로 결과가 나온다.
    assert "정형외과" in r.respond("진평동이야")


def test_walk_context_chains_two_followups():
    r = _responder()
    r.respond("공원 산책하고 왔어")
    second = r.respond("한 삼십 분 걸었어")
    assert "잘 걸으신" in second
    third = r.respond("다리는 괜찮아")
    assert "보약" in third


def test_chain_only_entry_never_matches_globally():
    r = _responder()
    # "분"은 walk_duration 의 검사어지만 chain_only 라 산책 맥락 밖에서는
    # 절대 걸리면 안 된다 — "기분", "충분" 오탐 방지.
    assert r.respond("삼십 분 정도 걸었어") == FALLBACK_RESPONSE


def test_reset_clears_pending_chain():
    r = _responder()
    r.respond("숨이 안 쉬어져")
    r.reset()
    assert r.respond("공원 산책하고 왔어") != (
        "제가 가족분께 연락드릴게요. 잠깐만 이대로 계세요."
    )


# ── 마무리 폴백 ─────────────────────────────────────────────────────────


def test_farewell_hint_uses_farewell_fallback_when_unmatched():
    # 루프의 is_farewell 이 잡았는데("여기까지 하자") 대본 farewell 검사어에는
    # 없는 발화 — 일반 폴백("말씀 더 해 주세요")으로 대화를 이어가려 들면 안 된다.
    r = _responder()
    assert r.respond("오늘은 여기까지 하자", farewell=True) == (
        FAREWELL_FALLBACK_RESPONSE
    )


def test_farewell_keyword_matches_scripted_goodbye():
    r = _responder()
    assert "보미야" in r.respond("고마워", farewell=True)


# ── TTS 사전 합성 캐시 ──────────────────────────────────────────────────


class _CountingTts:
    def __init__(self):
        self.calls = 0

    def synthesize(self, text: str) -> bytes:
        self.calls += 1
        return text.encode()


def test_warm_synthesizes_each_response_once():
    r = _responder()
    tts = _CountingTts()
    warmed = r.warm(tts)
    assert warmed == len(r.all_responses())
    # 재생 시에는 캐시에서 나온다 — 추가 합성 왕복 없음.
    calls_after_warm = tts.calls
    r.audio_for(tts, r.all_responses()[0])
    assert tts.calls == calls_after_warm


def test_audio_for_synthesizes_unknown_text_once():
    # 백엔드 시드 문장은 사전 합성 목록에 없다 — 첫 재생만 합성하고 캐시된다.
    r = _responder()
    tts = _CountingTts()
    r.audio_for(tts, "할머니, 다녀오셨어요?")
    r.audio_for(tts, "할머니, 다녀오셨어요?")
    assert tts.calls == 1


# ── env 스위치 ──────────────────────────────────────────────────────────


def test_builder_returns_none_when_disabled(monkeypatch):
    monkeypatch.delenv("SCRIPTED_DIALOGUE_ENABLED", raising=False)
    assert build_scripted_responder() is None


def test_builder_reads_idle_timeout(monkeypatch):
    monkeypatch.setenv("SCRIPTED_DIALOGUE_ENABLED", "true")
    monkeypatch.setenv("SCRIPTED_IDLE_TIMEOUT_SEC", "3")
    responder = build_scripted_responder()
    assert responder is not None
    assert responder.idle_timeout_sec == 3.0


def test_builder_ignores_bad_idle_timeout(monkeypatch):
    monkeypatch.setenv("SCRIPTED_DIALOGUE_ENABLED", "true")
    monkeypatch.setenv("SCRIPTED_IDLE_TIMEOUT_SEC", "abc")
    responder = build_scripted_responder()
    assert responder is not None
    assert responder.idle_timeout_sec is None
