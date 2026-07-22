"""노트북 마이크/스피커를 이용한 AudioInput/AudioOutput 구현체."""

import io
import wave

import numpy as np
import sounddevice as sd

from .base import AudioInput, AudioOutput

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SECONDS = 0.5       # 이 단위로 소리를 체크
SILENCE_THRESHOLD = 300   # 이 값보다 작으면 "무음"으로 판단 (환경에 따라 조정 필요)
SILENCE_LIMIT_SECONDS = 3.0  # 이 시간 동안 계속 무음이면 녹음 종료
MAX_SECONDS = 15          # 안전장치: 아무리 길어도 이 시간이 지나면 강제 종료


class LaptopMicInput(AudioInput):
    """무음이 감지될 때까지 녹음하는 노트북 마이크 입력."""

    def capture(self) -> bytes:
        print("[녹음 시작] 말씀해주세요...")

        frames = []
        silence_chunks = 0
        chunk_frame_count = int(CHUNK_SECONDS * SAMPLE_RATE)
        silence_chunk_limit = int(SILENCE_LIMIT_SECONDS / CHUNK_SECONDS)
        max_chunks = int(MAX_SECONDS / CHUNK_SECONDS)

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16"
        )
        stream.start()

        for _ in range(max_chunks):
            chunk, _ = stream.read(chunk_frame_count)
            frames.append(chunk.copy())

            volume = np.abs(chunk).mean()
            print(f"volume: {volume:.1f}")  # 임시로 볼륨값 출력

            if volume < SILENCE_THRESHOLD:
                silence_chunks += 1
            else:
                silence_chunks = 0

            if silence_chunks >= silence_chunk_limit:
                break

        stream.stop()
        stream.close()
    

        print("[녹음 종료]")
        recording = np.concatenate(frames)
        return self._to_wav_bytes(recording)

    def _to_wav_bytes(self, recording: np.ndarray) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(recording.tobytes())
        return buffer.getvalue()


class LaptopSpeakerOutput(AudioOutput):
    """노트북 스피커로 오디오 바이트를 재생한다."""

    def play(self, audio_bytes: bytes) -> None:
        buffer = io.BytesIO(audio_bytes)
        with wave.open(buffer, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            frames = wav_file.readframes(wav_file.getnframes())
            data = np.frombuffer(frames, dtype="int16")

        sd.play(data, samplerate=sample_rate)
        sd.wait()