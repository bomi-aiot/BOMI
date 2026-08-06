"""마이크 입력 레벨을 재고 AUDIO_SILENCE_THRESHOLD 를 실측으로 정한다.

왜 이 도구가 있나 (S15P11E102-233)
    실기 점검 첫 STT 에서 이렇게 나왔다.

        말한 것:   오늘 날씨가 참 좋네요
        받아쓴 것: 저 몸이야 날씨 좋다.

    로그의 청크별 볼륨은 26 / 132 / 12 / 11 / 171 / 702 / 85 / 69 / 226 / 178 / 56 / 15
    였고, 임계치는 300 이었다. **발화 중 300 을 넘은 청크가 하나뿐이었다.**

    즉 로봇은 사람이 말하는 동안 대부분을 '침묵'으로 판단하고 있었다. 그 상태에서
    6청크(3초) 연속 침묵이면 녹음을 끊으므로, 문장 앞뒤가 잘린 채 STT 로 간다.
    ASR 이 나쁜 것이 아니라 잘린 오디오를 받은 것이다.

    300 은 누가 재서 넣은 값이 아니라 추정값이다(CLAUDE.md §24 "튜닝 다이얼, 실측
    필요"). 이 도구는 그 실측을 한다 — 추측으로 낮추면 이번엔 에어컨 소리에 반응한다.

무엇을 하는가
    1) 조용히 있을 때의 배경 소음을 잰다
    2) 평소 말투로 말할 때의 볼륨을 잰다
    3) 둘 사이에서 임계치를 제안한다

실행
    python tests/manual/mic_level_check.py

주의사항
    - 실제 사용할 자리에서, 실제 거리에서 재야 한다. 마이크에 입을 대고 재면
      그 값은 아무 데도 쓸 수 없다.
    - 어르신은 개발자보다 작게, 느리게, 멀리서 말한다. 여기서 나온 값은 첫 근사다.
"""

import statistics
import sys
import time

import numpy as np
import sounddevice as sd

from bomi_ai_chat.audio_io.sounddevice_backend import _resolve_input_device
from bomi_ai_chat.config import get_settings


def measure(device, capture_sr: int, channels: int, chunk_frames: int,
            seconds: float, label: str) -> list[float]:
    """지정한 시간 동안 청크별 평균 진폭을 모은다."""
    volumes: list[float] = []
    print(f"\n[{label}] {seconds:.0f}초...")
    started = time.monotonic()
    with sd.InputStream(samplerate=capture_sr, channels=channels, dtype="int16",
                        device=device, blocksize=chunk_frames) as stream:
        while time.monotonic() - started < seconds:
            chunk, overflowed = stream.read(chunk_frames)
            if overflowed:
                print("  (오버플로우 — 값이 부정확할 수 있습니다)")
            channel0 = chunk[:, 0] if chunk.ndim > 1 else chunk
            volume = float(np.abs(channel0.astype(np.int32)).mean())
            volumes.append(volume)
            bar = "#" * min(60, int(volume / 20))
            print(f"  {volume:7.1f} {bar}")
    return volumes


def summarize(name: str, volumes: list[float]) -> dict:
    if not volumes:
        return {}
    stats = {
        "min": min(volumes),
        "median": statistics.median(volumes),
        "p90": sorted(volumes)[int(len(volumes) * 0.9) - 1],
        "max": max(volumes),
    }
    print(f"\n[{name}]  최소 {stats['min']:.1f}  중앙 {stats['median']:.1f}  "
          f"상위10% {stats['p90']:.1f}  최대 {stats['max']:.1f}")
    return stats


def main() -> int:
    settings = get_settings()
    device = _resolve_input_device(settings.audio_input_device)
    info = sd.query_devices(device)
    capture_sr = int(info["default_samplerate"]) or settings.audio_sample_rate
    chunk_frames = max(1, int(settings.audio_chunk_seconds * capture_sr))

    print(f"장치      [{device}] {info['name']}")
    print(f"채널      {settings.audio_channels} (장치 최대 {info['max_input_channels']})")
    print(f"샘플레이트 {capture_sr}Hz")
    print(f"현재 임계치 AUDIO_SILENCE_THRESHOLD={settings.audio_silence_threshold:.0f}")

    input("\n조용히 계신 상태로 Enter 를 누르세요 (배경 소음 측정) ")
    quiet = measure(device, capture_sr, settings.audio_channels, chunk_frames, 4, "배경 소음")

    input("\n평소 말투로 계속 말할 준비가 되면 Enter "
          "(예: '오늘 날씨가 참 좋네요' 를 천천히 반복) ")
    speech = measure(device, capture_sr, settings.audio_channels, chunk_frames, 8, "발화")

    quiet_stats = summarize("배경 소음", quiet)
    speech_stats = summarize("발화", speech)
    if not quiet_stats or not speech_stats:
        print("측정값이 없습니다.")
        return 1

    current = settings.audio_silence_threshold
    above = sum(1 for v in speech if v >= current)
    print(f"\n현재 임계치 {current:.0f} 로는 발화 청크 {len(speech)}개 중 "
          f"{above}개만 '말하는 중'으로 봅니다 ({above / len(speech) * 100:.0f}%).")

    # 배경 소음 위, 발화 중앙값 아래. 둘 사이가 좁으면 마이크 게인을 올려야 한다.
    suggested = (quiet_stats["p90"] + speech_stats["median"]) / 2
    print(f"\n제안 임계치: {suggested:.0f}")
    print(f"  배경 상위10% {quiet_stats['p90']:.1f} 보다 위,"
          f" 발화 중앙 {speech_stats['median']:.1f} 보다 아래여야 합니다.")

    if speech_stats["median"] < quiet_stats["p90"] * 2:
        print("\n★ 발화와 배경 소음이 충분히 벌어지지 않았습니다.")
        print("  임계치를 어디에 두어도 둘 중 하나는 틀립니다. 먼저 게인을 올리십시오:")
        print("   - Windows 설정 > 시스템 > 소리 > 입력 > 장치 속성 > 볼륨을 올린다")
        print("   - 마이크에 더 가까이 (실제 사용 거리 안에서)")
        print("   - 다른 장치 인덱스를 시도한다 (tests/list_audio_devices.py)")
        return 1

    print("\n적용하려면 .env 에:")
    print(f"  AUDIO_SILENCE_THRESHOLD={suggested:.0f}")
    print("\n그 뒤 stt_smoke.py 를 다시 돌려 받아쓰기가 나아지는지 확인하십시오.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
