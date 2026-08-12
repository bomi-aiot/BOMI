"""스피커와 TTS 가 실제로 쓸 수 있는 상태인지 확인한다.

왜 필요한가
    2026-08-09 실기에서 로봇이 한 마디도 하지 않았다. 스피커를 의심했지만
    장치는 정상이었고, Typecast TTS 가 HTTP 403 을 돌려주고 있었다. 시나리오는
    끝까지 도는데 소리만 없으니, 로그를 뒤지기 전에는 원인을 알 수 없었다.

    여기서 두 가지를 먼저 확인한다.
        1. 이름으로 지정한 출력 장치가 실제로 잡히는가
        2. TTS 가 실제로 음성 바이트를 돌려주는가 (인증·크레딧 포함)

    2번은 실제 요청을 한 번 보낸다. 짧은 문장이라 비용은 미미하고, 이것 없이는
    "키가 살아 있는가"를 알 방법이 없다.

사용법
    python3 check_speech.py            확인만 하고 종료 코드로 알린다
    종료 코드 0 정상 / 1 실패(사유는 stderr)
"""

from __future__ import annotations

import sys

PROBE_TEXT = "준비 확인"


def fail(message: str) -> int:
    print(f"    ❌ {message}", file=sys.stderr)
    return 1


def _output_device_list() -> str:
    """쓸 수 있는 출력 장치를 보기 좋게 늘어놓는다. 실패해도 빈 문자열."""
    try:
        import sounddevice as sd

        lines = [
            f"         [{idx}] {dev['name']}"
            for idx, dev in enumerate(sd.query_devices())
            if dev["max_output_channels"] > 0
        ]
    except Exception:  # noqa: BLE001 - 목록은 부가 정보다
        return ""
    if not lines:
        return "       출력 장치가 하나도 없습니다 (PulseAudio 미기동일 수 있습니다)."
    return "       쓸 수 있는 출력 장치:\n" + "\n".join(lines)


def main() -> int:
    try:
        from bomi_ai_chat.config import get_settings
    except Exception as error:  # noqa: BLE001 - 원인을 그대로 보여준다
        return fail(f"bomi_ai_chat 를 불러오지 못했습니다: {error}")

    settings = get_settings()

    # 1. 출력 장치
    device = getattr(settings, "audio_output_device", None)
    try:
        from bomi_ai_chat.audio_io.sounddevice_backend import _resolve_output_device

        resolved = _resolve_output_device(device)
    except Exception as error:  # noqa: BLE001
        # 못 찾았을 때 "그럼 뭐가 있는지"를 같이 보여준다. 이것 없이는
        # AUDIO_OUTPUT_DEVICE 에 무엇을 적어야 할지 알 수 없다.
        return fail(
            f"스피커를 찾지 못했습니다 (AUDIO_OUTPUT_DEVICE={device!r}): {error}\n"
            f"{_output_device_list()}"
        )
    print(f"    스피커 OK — AUDIO_OUTPUT_DEVICE={device!r} -> {resolved!r}")

    # 2. TTS. 인증·크레딧 문제는 여기서만 드러난다.
    try:
        from bomi_ai_chat.tts.client import TTSClient

        audio = TTSClient(settings=settings).synthesize(PROBE_TEXT)
    except Exception as error:  # noqa: BLE001
        return fail(
            f"TTS 실패: {error}\n"
            "       403 이면 Typecast 키 만료·크레딧 소진·voice 권한을 확인하세요 "
            "(.env 의 TYPECAST_API_KEY / TYPECAST_VOICE_ID)."
        )
    if not audio:
        return fail("TTS 가 빈 응답을 돌려줬습니다.")
    print(f"    TTS OK — {len(audio)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
