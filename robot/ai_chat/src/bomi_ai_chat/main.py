"""ai_chat CLI 진입점."""

import argparse
import logging
from collections.abc import Sequence
from logging.handlers import RotatingFileHandler

from bomi_ai_chat import policy
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
        "-v", "--verbose",
        action="store_true",
        help=(
            "DEBUG 까지 화면에 찍습니다. 실기 점검에서 판정 이유를 볼 때 씁니다 "
            "(S15P11E102-233). 로그 파일에는 -v 없이도 항상 남습니다."
        ),
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


def _setup_logging(settings: Settings, *, verbose: bool) -> None:
    """화면과 파일 두 곳에 로그를 남긴다.

    ★ 왜 이 함수가 생겼나 (S15P11E102-233)
        여기에 있던 basicConfig 가 주석 처리되어 있었다. 그래서 로봇을 켜면 핸들러가
        하나도 없고, INFO 는 통째로 사라지고 WARNING 만 형식 없이 stderr 로 나갔다.

        사라진 것들: "turn latency 1.83s", "scheduler built", "occupancy UNKNOWN ->
        HOME", "degrading to level 1". 실기 점검에서 봐야 할 것이 정확히 그것들이다.
        무엇이 왜 일어났는지 볼 수 없으면, 마이크 앞에서 관찰한 것을 코드의 어느
        판단과 연결할 방법이 없다.

    왜 파일에도 남기는가
        실기 점검의 산출물은 기록이다. 스크롤로 흘러간 화면은 다음 날 없다. 파일이
        있어야 "아까 그 턴이 왜 그랬지"를 나중에 grep 할 수 있고, 그것이 212 회귀
        세트의 재료가 된다.

    왜 파일은 항상 DEBUG 인가
        되돌릴 수 없는 것은 '남기지 않은 로그'다. 화면은 시끄러우면 안 되지만 파일은
        시끄러워도 된다. 문제가 생긴 뒤에 -v 를 켜고 재현하는 것은, 재현되지 않는
        문제 앞에서 아무 의미가 없다.

    어디에 쓰는가
        {LOCALSTORE_DIR}/logs/ai_chat.log — 운영 상태와 같은 디렉터리다. SD카드를
        옮기거나 백업할 때 대화 기록과 로그가 함께 간다.
    """
    from bomi_ai_chat.localstore.db import localstore_dir

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                                           datefmt="%H:%M:%S"))
    root.addHandler(console)

    try:
        log_dir = localstore_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        # 회전시킨다. 실기 점검은 몇 시간씩 돌고 DEBUG 는 빠르게 커진다.
        file_handler = RotatingFileHandler(
            log_dir / "ai_chat.log", maxBytes=20 * 1024 * 1024, backupCount=5,
            encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        root.addHandler(file_handler)
        root.info("logging to %s", log_dir / "ai_chat.log")
    except OSError:
        # 파일을 못 열어도 대화는 떠야 한다. 화면 로그는 이미 붙어 있다.
        root.exception("could not open the log file; console logging only")

    # 라이브러리 로그가 우리 로그를 덮지 않게 한다. httpx 는 요청마다 INFO 한 줄을
    # 남기는데, 실기에서는 그것이 화면의 대부분을 차지한다.
    for noisy in ("httpx", "httpcore", "urllib3", "paho", "apscheduler.executors.default"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


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

    _setup_logging(settings, verbose=args.verbose)

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

    def _weather_intent(text: str) -> bool:
        # 그래프 경로와 같은 값싼 "주제 + 조회 의도" 규칙을 공유한다.
        from bomi_ai_chat.llm.router import is_weather_query

        return is_weather_query(text)

    pipeline._detect_weather = _weather_intent

    logging.getLogger("bomi_ai_chat.main").info("의도 판정 규칙 준비...")
    _weather_intent("워밍업")

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

    # 배포 전환 중 기존 호출 순서를 유지하며 공용 결정 규칙의 import만 확인한다.
    # 이 훅은 모델을 로드하거나 네트워크를 사용하지 않는다.
    bootstrap.warm_up_intent_router()

    # 마이크 빔을 로봇 정면으로 고정한다 (S15P11E102-333).
    #
    # 이 배선도 레거시 경로(위 main())에만 있었다. 그래프 경로에서는 reSpeaker 의
    # 빔이 자동 추적으로 남아, 로봇 자신의 스피커나 TV 쪽으로 귀가 끌려갈 수 있다.
    # BEAM_FIX_ENABLED 가 꺼져 있거나 xvf_host 가 없는 환경(노트북)에서는
    # apply_fixed_beam 이 스스로 건너뛰므로 여기서 조건을 걸지 않는다.
    from bomi_ai_chat.audio_io.beam_control import BeamController

    beam = BeamController()
    beam.apply_fixed_beam()

    # 웨이크워드('보미야')를 그래프 경로에도 붙인다 -> 웨이크워드 + 기억이 함께 동작.
    # --once(한 턴 점검)에서는 상시 청취가 무의미하므로 붙이지 않는다(레거시 --once 와 동일).
    wake = None if once else _build_wakeword(settings)

    try:
        turns = bootstrap.run_conversation_loop(
            runtime, audio_in, settings,
            max_turns=1 if once else None,
            wake=wake, audio_out=audio_out)
    finally:
        # 빔 고정을 풀어 다음 실행(캘리브레이션 포함)이 깨끗한 상태에서 시작하게 한다.
        # 해제 실패가 종료 절차(runtime.shutdown)를 삼키면 안 되므로 예외는 여기서 그친다.
        try:
            beam.reset()
        except Exception:  # noqa: BLE001 - 장치 정리 실패가 종료를 막으면 안 된다
            logger.warning("could not reset the mic beam; it stays fixed", exc_info=True)
        # --once 일 때만 재생이 끝나기를 기다린다 (S15P11E102-233).
        #
        # ★ 재생은 daemon 스레드다. --once 는 한 턴 뒤 바로 끝나므로, 기다리지 않으면
        #   프로세스가 죽으면서 스레드도 죽고 **한 마디도 들리지 않는다.** 그래프는
        #   정상으로 돌고 로그도 정상인데 스피커만 조용해서, 원인을 오디오 장치나
        #   TTS 키에서 찾게 된다.
        #
        # 상시 실행(Ctrl+C)에서는 기다리지 않는다. 끄려는 사람을 문장이 끝날 때까지
        # 붙잡아 두는 것은 다른 종류의 잘못이다.
        runtime.shutdown(wait_for_speech_sec=policy.SPEECH_DRAIN_SEC if once else 0.0)

    return 0 if turns else 1


if __name__ == "__main__":
    raise SystemExit(main())
