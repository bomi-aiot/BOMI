"""어느 출력 장치에서 실제로 소리가 나는지 하나씩 들어본다.

왜 이 도구가 있나 (S15P11E102-233)
    실기 점검에서 이런 상태가 나왔다.

        - 로그는 전부 정상. 재생 스레드가 5초간 돌고 정상 종료
        - sd.play() 도 sd.wait() 도 예외 없이 끝남
        - **그런데 소리가 안 남**

    PortAudio 는 "존재하는 장치"를 열어 주고, 그 장치가 **실제로 스피커에 연결돼
    있는지는 알려주지 않는다.** 잭에 아무것도 안 꽂힌 Realtek 출력도 정상으로 열리고
    정상으로 재생을 마친다. 조용할 뿐이다.

    그래서 로그로는 영원히 알 수 없고, 귀로 확인하는 수밖에 없다. 이 도구가 그
    확인을 30초로 줄인다 — .env 를 고치고 앱을 재시작하며 하나씩 시도하는 대신.

실행
    python tests/manual/speaker_probe.py          # 출력 장치를 하나씩 들어본다
    python tests/manual/speaker_probe.py 4        # 특정 장치만
"""

import sys
import time

import numpy as np
import sounddevice as sd

TONE_SECONDS = 1.0
TONE_HZ = 440.0


def tone(sample_rate: int) -> np.ndarray:
    """1초짜리 440Hz 삐- 소리. 양 끝을 부드럽게 해서 딱 소리를 없앤다."""
    t = np.linspace(0, TONE_SECONDS, int(sample_rate * TONE_SECONDS), endpoint=False)
    wave = 0.25 * np.sin(2 * np.pi * TONE_HZ * t)
    fade = int(sample_rate * 0.02)
    wave[:fade] *= np.linspace(0, 1, fade)
    wave[-fade:] *= np.linspace(1, 0, fade)
    return (wave * 32767).astype(np.int16)


def try_device(index: int, info: dict) -> bool:
    rate = int(info["default_samplerate"]) or 44100
    print(f"\n[{index:2}] {info['name']}")
    print(f"     out={info['max_output_channels']}ch  {rate}Hz  "
          f"({sd.query_hostapis(info['hostapi'])['name']})")
    try:
        sd.play(tone(rate), samplerate=rate, device=index)
        sd.wait()
    except Exception as error:  # noqa: BLE001 - 못 여는 장치는 건너뛴다
        print(f"     ✕ 열지 못함: {error}")
        return False
    finally:
        sd.stop()
    print("     재생 완료 (소리가 났습니까?)")
    return True


def main() -> int:
    devices = sd.query_devices()

    if len(sys.argv) > 1:
        index = int(sys.argv[1])
        try_device(index, devices[index])
        return 0

    print("출력 장치를 하나씩 울립니다. 소리가 난 장치의 번호를 적어 두십시오.")
    print("(중복이 많습니다 — 같은 스피커가 MME / DirectSound / WASAPI 로 여러 번 잡힙니다)\n")

    playable = [(i, d) for i, d in enumerate(devices) if d["max_output_channels"] > 0]
    for index, info in playable:
        try_device(index, info)
        time.sleep(0.3)

    print("\n" + "=" * 60)
    print("소리가 난 번호를 .env 에 넣으십시오:")
    print("    AUDIO_OUTPUT_DEVICE=<번호>")
    print()
    print("아무 데서도 안 났다면 장치가 아니라 시스템 문제입니다:")
    print("  - Windows 설정 > 시스템 > 소리 > 출력 장치와 볼륨")
    print("  - 헤드폰 잭에 아무것도 안 꽂혀 있는지 (Realtek 출력이 잭으로 나갈 수 있음)")
    print("  - 모니터 스피커(HDMI)라면 모니터 자체 볼륨")
    return 0


if __name__ == "__main__":
    sys.exit(main())
