"""ai_chat 진입점 (노트북 모드)."""

from bomi_ai_chat.config import ConfigurationError, get_settings


def main():
    try:
        settings = get_settings()
        settings.validate_conversation()
    except ConfigurationError as exc:
        raise SystemExit(f"설정 오류: {exc}") from None

    # 임베딩 모델 등 무거운 런타임 의존성은 설정 검증 이후 불러온다.
    from bomi_ai_chat.audio_io.laptop import (
        LaptopMicInput,
        LaptopSpeakerOutput,
    )
    from bomi_ai_chat.pipeline import ConversationPipeline

    pipeline = ConversationPipeline(
        audio_in=LaptopMicInput(),
        audio_out=LaptopSpeakerOutput(),
        settings=settings,
    )
    pipeline.run_once()


if __name__ == "__main__":
    main()
