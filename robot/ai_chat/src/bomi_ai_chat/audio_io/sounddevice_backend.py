"""PortAudio(sounddevice) 기반의 공통 녹음·재생 구현."""

from __future__ import annotations

import io
import math
import wave

import noisereduce as nr
import numpy as np
import sounddevice as sd

from .base import AudioInput, AudioOutput

AudioDevice = int | str | None


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

        frames = []
        silence_chunks = 0
        chunk_frame_count = max(1, math.ceil(self.chunk_seconds * self.sample_rate))
        silence_chunk_limit = max(
            1,
            math.ceil(self.silence_limit_seconds / self.chunk_seconds),
        )
        max_chunks = max(1, math.ceil(self.max_seconds / self.chunk_seconds))

        stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            device=self.device,
        )
        try:
            stream.start()
            try:
                for _ in range(max_chunks):
                    chunk, _ = stream.read(chunk_frame_count)
                    frames.append(chunk.copy())

                    volume = np.abs(chunk.astype(np.int32)).mean()
                    print(f"volume: {volume:.1f}")

                    if volume < self.silence_threshold:
                        silence_chunks += 1
                    else:
                        silence_chunks = 0

                    if silence_chunks >= silence_chunk_limit:
                        break
            finally:
                stream.stop()
        finally:
            stream.close()

        print("[녹음 종료]")
        recording = np.concatenate(frames, axis=0)
        recording = self._reduce_noise(recording)
        return self._to_wav_bytes(recording)

    def _reduce_noise(self, recording: np.ndarray) -> np.ndarray:
        """각 채널의 첫 0.3초를 배경 소음 표본으로 삼아 제거한다."""

        audio_float = recording.astype(np.float32) / 32768.0
        channel_first = audio_float.T
        noise_frame_count = max(1, int(0.3 * self.sample_rate))
        noise_sample = channel_first[..., :noise_frame_count]

        reduced = nr.reduce_noise(
            y=channel_first,
            sr=self.sample_rate,
            y_noise=noise_sample,
            prop_decrease=0.8,
            stationary=True,
        )
        reduced = np.nan_to_num(reduced)
        reduced = np.clip(reduced * 32768.0, -32768, 32767).astype(np.int16)
        return reduced.T

    def _to_wav_bytes(self, recording: np.ndarray) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(self.channels)
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
