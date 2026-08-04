"""대화 파이프라인의 단계별 복구와 반복 실행 회귀 테스트."""

import logging

import pytest

import bomi_ai_chat.pipeline as pipeline_module
from bomi_ai_chat.pipeline import (
    CAPTURE_ERROR_MESSAGE,
    EMPTY_STT_MESSAGE,
    RESPONSE_ERROR_MESSAGE,
    STT_ERROR_MESSAGE,
    WEATHER_ERROR_MESSAGE,
    ConversationPipeline,
)


class AudioSequenceExhausted(BaseException):
    """대역의 녹음 결과가 동나면 던진다. 일부러 Exception 이 아니라 BaseException 이다.

    왜 BaseException 인가
        pipeline._run_once_inner 는 capture 실패를 `except Exception` 으로 삼키고
        루프를 계속 돈다(단계 하나가 실패해도 로봇이 멈추면 안 되기 때문이다).
        대역이 평범한 예외를 던지면 그 관용이 '무한 반복'으로 바뀌어, 테스트가
        실패하지 않고 그냥 안 끝난다. Exception 밖으로 나가야 pytest 가 잡는다.

    이게 없으면 무엇이 조용히 망가지는가
        S15P11E102-299 가 정확히 이것이었다. capture 시그니처가 어긋나 매 호출이
        TypeError 로 죽었고, 루프가 outcome 을 하나도 소비하지 못한 채 영원히 돌았다.
        push 훅이 300초 타임아웃까지 매달렸고, 증상이 '실패'가 아니라 '안 끝남'이라
        원인을 게이트에서 찾게 만들었다.
    """


class SequenceAudioInput:
    """정해진 순서대로 녹음 결과를 돌려주는 마이크 대역.

    주의사항
        - capture 의 시그니처는 실제 어댑터(audio_io/base.py:14)와 '같아야 한다'.
          어긋나면 파이프라인은 그것을 마이크 고장과 구분하지 못한다.
        - onset_timeout_seconds 를 기록해 두는 이유: 대화 세션의 무응답 종료가 이
          값을 실제로 넘기는지 테스트가 확인할 수 있어야 하기 때문이다.
    """

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.onset_timeouts: list[float | None] = []

    def capture(self, onset_timeout_seconds: float | None = None):
        self.onset_timeouts.append(onset_timeout_seconds)
        if not self.outcomes:
            raise AudioSequenceExhausted(
                "SequenceAudioInput 의 녹음 결과가 동났습니다. "
                "루프가 예상보다 많이 돌고 있습니다."
            )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class RecordingAudioOutput:
    def __init__(self, error=None):
        self.error = error
        self.played = []

    def play(self, audio):
        if self.error:
            raise self.error
        self.played.append(audio)


class StubSTT:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def transcribe(self, audio):
        self.calls.append(audio)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class StubLLM:
    def __init__(self, outcome="반가워요."):
        self.outcome = outcome
        self.calls = []

    def generate(self, text, weather_data=None):
        self.calls.append((text, weather_data))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class StubWeather:
    def __init__(self, outcome=None):
        self.outcome = outcome or {"기온": "20"}
        self.calls = []

    def get_forecast(self, city):
        self.calls.append(city)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class RecordingTTS:
    def __init__(self, error=None):
        self.error = error
        self.texts = []

    def synthesize(self, text):
        self.texts.append(text)
        if self.error:
            raise self.error
        return f"audio:{text}".encode()


def build_pipeline(
    settings_factory,
    *,
    audio_input=None,
    audio_output=None,
    detector=None,
    sleep=lambda seconds: None,
    monotonic=None,
):
    kwargs = {
        "medical_query_detector": detector or (lambda text: False),
        "sleep": sleep,
    }
    if monotonic is not None:
        kwargs["monotonic"] = monotonic
    pipeline = ConversationPipeline(
        audio_input or SequenceAudioInput(b"wav"),
        audio_output or RecordingAudioOutput(),
        settings_factory(),
        **kwargs,
    )
    pipeline.stt = StubSTT("안녕하세요")
    pipeline.llm = StubLLM()
    pipeline.weather = StubWeather()
    pipeline.tts = RecordingTTS()
    return pipeline


def test_successful_turn_returns_observable_result(
    settings_factory,
    caplog,
):
    times = iter((10.0, 10.25))
    output = RecordingAudioOutput()
    pipeline = build_pipeline(
        settings_factory,
        audio_output=output,
        monotonic=lambda: next(times),
    )

    with caplog.at_level(logging.INFO):
        result = pipeline.run_once()

    assert result.succeeded is True
    assert result.user_text == "안녕하세요"
    assert result.response_text == "반가워요."
    assert result.audio_played is True
    assert result.failure_stages == ()
    assert result.duration_seconds == pytest.approx(0.25)
    assert output.played == ["audio:반가워요.".encode()]
    assert "duration_seconds=0.250" in caplog.text


def test_empty_stt_skips_routing_and_llm(settings_factory):
    pipeline = build_pipeline(settings_factory)
    pipeline.stt = StubSTT(" \n ")
    detector_calls = []
    pipeline._is_medical_query = lambda text: detector_calls.append(text)

    result = pipeline.run_once()

    assert result.user_text == ""
    assert result.response_text == EMPTY_STT_MESSAGE
    assert result.failure_stages == ("stt_empty",)
    assert result.audio_played is True
    assert detector_calls == []
    assert pipeline.llm.calls == []
    assert pipeline.tts.texts == [EMPTY_STT_MESSAGE]


@pytest.mark.parametrize(
    ("stage", "configure", "expected_message"),
    [
        (
            "capture",
            lambda pipeline: setattr(
                pipeline,
                "audio_in",
                SequenceAudioInput(RuntimeError("microphone")),
            ),
            CAPTURE_ERROR_MESSAGE,
        ),
        (
            "stt",
            lambda pipeline: setattr(
                pipeline,
                "stt",
                StubSTT(TimeoutError("stt")),
            ),
            STT_ERROR_MESSAGE,
        ),
        (
            "routing",
            lambda pipeline: setattr(
                pipeline,
                "_is_medical_query",
                lambda text: (_ for _ in ()).throw(RuntimeError("router")),
            ),
            RESPONSE_ERROR_MESSAGE,
        ),
        (
            "llm",
            lambda pipeline: setattr(
                pipeline,
                "llm",
                StubLLM(RuntimeError("llm")),
            ),
            RESPONSE_ERROR_MESSAGE,
        ),
    ],
)
def test_stage_failure_becomes_spoken_user_message(
    settings_factory,
    caplog,
    stage,
    configure,
    expected_message,
):
    pipeline = build_pipeline(settings_factory)
    configure(pipeline)

    with caplog.at_level(logging.ERROR):
        result = pipeline.run_once()

    assert result.failure_stages == (stage,)
    assert result.response_text == expected_message
    assert result.audio_played is True
    assert pipeline.tts.texts == [expected_message]
    assert f"stage={stage}" in caplog.text


def test_weather_failure_does_not_fall_through_to_llm(settings_factory):
    pipeline = build_pipeline(settings_factory)
    pipeline.stt = StubSTT("서울 날씨 알려줘")
    pipeline.weather = StubWeather(RuntimeError("weather"))

    result = pipeline.run_once()

    assert result.failure_stages == ("weather",)
    assert result.response_text == WEATHER_ERROR_MESSAGE
    assert pipeline.weather.calls == ["서울"]
    assert pipeline.llm.calls == []


def test_supported_city_weather_is_passed_to_llm(settings_factory):
    pipeline = build_pipeline(settings_factory)
    pipeline.stt = StubSTT("서울 날씨 알려줘")
    forecast = {"기온": "20", "하늘상태": "1"}
    pipeline.weather = StubWeather(forecast)

    result = pipeline.run_once()

    assert result.succeeded is True
    assert pipeline.weather.calls == ["서울"]
    assert pipeline.llm.calls == [("서울 날씨 알려줘", forecast)]


def test_weather_without_city_skips_external_lookup(settings_factory):
    pipeline = build_pipeline(settings_factory)
    pipeline.stt = StubSTT("오늘 날씨 알려줘")

    result = pipeline.run_once()

    assert result.succeeded is True
    assert pipeline.weather.calls == []
    assert pipeline.llm.calls == [("오늘 날씨 알려줘", None)]


def test_medical_failure_is_recovered(
    monkeypatch,
    settings_factory,
):
    pipeline = build_pipeline(
        settings_factory,
        detector=lambda text: True,
    )
    monkeypatch.setattr(
        pipeline_module,
        "handle_medical_query",
        lambda text: (_ for _ in ()).throw(RuntimeError("medical")),
    )

    result = pipeline.run_once()

    assert result.failure_stages == ("medical",)
    assert result.response_text == RESPONSE_ERROR_MESSAGE
    assert result.audio_played is True


def test_invalid_router_result_is_recovered(settings_factory):
    pipeline = build_pipeline(
        settings_factory,
        detector=lambda text: "medical",
    )

    result = pipeline.run_once()

    assert result.failure_stages == ("routing",)
    assert result.response_text == RESPONSE_ERROR_MESSAGE
    assert pipeline.llm.calls == []


def test_tts_failure_preserves_generated_text(
    settings_factory,
    capsys,
):
    output = RecordingAudioOutput()
    pipeline = build_pipeline(settings_factory, audio_output=output)
    pipeline.tts = RecordingTTS(RuntimeError("tts"))

    result = pipeline.run_once()

    assert result.failure_stages == ("tts",)
    assert result.response_text == "반가워요."
    assert result.audio_played is False
    assert output.played == []
    assert "[응답 텍스트] 반가워요." in capsys.readouterr().out


def test_tts_failure_keeps_original_stage(settings_factory):
    pipeline = build_pipeline(
        settings_factory,
        audio_input=SequenceAudioInput(RuntimeError("microphone")),
    )
    pipeline.tts = RecordingTTS(RuntimeError("tts"))

    result = pipeline.run_once()

    assert result.failure_stages == ("capture", "tts")
    assert result.response_text == CAPTURE_ERROR_MESSAGE
    assert result.audio_played is False


def test_playback_failure_preserves_generated_text(settings_factory):
    pipeline = build_pipeline(
        settings_factory,
        audio_output=RecordingAudioOutput(RuntimeError("speaker")),
    )

    result = pipeline.run_once()

    assert result.failure_stages == ("playback",)
    assert result.response_text == "반가워요."
    assert result.audio_played is False


def test_loop_continues_after_failed_turn(settings_factory):
    delays = []
    output = RecordingAudioOutput()
    pipeline = build_pipeline(
        settings_factory,
        audio_input=SequenceAudioInput(
            RuntimeError("microphone"),
            b"wav",
        ),
        audio_output=output,
        sleep=delays.append,
    )

    turns = pipeline.run(max_turns=2)

    assert turns == 2
    assert pipeline.tts.texts == [CAPTURE_ERROR_MESSAGE, "반가워요."]
    assert len(output.played) == 2
    assert delays == [1.0]


def test_loop_stops_cleanly_on_keyboard_interrupt(settings_factory):
    pipeline = build_pipeline(
        settings_factory,
        audio_input=SequenceAudioInput(KeyboardInterrupt()),
    )

    assert pipeline.run() == 0
    assert pipeline.tts.texts == []


@pytest.mark.parametrize("max_turns", [0, -1, True, 1.5])
def test_loop_rejects_invalid_turn_limit(settings_factory, max_turns):
    pipeline = build_pipeline(settings_factory)

    with pytest.raises(ValueError, match="max_turns"):
        pipeline.run(max_turns=max_turns)
