"""Typecast TTS timeout, retry, WAV 응답 검증 테스트."""

import pytest

from bomi_ai_chat.http import InvalidResponseError
from bomi_ai_chat.tts.client import TTSClient
from bomi_ai_chat.turn_timer import TurnTimer
from tests.http_fakes import StubResponse, StubSession

WAV_BYTES = b"RIFF\x04\x00\x00\x00WAVEdata"


def tts_settings(settings_factory):
    return settings_factory(
        TYPECAST_API_KEY="typecast-key",
        TYPECAST_VOICE_ID="voice-id",
        HTTP_TIMEOUT_SECONDS="5",
        HTTP_MAX_ATTEMPTS="2",
        HTTP_BACKOFF_SECONDS="0.1",
        HTTP_MAX_BACKOFF_SECONDS="0.1",
    )


def test_tts_retries_502_and_returns_wav(settings_factory):
    session = StubSession(
        StubResponse(502),
        StubResponse(content=WAV_BYTES),
    )
    delays = []
    client = TTSClient(
        tts_settings(settings_factory),
        session=session,
        sleep=delays.append,
    )

    assert client.synthesize("안녕하세요") == WAV_BYTES
    assert delays == [0.1]
    assert session.calls[0]["timeout"] == 5.0


def test_tts_rejects_non_wav_response(settings_factory):
    session = StubSession(StubResponse(content=b'{"error":"unexpected"}'))
    client = TTSClient(tts_settings(settings_factory), session=session)

    with pytest.raises(InvalidResponseError, match="WAV"):
        client.synthesize("안녕하세요")


def test_tts_rejects_empty_text_before_request(settings_factory):
    session = StubSession()
    client = TTSClient(tts_settings(settings_factory), session=session)

    with pytest.raises(ValueError, match="비어 있지 않은 문자열"):
        client.synthesize(" ")

    assert session.calls == []


def test_tts_call_is_timed_and_logged_in_the_active_turn(settings_factory, caplog):
    client = TTSClient(
        tts_settings(settings_factory),
        session=StubSession(StubResponse(content=WAV_BYTES)),
    )
    timer = TurnTimer()

    with caplog.at_level("INFO"), timer.activate():
        client.synthesize("안녕하세요")

    assert timer.stages["tts"] >= 0
    assert any("tts latency" in record.message for record in caplog.records)
