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

    # logging.basicConfig(
    #     level=logging.INFO,
    #     format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    # )

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

    # 웨이크워드('보미야') 감지기. 설정에서 켜져 있을 때만 붙인다. 붙으면 매 턴
    # 대화 시작 전에 "보미야"를 기다린다(pipeline.run 참고). 노트북 개발 등에서
    # WAKEWORD_ENABLED=0 이면 붙이지 않아 상시 청취 없이 곧바로 대화한다.
    if settings.wakeword_enabled:
        from bomi_ai_chat import policy
        from bomi_ai_chat.audio_io.wakeword import WakeWordDetector

        pipeline.wake = WakeWordDetector(
            model_path=settings.wakeword_model_path,
            # 마이크 장치/채널은 캡처와 동일하게 맞춘다(같은 ReSpeaker 왼쪽 채널).
            device=settings.audio_input_device,
            channels=settings.audio_channels,
            target_sample_rate=settings.audio_sample_rate,
            threshold=policy.WAKEWORD_THRESHOLD,
            window=policy.WAKEWORD_WINDOW,
            min_hits=policy.WAKEWORD_MIN_HITS,
            frame_samples=policy.WAKEWORD_FRAME_SAMPLES,
        )
        # 첫 감지가 느려지지 않게 대기 루프 전에 모델을 미리 로드한다(warm-up).
        logging.getLogger("bomi_ai_chat.main").info("웨이크워드 모델 로딩(warm-up)...")
        pipeline.wake.warm_up()

    def _semantic_weather(text: str) -> bool:
        # 무거운 임베딩 라우터는 실제 판정 시점에만 불러온다.
        from bomi_ai_chat.llm.router import is_weather_query

        return is_weather_query(text)

    pipeline._detect_weather = _semantic_weather

    # 임베딩 의도 판정 모델을 '수음 시작 전에' 미리 로드(warm-up)한다.
    # 이렇게 안 하면 첫 대화 도중(수음 뒤) 모델이 로드되면서 응답이 크게
    # 지연된다. 아래 호출이 router 모듈을 import시켜 모델을 미리 올려둔다.
    logging.getLogger("bomi_ai_chat.main").info("의도 판정 모델 로딩(warm-up)...")
    _semantic_weather("워밍업")

    if args.once:
        result = pipeline.run_once()
        return 0 if result.succeeded else 1

    pipeline.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())