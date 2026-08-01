"""PortAudio(sounddevice) 기반의 공통 녹음·재생 구현."""

from __future__ import annotations

import io
import math
import queue
import wave

import numpy as np
import sounddevice as sd

from .base import AudioInput, AudioOutput

AudioDevice = int | str | None


def _resolve_input_device(device: AudioDevice) -> AudioDevice:
    """device가 '이름(문자열)'이면 그 이름을 포함하는 입력 장치를 찾아 인덱스로 바꾼다.

    USB를 다시 꽂아 장치 인덱스가 바뀌어도, 매 실행마다 이름으로 다시 찾으므로
    항상 올바른 마이크를 자동으로 잡는다. 정수 인덱스나 None이면 그대로 둔다.

    같은 이름이 여러 호스트 API(MME/DirectSound/WASAPI)로 잡히면 'DirectSound'를
    우선한다(ReSpeaker에서 이 조합이 안정적으로 동작). 없으면 첫 입력 매칭을 쓴다.
    """
    if not isinstance(device, str):
        return device

    name_hint = device.lower()
    matches = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and name_hint in dev["name"].lower():
            hostapi = sd.query_hostapis(dev["hostapi"])["name"]
            matches.append((idx, hostapi))

    if not matches:
        raise RuntimeError(
            f"이름에 '{device}'가 들어간 입력 장치를 찾을 수 없습니다. "
            "tests/list_audio_devices.py로 장치 이름을 확인하세요."
        )

    for idx, hostapi in matches:
        if "directsound" in hostapi.lower():
            return idx
    return matches[0][0]


def _resample_int16(mono: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """선형 보간으로 모노 int16 신호의 샘플레이트를 변환한다.

    녹음을 네이티브 레이트로 받은 뒤 마지막에 한 번에 목표 레이트로 바꾼다.
    (스트리밍 도중 실시간 리샘플링은 타이밍 왜곡을 일으켜 피한다.)
    """
    if orig_sr == target_sr or len(mono) == 0:
        return mono
    duration = len(mono) / orig_sr
    target_len = max(1, int(duration * target_sr))
    src_idx = np.arange(len(mono))
    tgt_idx = np.linspace(0, len(mono) - 1, num=target_len)
    resampled = np.interp(tgt_idx, src_idx, mono.astype(np.float64))
    return resampled.astype(np.int16)


class SoundDeviceAudioInput(AudioInput):
    """설정된 PortAudio 입력 장치에서 무음까지 PCM 음성을 녹음한다."""

    def __init__(
        self,
        *,
        device: AudioDevice,
        sample_rate: int,
        channels: int,
        chunk_seconds: float,
        silence_threshold: float,
        silence_limit_seconds: float,
        max_seconds: float,
    ) -> None:
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_seconds = chunk_seconds
        self.silence_threshold = silence_threshold
        self.silence_limit_seconds = silence_limit_seconds
        self.max_seconds = max_seconds

    def capture(self) -> bytes:
        print("[녹음 시작] 말씀해주세요...")

        # 일부 장치(예: ReSpeaker + Windows DirectSound)는 blocking read로 열면
        # 계속 0(무음)만 반환한다. 그래서 스트림을 한 번만 열고 콜백으로 청크를
        # 받는 방식으로 캡처한다. 또한 장치의 네이티브 샘플레이트로 녹음한 뒤
        # 마지막에 목표 레이트로 변환한다(16000으로 직접 열면 일부 장치에서
        # 무음이 되는 문제를 피하기 위함).
        # 이름으로 지정한 경우 현재 인덱스로 변환(재연결로 번호가 바뀌어도 자동 대응).
        device = _resolve_input_device(self.device)

        try:
            capture_sr = int(sd.query_devices(device)["default_samplerate"])
        except Exception:
            capture_sr = self.sample_rate
        if capture_sr <= 0:
            capture_sr = self.sample_rate

        chunk_frame_count = max(1, math.ceil(self.chunk_seconds * capture_sr))
        silence_chunk_limit = max(
            1,
            math.ceil(self.silence_limit_seconds / self.chunk_seconds),
        )
        max_chunks = max(1, math.ceil(self.max_seconds / self.chunk_seconds))

        chunk_queue: queue.Queue = queue.Queue()

        def _callback(indata, _frames, _time_info, status):
            if status:
                print(f"[오디오 상태] {status}")
            chunk_queue.put(indata.copy())

        frames = []
        silence_chunks = 0
        with sd.InputStream(
            samplerate=capture_sr,
            channels=self.channels,
            dtype="int16",
            device=device,
            blocksize=chunk_frame_count,
            callback=_callback,
        ):
            for _ in range(max_chunks):
                # timeout을 둬야 Ctrl+C(KeyboardInterrupt)에 반응할 수 있다.
                # timeout 없는 blocking get은 Windows에서 Ctrl+C를 못 받아 멈춘다.
                try:
                    chunk = chunk_queue.get(timeout=1.0)
                except queue.Empty:
                    continue  # 잠깐 안 와도 루프를 돌며 인터럽트를 받을 수 있게 함
                frames.append(chunk)

                # 2채널 이상이면 왼쪽(채널 0)으로 볼륨 판단.
                # ReSpeaker는 채널 0이 하드웨어 처리된(빔포밍/AEC) 신호다.
                channel0 = chunk[:, 0] if chunk.ndim > 1 else chunk
                volume = np.abs(channel0.astype(np.int32)).mean()
                print(f"volume: {volume:.1f}")

                if volume < self.silence_threshold:
                    silence_chunks += 1
                else:
                    silence_chunks = 0

                if silence_chunks >= silence_chunk_limit:
                    break

        print("[녹음 종료]")
        if not frames:
            # 한 청크도 못 받은 경우(장치 문제 등) 빈 무음 WAV 반환.
            return self._to_wav_bytes(np.zeros(0, dtype=np.int16))
        recording = np.concatenate(frames, axis=0)
        # 왼쪽 채널만 모노로 사용 -> 목표 샘플레이트로 변환.
        mono = recording[:, 0] if recording.ndim > 1 else recording
        mono = _resample_int16(mono, capture_sr, self.sample_rate)
        return self._to_wav_bytes(mono)

    def _to_wav_bytes(self, recording: np.ndarray) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)  # 왼쪽 채널만 사용하므로 모노
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(recording.tobytes())
        return buffer.getvalue()


class SoundDeviceAudioOutput(AudioOutput):
    """설정된 PortAudio 출력 장치로 16-bit PCM WAV를 재생한다."""

    def __init__(self, *, device: AudioDevice) -> None:
        self.device = device

    def play(self, audio_bytes: bytes) -> None:
        buffer = io.BytesIO(audio_bytes)
        with wave.open(buffer, "rb") as wav_file:
            if wav_file.getsampwidth() != 2:
                raise ValueError("16-bit PCM WAV만 재생할 수 있습니다.")
            channels = wav_file.getnchannels()
            sample_rate = wav_file.getframerate()
            frames = wav_file.readframes(wav_file.getnframes())
            data = np.frombuffer(frames, dtype=np.int16)
            if channels > 1:
                data = data.reshape(-1, channels)

        try:
            sd.play(data, samplerate=sample_rate, device=self.device)
            sd.wait()
        finally:
            sd.stop()
