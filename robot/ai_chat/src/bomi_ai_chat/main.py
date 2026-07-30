"""ai_chat CLI 진입점."""

import argparse
import logging
from collections.abc import Sequence

from bomi_ai_chat.config import ConfigurationError, get_settings


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
    if args.once:
        result = pipeline.run_once()
        return 0 if result.succeeded else 1

    pipeline.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
