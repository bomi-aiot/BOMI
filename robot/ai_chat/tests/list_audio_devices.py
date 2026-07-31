# robot/ai_chat/tests/list_audio_devices.py
"""컴퓨터에 연결된 오디오 장치(입력/출력) 목록을 보여주는 스크립트.

USB 스피커나 마이크가 sounddevice에 어떤 '이름'과 '번호(인덱스)'로 잡히는지
확인할 때 쓴다. 출력할 스피커를 코드에서 골라 쓰려면 그 이름을 알아야 한다.

실행:  (ai_chat 폴더에서)  python tests/list_audio_devices.py
"""

import sounddevice as sd


def main():
    print("=== 전체 오디오 장치 목록 ===")
    print("(in=입력채널수, out=출력채널수. out>0 이면 스피커로 쓸 수 있는 장치)\n")

    for idx, dev in enumerate(sd.query_devices()):
        hostapi = sd.query_hostapis(dev["hostapi"])["name"]
        print(
            f"[{idx:2}] {dev['name']}\n"
            f"      호스트API: {hostapi} | "
            f"in: {dev['max_input_channels']}, out: {dev['max_output_channels']} | "
            f"기본 샘플레이트: {int(dev['default_samplerate'])}Hz"
        )

    print("\n=== 현재 기본 장치 ===")
    default_in, default_out = sd.default.device
    print(f"기본 입력 : {default_in}")
    print(f"기본 출력 : {default_out}")


if __name__ == "__main__":
    main()
