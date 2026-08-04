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
    parser.add_argument(
        "--legacy",
        action="store_true",
        help=(
            "대화 런타임(그래프)을 건너뛰고 200번 이전의 파이프라인으로 돕니다. "
            "게이트·침묵 사다리·트리아지·현관이 전부 꺼집니다. "
            "USE_GRAPH_RUNTIME=false 와 같습니다."
        ),
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


def _build_wakeword(settings: Settings):
    """설정이 켜져 있으면 WakeWordDetector 를 만들어 warm-up 까지 하고 돌려준다.

    레거시 경로와 그래프 경로가 같은 방식으로 웨이크워드를 붙이도록 공용화한다.
    WAKEWORD_ENABLED=false 면 None 을 돌려준다(웨이크워드 없이 동작).

    warm-up 을 여기서 하는 이유
        첫 "보미야" 감지가 느려지지 않게 모델을 미리 로드한다(의도 판정 warm-up 과
        같은 이유).
    """
    if not settings.wakeword_enabled:
        return None

    from bomi_ai_chat import policy
    from bomi_ai_chat.audio_io.wakeword import WakeWordDetector

    wake = WakeWordDetector(
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
    logging.getLogger("bomi_ai_chat.main").info("웨이크워드 모델 로딩(warm-up)...")
    wake.warm_up()
    return wake


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

    audio_in, audio_out = _build_audio_adapters(settings)

    # 그래프 경로가 기본이다 (S15P11E102-232).
    #
    # 200~211 에서 만든 게이트·침묵 사다리·트리아지·현관·온보딩·보호자 알림은 전부
    # 이 경로에만 있다. --legacy 로 옛 경로를 고를 수 있게 남겨 둔 이유는, 실기에서
    # 문제가 나면 즉시 되돌려야 하는데 그 되돌리기가 코드 수정이면 현장에서 못 하기
    # 때문이다 (S15P11E102-233).
    if settings.use_graph_runtime and not args.legacy:
        return _run_graph_runtime(settings, audio_in, audio_out, once=args.once)

    logging.getLogger("bomi_ai_chat.main").warning(
        "running the legacy pipeline: no gate, no silence ladder, no triage, no door. "
        "The robot will only answer when spoken to.")

    # 임베딩 모델 등 무거운 런타임 의존성은 설정 검증 이후 불러온다.
    from bomi_ai_chat.pipeline import ConversationPipeline

    pipeline = ConversationPipeline(
        audio_in=audio_in,
        audio_out=audio_out,
        settings=settings,
    )

    # 실제 실행에서만 빔 제어와 의미 기반 날씨 판정을 붙인다.
    # (단위 테스트의 StubPipeline 생성자 계약을 깨지 않도록 속성으로 주입한다.)
    from bomi_ai_chat.audio_io.beam_control import BeamController

    pipeline.beam = BeamController()

    # 웨이크워드('보미야') 감지기. 설정에서 켜져 있을 때만 붙는다(없으면 None).
    # 붙으면 매 대화 시작 전에 "보미야"를 기다린다(pipeline.run 참고).
    pipeline.wake = _build_wakeword(settings)

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


def _run_graph_runtime(settings: Settings, audio_in, audio_out, *, once: bool) -> int:
    """대화 런타임을 띄우고 입력 루프를 돈다.

    무엇을 하는가
        그래프·스케줄러·현관 구독·재생기를 연결하고(bootstrap), 캡처 -> STT -> 그래프
        루프를 돈다. 종료 시 배경 스레드를 정리한다.

    왜 --once 에서 배경 작업을 띄우지 않는가
        한 턴만 확인하려는 실행에 스케줄러와 MQTT 구독이 뜨면, 정리되기 전에 틱이
        한 번 돌아 제안이 큐에 남는다. 다음 실행이 그것을 물려받아 "왜 갑자기
        말하지?"가 된다.
    """
    from bomi_ai_chat import bootstrap

    logger = logging.getLogger("bomi_ai_chat.main")
    runtime = bootstrap.build_runtime(
        settings, audio_out=audio_out, start_background=not once)
    logger.info("conversation runtime ready (senior=%s)", runtime.senior_id)

    # 웨이크워드('보미야')를 그래프 경로에도 붙인다 -> 웨이크워드 + 기억이 함께 동작.
    # --once(한 턴 점검)에서는 상시 청취가 무의미하므로 붙이지 않는다(레거시 --once 와 동일).
    wake = None if once else _build_wakeword(settings)

    try:
        turns = bootstrap.run_conversation_loop(
            runtime, audio_in, settings,
            max_turns=1 if once else None,
            wake=wake, audio_out=audio_out)
    finally:
        runtime.shutdown()

    return 0 if turns else 1


if __name__ == "__main__":
    raise SystemExit(main())