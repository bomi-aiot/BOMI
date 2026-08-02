"""런타임 배선 — 만들어 둔 것들을 실제로 연결해 돌린다 (S15P11E102-232).

★ 왜 이 파일이 필요했는가

    200~211 에서 그래프·게이트·침묵 사다리·현관·트리아지·온보딩·보호자 알림을
    만들었지만, **어느 것도 실행 경로에 연결되어 있지 않았다.** main.py 는 그 이전부터
    있던 ConversationPipeline 을 띄웠고, 그것은 STT -> LLM -> TTS 를 직접 부른다.

    테스트 420건은 전부 모듈을 직접 불러서 검증한 것이다. 로봇을 켜면 게이트도
    사다리도 트리아지도 돌지 않았다. 각 티켓 MR 에 "부트스트랩이 아직 호출하지
    않습니다"라고 조각조각 적혀 있던 것들이, 합치면 이 상태였다.

이 파일이 하는 일
    1. 그래프를 컴파일하고 checkpointer 를 붙인다
    2. 재생기(TTS + 오디오 출력 + 에코 가드)를 주입한다
    3. 백엔드 클라이언트들을 주입한다
    4. 스케줄러를 시작한다 (침묵 사다리·현관 감시·일정·계약·outbox)
    5. 현관 MQTT 구독을 시작한다
    6. runtime_state 에서 재부팅 전 상태를 복원한다
    7. 입력 루프를 돈다: 캡처 -> STT -> 그래프

이 파일이 하지 않는 일
    새 기능. 전부 이미 있는 것을 잇는다. 여기에 판단 로직이 생기기 시작하면,
    "로봇이 왜 그렇게 행동했는가"의 답이 그래프 밖으로 새어 나간다.

참고
    CLAUDE.md §6 (아키텍처), §15 (시계 주입), §22 (개발 순서)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bomi_ai_chat.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class Runtime:
    """돌아가고 있는 것들. 종료할 때 이 핸들로 정리한다."""

    app: Any
    senior_id: str
    scheduler: Any = None
    door_subscriber: Any = None

    def shutdown(self) -> None:
        """백그라운드 스레드를 정리한다. 실패해도 종료를 막지 않는다.

        정리하지 않으면 재시작할 때마다 스케줄러 스레드가 쌓이고, 침묵 틱이 두 번씩
        돌아 프로브가 겹쳐 나간다.
        """
        for name, closer in (
            ("door subscriber", getattr(self.door_subscriber, "stop", None)),
            ("scheduler", getattr(self.scheduler, "shutdown", None)),
        ):
            if closer is None:
                continue
            try:
                closer()
            except Exception:  # noqa: BLE001 - 종료 경로에서 예외를 올리지 않는다
                logger.warning("could not stop the %s cleanly", name, exc_info=True)


def build_runtime(
    settings: Settings | None = None,
    *,
    audio_out=None,
    start_background: bool = True,
) -> Runtime:
    """그래프를 만들고 주변을 전부 연결한다. 입력 루프는 돌지 않는다.

    인자
        audio_out: 오디오 출력 어댑터. None 이면 재생기를 붙이지 않는다 — 그러면
            emit 이 조용히 넘어가므로, 소리 없이 판단 경로만 확인할 때 쓴다.
        start_background: False 면 스케줄러와 현관 구독을 시작하지 않는다.
            한 턴만 돌려보는 --once 실행에서 배경 작업이 뜨는 것은 낭비다.

    반환값
        Runtime. 호출부가 shutdown() 을 책임진다.
    """
    settings = settings or get_settings()
    senior_id = _resolve_senior_id(settings)

    app = _compile_graph()
    _wire_player(settings, audio_out)
    _wire_backend_clients()
    _restore_runtime_state(app, senior_id)

    runtime = Runtime(app=app, senior_id=senior_id)
    if start_background:
        runtime.scheduler = _start_scheduler(senior_id, app)
        runtime.door_subscriber = _start_door_subscriber(senior_id, app, settings)
    return runtime


def _resolve_senior_id(settings: Settings) -> str:
    """이 로봇이 돌보는 어르신.

    ★ checkpointer 의 thread_id 이자 모든 저장소의 키다. 잘못 넣으면 두 어르신이
    침묵 사다리를 공유하게 되고, 안전 시스템에서 그것은 한 사람의 발화가 다른
    사람의 에스컬레이션을 억제한다는 뜻이다 (graph/build.py).

    설정이 없으면 요란하게 실패한다. 임의의 기본값을 쓰면 그 값으로 기록이 쌓이고,
    나중에 진짜 id 로 바꾸는 순간 그동안의 상태가 통째로 사라진다.
    """
    senior_id = getattr(settings, "senior_id", None)
    if not senior_id:
        raise RuntimeError(
            "SENIOR_ID is not configured; the robot does not know whose state it is "
            "keeping. Set it in .env before starting.")
    return senior_id


def _compile_graph():
    from bomi_ai_chat.graph.build import build_graph

    logger.info("compiling the conversation graph")
    return build_graph()


def _wire_player(settings: Settings, audio_out) -> None:
    """emit 이 쓸 재생기를 붙인다. TTS 와 오디오 출력은 기존 것을 그대로 쓴다.

    에코 가드를 함께 넣는 이유
        스피커와 마이크가 한 몸통에 있어서 로봇의 목소리가 마이크로 되돌아온다.
        가드가 없으면 로봇이 자기 말에 자기가 멈추고, 그러면 이후 모든 게이트 버그
        리포트가 실제로는 에코다 (CLAUDE.md §13).
    """
    from bomi_ai_chat.audio.echo_guard import EchoGuard
    from bomi_ai_chat.audio.playback import SentencePlayer
    from bomi_ai_chat.graph import output
    from bomi_ai_chat.tts.client import TTSClient

    if audio_out is None:
        logger.warning("no audio output wired; the robot will decide what to say but "
                       "will not say it")
        return

    tts = TTSClient(settings)
    output.set_player(SentencePlayer(
        synthesize=tts.synthesize,
        play=audio_out.play,
        echo_guard=EchoGuard(),
    ))


def _wire_backend_clients() -> None:
    """백엔드 클라이언트들을 주입한다.

    지연 생성이 기본값이므로 대부분은 저절로 붙는다. 여기서 명시적으로 붙이는 것은
    **기본값이 대역인 것들**이다 — 그냥 두면 조용히 로그로만 나간다.
    """
    from bomi_ai_chat.backend_client import BackendConversationClient
    from bomi_ai_chat.graph import build as graph_build

    graph_build.set_conversation_client(BackendConversationClient())


def _restore_runtime_state(app, senior_id: str) -> None:
    """재부팅 전 상태를 그래프 checkpoint 로 되돌린다.

    ★ 왜 필요한가
        침묵 사다리가 2칸까지 올라간 상태에서 로봇이 재부팅되면, 복원이 없으면
        사다리가 0 으로 돌아간다. 응답 없는 어르신에 대한 시계가 처음부터 다시
        흐르고, 에스컬레이션이 그만큼 늦어진다. 안전 기기에서 그건 조용한 실패다
        (localstore/runtime.py).

    틱들은 runtime_state 를 직접 읽으므로 이 복원이 없어도 동작한다. 복원이 채우는
    것은 '그래프 쪽 사본'이다 — 두 저장소의 수명이 다르다는 그 이야기다.
    """
    from bomi_ai_chat.graph.build import thread
    from bomi_ai_chat.localstore import runtime as runtime_store

    stored = runtime_store.load(senior_id)
    try:
        # as_node 를 종단 노드로 준다.
        #
        # ★ 그냥 update_state 를 부르면 LangGraph 가 이것을 '새 입력'으로 보고
        #   그래프를 한 번 돌린다. 기동하자마자 trigger_type 없는 턴이 실행되고,
        #   route_ingress 가 KeyError 로 죽는다. 우리가 원하는 것은 실행이 아니라
        #   상태를 앉히는 것뿐이다.
        #
        #   emit 은 END 로만 이어지므로, 그 노드가 낸 결과로 기록하면 뒤따라 도는
        #   것이 없다.
        app.update_state(
            thread(senior_id), {"senior_id": senior_id, **stored}, as_node="emit")
    except Exception:  # noqa: BLE001 - 복원 실패가 기동을 막으면 안 된다
        logger.warning("could not restore runtime state; starting from a clean slate. "
                       "The silence ladder will begin at rung 0.", exc_info=True)
        return

    if stored.get("silence_level"):
        logger.warning("restored the silence ladder at rung %s — the senior had not "
                       "responded before the restart", stored["silence_level"])


def _start_scheduler(senior_id: str, app):
    """주기 작업을 시작한다.

    이게 없으면 침묵 사다리·현관 감시·일정 권유·계약 대화·outbox flush 가 전부
    돌지 않는다. 즉 로봇이 먼저 말하는 일이 영원히 없고, 큐에 든 T1 이 나가지 않는다.
    """
    from bomi_ai_chat.jobs.scheduler import build_scheduler

    try:
        scheduler = build_scheduler(senior_id, app)
        scheduler.start()
    except Exception:  # noqa: BLE001 - 스케줄러가 없다고 대화까지 막지 않는다
        logger.exception("could not start the scheduler; the robot will only respond "
                         "when spoken to. No silence ladder, no reminders, no outbox flush.")
        return None

    logger.info("scheduler started")
    return scheduler


def _start_door_subscriber(senior_id: str, app, settings: Settings):
    """현관 이벤트 구독을 시작한다. 비활성이면 경고만 남기고 넘어간다."""
    from bomi_ai_chat.door.mqtt import build_door_subscriber

    try:
        subscriber = build_door_subscriber(senior_id, settings=settings, app=app)
        if subscriber is None:
            return None
        subscriber.start()
    except Exception:  # noqa: BLE001 - 브로커가 없다고 대화까지 막지 않는다
        logger.exception("could not start the door subscriber; occupancy will stay "
                         "UNKNOWN and the door watch cannot detect a missing return")
        return None

    logger.info("door subscriber started")
    return subscriber


# ─────────────────────────────────────────────────────────────────────────────
# 입력 루프
# ─────────────────────────────────────────────────────────────────────────────


def run_conversation_loop(
    runtime: Runtime,
    audio_in,
    settings: Settings | None = None,
    *,
    max_turns: int | None = None,
) -> int:
    """캡처 -> STT -> 그래프 를 반복한다.

    ★ 옛 ConversationPipeline 과 무엇이 다른가
        저쪽은 LLM 을 직접 부르고 응답을 바로 재생한다. 여기는 그래프에 태운다 —
        그래서 트리아지가 생성보다 위에 있고, 능동 발화가 게이트를 거치고, 모든
        출력이 정제기를 통과한다.

    누가 호출하는가
        main.py. 테스트는 max_turns 로 횟수를 묶는다.

    반환값
        처리한 턴 수.

    주의사항
        - 한 턴의 실패가 루프를 죽이지 않는다. run_user_turn 이 이미 예외를 삼키지만,
          캡처와 STT 는 그 밖이라 여기서 감싼다. 로봇이 멈추면 어르신은 고장 난
          기계 앞에 남는다.
        - 재생 완료를 기다리지 않는다. 기다리면 barge-in 이 원리적으로 불가능해진다
          (CLAUDE.md §13).
    """
    from bomi_ai_chat.graph.turn import run_user_turn
    from bomi_ai_chat.stt.client import STTClient

    settings = settings or get_settings()
    stt = STTClient(settings)
    turns = 0
    logger.info("conversation loop started (graph path)")

    while max_turns is None or turns < max_turns:
        try:
            text, duration = _listen(audio_in, stt)
        except KeyboardInterrupt:
            logger.info("conversation loop stopped by user after %d turns", turns)
            break
        except Exception:  # noqa: BLE001 - 한 번의 수음 실패가 루프를 죽이면 안 된다
            logger.exception("could not capture or transcribe; waiting for the next turn")
            continue

        if not text:
            # 조용한 구간이거나 인식되지 않았다. 되묻지 않는다 — 아무 말도 안 한
            # 사람에게 "네?"라고 하는 로봇은 성가시다.
            continue

        run_user_turn(runtime.app, runtime.senior_id, text, duration_sec=duration)
        turns += 1

    return turns


def _listen(audio_in, stt) -> tuple[str, float]:
    """한 번 수음해서 텍스트와 길이를 돌려준다.

    길이를 함께 돌려주는 이유
        맞장구("응")와 진짜 끼어들기를 구분하는 데 필요하다. 텍스트만으로는
        부족하다 — "네"는 질문에 대한 진짜 대답일 수도 있다 (CLAUDE.md §13).
    """
    from bomi_ai_chat.clock import clock

    started = clock.now()
    audio = audio_in.capture()
    if not isinstance(audio, bytes) or not audio:
        return "", 0.0

    text = (stt.transcribe(audio) or "").strip()
    return text, max(0.0, clock.now() - started)
