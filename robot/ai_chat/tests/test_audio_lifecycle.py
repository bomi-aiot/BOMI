"""공통 오디오 백엔드의 장치 전달과 예외 시 해제 회귀 테스트."""

import importlib
import io
import sys
import wave
from types import ModuleType

import pytest

from bomi_ai_chat.config import ConfigurationError


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
def backend_module(monkeypatch):
    """오디오·수치 라이브러리 없이 공통 백엔드의 수명주기만 불러온다."""

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

    module_names = (
        "bomi_ai_chat.audio_io.laptop",
        "bomi_ai_chat.audio_io.robot",
        "bomi_ai_chat.audio_io.sounddevice_backend",
    )
    previous_modules = {
        name: sys.modules.pop(name)
        for name in module_names
        if name in sys.modules
    }
    try:
        module = importlib.import_module(module_names[-1])
        yield module
    finally:
        for name in module_names:
            sys.modules.pop(name, None)
        sys.modules.update(previous_modules)


def audio_input(backend_module, *, device="USB Mic"):
    return backend_module.SoundDeviceAudioInput(
        device=device,
        sample_rate=16000,
        channels=1,
        chunk_seconds=0.5,
        silence_threshold=300.0,
        silence_limit_seconds=3.0,
        max_seconds=15.0,
    )


def test_laptop_adapter_forwards_audio_settings(
    backend_module,
    settings_factory,
):
    laptop = importlib.import_module("bomi_ai_chat.audio_io.laptop")
    settings = settings_factory(
        AUDIO_INPUT_DEVICE="1",
        AUDIO_OUTPUT_DEVICE="USB Speaker",
        AUDIO_SAMPLE_RATE="48000",
        AUDIO_CHANNELS="2",
        AUDIO_CHUNK_SECONDS="0.25",
        AUDIO_SILENCE_THRESHOLD="125",
        AUDIO_SILENCE_LIMIT_SECONDS="2",
        AUDIO_MAX_SECONDS="10",
    )

    audio_in = laptop.LaptopMicInput(settings)
    audio_out = laptop.LaptopSpeakerOutput(settings)

    assert audio_in.device == 1
    assert audio_in.sample_rate == 48000
    assert audio_in.channels == 2
    assert audio_in.chunk_seconds == 0.25
    assert audio_in.silence_threshold == 125.0
    assert audio_in.silence_limit_seconds == 2.0
    assert audio_in.max_seconds == 10.0
    assert audio_out.device == "USB Speaker"


def test_robot_adapter_requires_and_forwards_explicit_devices(
    backend_module,
    settings_factory,
):
    robot = importlib.import_module("bomi_ai_chat.audio_io.robot")
    settings = settings_factory(
        AUDIO_MODE="robot",
        AUDIO_INPUT_DEVICE="Jetson Mic",
        AUDIO_OUTPUT_DEVICE="2",
    )

    audio_in = robot.RobotAudioInput(settings)
    audio_out = robot.RobotAudioOutput(settings)

    assert audio_in.device == "Jetson Mic"
    assert audio_out.device == 2


def test_robot_adapter_rejects_default_laptop_devices(
    backend_module,
    settings_factory,
):
    robot = importlib.import_module("bomi_ai_chat.audio_io.robot")
    settings = settings_factory()

    with pytest.raises(ConfigurationError, match="AUDIO_INPUT_DEVICE"):
        robot.RobotAudioInput(settings)


@pytest.mark.parametrize("failure_stage", ["start", "read"])
def test_microphone_stream_closes_when_start_or_read_fails(
    monkeypatch,
    backend_module,
    failure_stage,
):
    stream = FailingInputStream(failure_stage)
    stream_options = {}

    def input_stream(**kwargs):
        stream_options.update(kwargs)
        return stream

    monkeypatch.setattr(backend_module.sd, "InputStream", input_stream)

    with pytest.raises(RuntimeError, match=f"audio {failure_stage} failed"):
        audio_input(backend_module).capture()

    assert stream_options["device"] == "USB Mic"
    assert stream_options["samplerate"] == 16000
    assert stream.closed is True
    assert stream.stopped is (failure_stage == "read")


@pytest.mark.parametrize("failure_stage", [None, "play", "wait"])
def test_speaker_is_stopped_after_success_or_failure(
    monkeypatch,
    backend_module,
    failure_stage,
):
    calls = []

    def play(data, samplerate, device):
        calls.append(("play", samplerate, device))
        if failure_stage == "play":
            raise RuntimeError("playback failed")

    def wait():
        calls.append(("wait",))
        if failure_stage == "wait":
            raise RuntimeError("playback failed")

    monkeypatch.setattr(backend_module.sd, "play", play)
    monkeypatch.setattr(backend_module.sd, "wait", wait)
    monkeypatch.setattr(
        backend_module.sd,
        "stop",
        lambda: calls.append(("stop",)),
    )

    output = backend_module.SoundDeviceAudioOutput(device=2)
    if failure_stage:
        with pytest.raises(RuntimeError, match="playback failed"):
            output.play(wav_bytes())
    else:
        output.play(wav_bytes())

    assert calls[0] == ("play", 16000, 2)
    assert calls[-1] == ("stop",)
