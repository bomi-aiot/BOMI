"""ai_chat CLI 진입점."""

import argparse
import logging
from collections.abc import Sequence

from bomi_ai_chat.audio_io.base import AudioInput, AudioOutput
from bomi_ai_chat.config import ConfigurationError, Settings, get_settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="BOMI AI Chat 음성 대화 모듈",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="한 번만 대화한 뒤 종료합니다. 기본값은 Ctrl+C까지 반복입니다.",
    )
    return parser


def _build_audio_adapters(
    settings: Settings,
) -> tuple[AudioInput, AudioOutput]:
    """설정한 실행 환경에 맞는 오디오 입력·출력을 만든다."""

    if settings.audio_mode == "robot":
        from bomi_ai_chat.audio_io.robot import (
            RobotAudioInput,
            RobotAudioOutput,
        )

        return RobotAudioInput(settings), RobotAudioOutput(settings)

    from bomi_ai_chat.audio_io.laptop import (
        LaptopMicInput,
        LaptopSpeakerOutput,
    )

    return LaptopMicInput(settings), LaptopSpeakerOutput(settings)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        settings = get_settings()
        settings.validate_conversation()
    except ConfigurationError as exc:
        raise SystemExit(f"설정 오류: {exc}") from None

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # 임베딩 모델 등 무거운 런타임 의존성은 설정 검증 이후 불러온다.
    from bomi_ai_chat.pipeline import ConversationPipeline

    audio_in, audio_out = _build_audio_adapters(settings)
    pipeline = ConversationPipeline(
        audio_in=audio_in,
        audio_out=audio_out,
        settings=settings,
    )

    # 실제 실행에서만 빔 제어와 의미 기반 날씨 판정을 붙인다.
    # (단위 테스트의 StubPipeline 생성자 계약을 깨지 않도록 속성으로 주입한다.)
    from bomi_ai_chat.audio_io.beam_control import BeamController

    pipeline.beam = BeamController()

    def _semantic_weather(text: str) -> bool:
        # 무거운 임베딩 라우터는 실제 판정 시점에만 불러온다.
        from bomi_ai_chat.llm.router import is_weather_query

        return is_weather_query(text)

    pipeline._detect_weather = _semantic_weather

    if args.once:
        result = pipeline.run_once()
        return 0 if result.succeeded else 1

    pipeline.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
