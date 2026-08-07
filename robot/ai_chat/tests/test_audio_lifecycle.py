"""공통 오디오 백엔드의 장치 전달과 예외 시 해제 회귀 테스트."""

import importlib
import io
import sys
import wave
from types import ModuleType

import pytest

from bomi_ai_chat.config import ConfigurationError


class FailingInputStream:
    """실패하는 입력 스트림 대역.

    S15P11E102-214 가 캡처 경로를 `with sd.InputStream(...)` + 콜백 방식으로 바꿔서
    이 대역도 컨텍스트 매니저가 됐다. 검증하려는 것은 그대로다 — 열다가 실패하든
    쓰는 중에 실패하든 스트림이 닫히는가.

    open  단계: __enter__ 에서 터진다. 아무것도 열리지 않았으므로 누수도 없다.
    read  단계: 들어와서 데이터를 기다리는 중에 터진다. __exit__ 가 반드시 불려야 한다.
    """

    def __init__(self, failure_stage):
        self.failure_stage = failure_stage
        self.started = False
        self.closed = False

    def __enter__(self):
        if self.failure_stage == "start":
            raise RuntimeError("audio start failed")
        self.started = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        return False  # 예외를 삼키지 않는다


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
    # S15P11E102-214 가 이름으로 장치를 찾는 경로를 넣으면서 query_devices 와
    # query_hostapis 가 필요해졌다. 여기서 검증하려는 것은 스트림 수명주기이지 장치
    # 탐색이 아니므로, 이름으로 찾는 테스트가 통과하도록 장치 하나를 노출한다.
    fake_sounddevice.query_devices = lambda: [
        {"name": "USB Mic", "max_input_channels": 2, "hostapi": 0},
    ]
    fake_sounddevice.query_hostapis = lambda index: {"name": "DirectSound"}

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
    """장치 지정 없이 로봇 어댑터를 만들면 거부한다.

    입력이 아니라 '출력'으로 검사하는 이유: S15P11E102-214 에서 입력 기본값이
    "reSpeaker" 로 바뀌었다. 출력은 여전히 기본값이 없어서, 지정 없이 로봇 모드로
    올리려는 실수를 여전히 여기서 잡는다.
    """
    robot = importlib.import_module("bomi_ai_chat.audio_io.robot")
    settings = settings_factory()

    with pytest.raises(ConfigurationError, match="AUDIO_OUTPUT_DEVICE"):
        robot.RobotAudioOutput(settings)


def test_microphone_stream_reports_failure_to_open(monkeypatch, backend_module):
    """스트림을 여는 데 실패하면 그 오류가 그대로 올라온다."""
    stream = FailingInputStream("start")
    stream_options = {}

    def input_stream(**kwargs):
        stream_options.update(kwargs)
        return stream

    monkeypatch.setattr(backend_module.sd, "InputStream", input_stream)

    with pytest.raises(RuntimeError, match="audio start failed"):
        audio_input(backend_module).capture()

    # 이름으로 준 장치가 인덱스로 해소되어 넘어간다 (S15P11E102-214).
    assert stream_options["device"] == 0
    assert stream_options["samplerate"] == 16000
    assert stream.closed is False, "열리지 않았으므로 닫을 것도 없다"


def test_microphone_stream_closes_when_capture_body_fails(monkeypatch, backend_module):
    """캡처 도중 실패해도 스트림이 닫힌다.

    214 이후로는 `with` 가 이것을 보장한다. 그래도 테스트를 남기는 이유는, 누군가
    다시 수동 start/stop 으로 되돌리면 조용히 마이크가 열린 채 남기 때문이다.
    """
    stream = FailingInputStream("read")

    def input_stream(**kwargs):
        return stream

    def exploding_queue(*args, **kwargs):
        raise RuntimeError("audio read failed")

    monkeypatch.setattr(backend_module.sd, "InputStream", input_stream)
    # 스트림 안에서 데이터를 기다리는 지점에서 터뜨린다.
    monkeypatch.setattr(backend_module.queue.Queue, "get", exploding_queue)

    with pytest.raises(RuntimeError, match="audio read failed"):
        audio_input(backend_module).capture()

    assert stream.started is True
    assert stream.closed is True


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
