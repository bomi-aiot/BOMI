"""노트북 오디오 예외 경로의 장치 해제 회귀 테스트."""

import importlib
import io
import sys
import wave
from types import ModuleType

import pytest


class FailingInputStream:
    def __init__(self, failure_stage):
        self.failure_stage = failure_stage
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self):
        if self.failure_stage == "start":
            raise RuntimeError("audio start failed")
        self.started = True

    def read(self, frame_count):
        raise RuntimeError("audio read failed")

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00" * 10)
    return buffer.getvalue()


@pytest.fixture
def laptop_module(monkeypatch):
    """오디오·수치 라이브러리 없이 laptop 모듈의 수명주기만 불러온다."""

    fake_noisereduce = ModuleType("noisereduce")
    fake_noisereduce.reduce_noise = lambda **kwargs: kwargs["y"]

    fake_numpy = ModuleType("numpy")
    fake_numpy.ndarray = object
    fake_numpy.float32 = "float32"
    fake_numpy.int16 = "int16"
    fake_numpy.frombuffer = lambda frames, dtype: frames

    fake_sounddevice = ModuleType("sounddevice")
    fake_sounddevice.InputStream = None
    fake_sounddevice.play = None
    fake_sounddevice.wait = None
    fake_sounddevice.stop = None

    monkeypatch.setitem(sys.modules, "noisereduce", fake_noisereduce)
    monkeypatch.setitem(sys.modules, "numpy", fake_numpy)
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    module_name = "bomi_ai_chat.audio_io.laptop"
    previous_module = sys.modules.pop(module_name, None)
    try:
        module = importlib.import_module(module_name)
        yield module
    finally:
        sys.modules.pop(module_name, None)
        if previous_module is not None:
            sys.modules[module_name] = previous_module


@pytest.mark.parametrize("failure_stage", ["start", "read"])
def test_microphone_stream_closes_when_start_or_read_fails(
    monkeypatch,
    laptop_module,
    failure_stage,
):
    stream = FailingInputStream(failure_stage)
    monkeypatch.setattr(
        laptop_module.sd,
        "InputStream",
        lambda **kwargs: stream,
    )

    with pytest.raises(RuntimeError, match=f"audio {failure_stage} failed"):
        laptop_module.LaptopMicInput().capture()

    assert stream.closed is True
    assert stream.stopped is (failure_stage == "read")


@pytest.mark.parametrize("failure_stage", [None, "play", "wait"])
def test_speaker_is_stopped_after_success_or_failure(
    monkeypatch,
    laptop_module,
    failure_stage,
):
    calls = []

    def play(data, samplerate):
        calls.append(("play", samplerate))
        if failure_stage == "play":
            raise RuntimeError("playback failed")

    def wait():
        calls.append(("wait",))
        if failure_stage == "wait":
            raise RuntimeError("playback failed")

    monkeypatch.setattr(laptop_module.sd, "play", play)
    monkeypatch.setattr(laptop_module.sd, "wait", wait)
    monkeypatch.setattr(
        laptop_module.sd,
        "stop",
        lambda: calls.append(("stop",)),
    )

    if failure_stage:
        with pytest.raises(RuntimeError, match="playback failed"):
            laptop_module.LaptopSpeakerOutput().play(wav_bytes())
    else:
        laptop_module.LaptopSpeakerOutput().play(wav_bytes())

    assert calls[-1] == ("stop",)
