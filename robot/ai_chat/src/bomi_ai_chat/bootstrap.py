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
import os
import queue
import time
from dataclasses import dataclass, field
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
    # 재생기(재생 상태를 표시)와 대화 루프(재생 끝날 때까지 대기)가 공유하는 에코 가드.
    # 응답 재생 중에 다음 리슨을 열지 않기 위한 근거(is_playing)를 여기서 읽는다.
    echo_guard: Any = None
    # 백엔드 START_CONVERSATION 구독자(ai_commands.AiCommandSubscriber). 현관
    # 인사·복약 알림·온습도 안부, 세 시나리오의 대화가 이 경로로 들어온다.
    ai_command_subscriber: Any = None
    # 위 구독자(paho 콜백 스레드)와 메인 루프(마이크를 쥔 유일한 스레드) 사이의
    # 손 넘김 큐. 큐가 비어 있지 않으면 메인 루프가 웨이크워드 대기 대신 이
    # 대화를 먼저 진행한다 — 이유는 run_conversation_loop 의 주석 참고.
    backend_conversation_queue: queue.Queue | None = field(default=None)
    # 이동 중 침묵(§3a)이 켜져 있을 때만 만들어지는 도착 감시자
    # (navigation_watch.NavigationArrivalWatcher). None 이면 이 기능이
    # 꺼져 있다는 뜻 — 웨이크 흐름은 기존 WAKE_ACK_MESSAGE 로 그대로 동작한다.
    navigation_watcher: Any = None
    # 보미야 호출 회전 탐색 신호 발신자(search_signal.SearchSignalSender).
    # 웨이크워드 직후 소리 방향을, 대화 중 정지 요청과 대화 종료 시 정지를
    # 로봇 내부(ROS 2 wake_search 노드)로 UDP 발신한다. None 이면 이 기능이
    # 꺼져 있다는 뜻 — 대화는 그대로 동작하고 로봇만 돌지 않는다.
    search_signal: Any = None

    def shutdown(self, *, wait_for_speech_sec: float = 0.0) -> None:
        """백그라운드 스레드를 정리한다. 실패해도 종료를 막지 않는다.

        정리하지 않으면 재시작할 때마다 스케줄러 스레드가 쌓이고, 침묵 틱이 두 번씩
        돌아 프로브가 겹쳐 나간다.

        인자
            wait_for_speech_sec: 종료 전에 재생이 끝나기를 이만큼 기다린다.

        ★ 왜 기다리는 선택지가 필요한가 (S15P11E102-233)
            재생은 daemon 스레드다. 그래서 프로세스가 끝나면 말하던 중이라도 그대로
            죽는다. 평상시에는 그것이 옳다 — Ctrl+C 를 눌렀는데 로봇이 문장을 다
            마칠 때까지 안 꺼지면 곤란하다.

            그런데 --once 는 한 턴만 돌고 바로 끝난다. 그 결과 **한 마디도 들리지
            않는다.** 그래프는 정상으로 돌고 로그도 정상인데 스피커만 조용하다.
            실기 점검 0.6(에코 확인)이 --once 로 시작하는데, 소리가 안 나면 확인할
            대상 자체가 없다.

            기본값은 0 이다. 기다림은 --once 처럼 '끝을 보려는' 실행에서만 켠다.
        """
        if wait_for_speech_sec > 0:
            self._await_speech(wait_for_speech_sec)

        for name, closer in (
            ("door subscriber", getattr(self.door_subscriber, "stop", None)),
            ("ai command subscriber", getattr(self.ai_command_subscriber, "stop", None)),
            ("navigation arrival watcher", getattr(self.navigation_watcher, "stop", None)),
            ("search signal sender", getattr(self.search_signal, "close", None)),
            ("scheduler", getattr(self.scheduler, "shutdown", None)),
        ):
            if closer is None:
                continue
            try:
                closer()
            except Exception:  # noqa: BLE001 - 종료 경로에서 예외를 올리지 않는다
                logger.warning("could not stop the %s cleanly", name, exc_info=True)


    def _await_speech(self, timeout_sec: float) -> None:
        """재생 중인 발화가 끝나기를 기다린다.

        핸들이 진행 상황의 권위다(graph/output.TTS_HANDLES). 여기서는 '아직 말하고
        있는가'만 물어보고, 끝났거나 시간이 다 되면 넘어간다.
        """
        from bomi_ai_chat.graph.output import TTS_HANDLES

        handle = TTS_HANDLES.get(self.senior_id)
        if handle is None:
            return
        waiter = getattr(handle, "wait", None)
        if waiter is None:
            # 대역 핸들에는 wait 가 없을 수 있다. 없으면 기다리지 않는다 —
            # 여기서 sleep 으로 때우면 테스트가 그 시간만큼 느려진다.
            return
        logger.info("waiting up to %.1fs for speech to finish", timeout_sec)
        waiter(timeout_sec)


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

    # 에코 가드 하나를 만들어 재생기와 대화 루프가 '같은 인스턴스'를 공유하게 한다.
    # 재생기는 재생 시작/끝을 여기 표시하고, 대화 루프는 is_playing 을 읽어 재생이 끝날
    # 때까지 리슨을 미룬다(barge-in 없이 에코 겹침 방지).
    from bomi_ai_chat.audio.echo_guard import EchoGuard
    echo_guard = EchoGuard()

    app = _compile_graph()
    _wire_player(settings, audio_out, echo_guard)
    _wire_backend_clients()
    _restore_runtime_state(app, senior_id)

    # 백엔드 대화 명령(START_CONVERSATION)이 도착하면 이 큐를 거쳐 메인
    # 루프로 전달된다. maxsize 는 ai_commands.QUEUE_MAX_SIZE 와 맞춘다 —
    # 두 곳에 같은 숫자를 다른 이유로 들고 있지 않도록 여기서 그 상수를 쓴다.
    from bomi_ai_chat.ai_commands import QUEUE_MAX_SIZE
    backend_conversation_queue: queue.Queue = queue.Queue(maxsize=QUEUE_MAX_SIZE)

    runtime = Runtime(
        app=app, senior_id=senior_id, echo_guard=echo_guard,
        backend_conversation_queue=backend_conversation_queue,
    )
    if start_background:
        runtime.scheduler = _start_scheduler(senior_id, app)
        runtime.door_subscriber = _start_door_subscriber(senior_id, app, settings)
        runtime.ai_command_subscriber = _start_ai_command_subscriber(
            settings, backend_conversation_queue)
        runtime.navigation_watcher = _start_navigation_watcher(settings)
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


def _wire_player(settings: Settings, audio_out, echo_guard) -> None:
    """emit 이 쓸 재생기를 붙인다. TTS 와 오디오 출력은 기존 것을 그대로 쓴다.

    에코 가드를 밖에서 받는 이유
        재생기는 재생 시작/끝을 이 가드에 표시하고, 대화 루프는 같은 가드의 is_playing
        을 읽어 재생이 끝날 때까지 리슨을 미룬다. 그러려면 둘이 '같은 인스턴스'를 써야
        하므로, build_runtime 이 만들어 여기로 넘긴다(예전엔 여기서 새로 만들었다).
    """
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
        echo_guard=echo_guard,
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


def _start_ai_command_subscriber(settings: Settings, pending_queue: queue.Queue):
    """백엔드 대화 명령(START_CONVERSATION) 구독을 시작한다.

    door 구독과 달리 그래프 `app` 을 주입하지 않는다 — 대화 진행은 메인 루프가
    `pending_queue` 를 통해 직접 한다(bootstrap.py 모듈 docstring 의 스레드
    경계 설명 참고). 이 구독자는 수신·ACK·중복 제거만 한다.

    비활성이면 경고만 남기고 넘어간다 — 그러면 현관 인사·복약 알림·온습도
    안부, 세 시나리오의 대화가 전혀 시작되지 않는다.
    """
    from bomi_ai_chat.ai_commands import build_ai_command_subscriber

    try:
        subscriber = build_ai_command_subscriber(
            settings=settings, pending_queue=pending_queue)
        if subscriber is None:
            return None
        subscriber.start()
    except Exception:  # noqa: BLE001 - 브로커가 없다고 대화까지 막지 않는다
        logger.exception("could not start the ai command subscriber; homecoming/"
                         "medication/wellness conversations will never start")
        return None

    logger.info("ai command subscriber started")
    return subscriber


def _start_navigation_watcher(settings: Settings):
    """이동 중 침묵(§3a)의 도착 감시자를 시작한다.

    `settings.wake_movement_wait_enabled` 가 꺼져 있으면 조용히 None —
    이건 "고장"이 아니라 이 기능 자체가 옵트인이기 때문이다(경고 로그를
    남기지 않는다. build_navigation_arrival_watcher 안에서 이미 켜져
    있는데 다른 전제가 빠진 경우만 경고한다).
    """
    from bomi_ai_chat.navigation_watch import build_navigation_arrival_watcher

    try:
        watcher = build_navigation_arrival_watcher(settings)
        if watcher is None:
            return None
        watcher.start()
    except Exception:  # noqa: BLE001 - 브로커가 없다고 대화까지 막지 않는다
        logger.exception("could not start the navigation arrival watcher; "
                         "wake-triggered movement will always use the "
                         "movement-wait timeout")
        return None

    logger.info("navigation arrival watcher started")
    return watcher


# ─────────────────────────────────────────────────────────────────────────────
# 입력 루프
# ─────────────────────────────────────────────────────────────────────────────


def run_conversation_loop(
    runtime: Runtime,
    audio_in,
    settings: Settings | None = None,
    *,
    max_turns: int | None = None,
    wake=None,
    audio_out=None,
    event_publisher=None,
) -> int:
    """캡처 -> STT -> 그래프 를 반복한다. (웨이크워드가 있으면 대화 단위로 묶는다.)

    ★ 옛 ConversationPipeline 과 무엇이 다른가
        저쪽은 LLM 을 직접 부르고 응답을 바로 재생한다. 여기는 그래프에 태운다 —
        그래서 트리아지가 생성보다 위에 있고, 능동 발화가 게이트를 거치고, 모든
        출력이 정제기를 통과한다. 기억(context_read/memory_write)도 run_user_turn 안이다.

    웨이크워드 (wake 가 주어지면)
        매 발화가 아니라 '대화 단위'로 동작한다: "보미야"를 기다렸다가, 호출 응답
        (conversation_control.WAKE_ACK_MESSAGE, 현재 "네, 말씀하세요.")으로 먼저
        응답하고, 그 대화 안에서는 재호출 없이 여러 발화를 이어 처리한다. 15초
        무응답 또는 마무리 언급이면 대화를 끝내고 다시 "보미야"를 기다린다.
        wake 가 None 이면 예전처럼 매 발화를 그냥 처리한다(팀원 기본 동작).

        세션의 상태는 conversation_control.SessionState 로 명시화되어 있다 —
        IDLE(웨이크 대기) → LISTENING → PROCESSING → RESPONDING → (반복) → ENDING.
        전이표가 곧 세션 정책이고, 이 루프는 그 표를 구동만 한다.

    호출 응답은 왜 audio_out 으로 직접 재생하나
        그래프의 응답 출력(emit)은 barge-in 위해 논블로킹이다. 호출 응답을
        그걸로 내보내면 인사와 녹음이 겹친다. 그래서 audio_out.play 로 '블로킹' 재생해
        인사가 끝난 뒤에 듣기 시작한다.

    누가 호출하는가
        main.py. 테스트는 max_turns 로 횟수를 묶는다.

    주의사항
        - 한 턴의 실패가 루프를 죽이지 않는다. run_user_turn 이 이미 예외를 삼키지만,
          캡처와 STT 는 그 밖이라 여기서 감싼다.
        - 대화 턴 응답 재생은 기다리지 않는다(barge-in 유지). 다만 그로 인해 다음
          리슨이 로봇 목소리를 잡는 에코 겹침은 실기에서 EchoGuard 를 캡처에 연결해
          다룬다(현재는 미연결 — docs/hardware 확인 항목).
    """
    from bomi_ai_chat.graph.turn import run_user_turn
    from bomi_ai_chat.stt.client import STTClient

    settings = settings or get_settings()
    stt = STTClient(settings)

    # 웨이크워드 감지 MQTT 발행자 (S15P11E102-349). 백엔드의 보미야 호출
    # 시나리오(335)가 이 신호를 기다린다. MQTT 가 꺼져 있으면 None 이고,
    # None 이면 아래에서 조용히 건너뛴다 — 시나리오만 빠질 뿐 대화는 정상이다.
    # 테스트는 event_publisher 인자로 가짜를 주입한다.
    if event_publisher is None and wake is not None:
        from bomi_ai_chat.robot_events import build_robot_event_publisher

        event_publisher = build_robot_event_publisher(settings)
        if event_publisher is not None:
            event_publisher.start()

    # 회전 탐색 신호 발신자. 웨이크워드가 있을 때만 의미가 있다 — 부르지 않으면
    # 탐색을 시작할 계기도 없다. 이미 만들어져 있으면(테스트 주입) 그대로 쓴다.
    if runtime.search_signal is None and wake is not None:
        from bomi_ai_chat.search_signal import build_search_signal_sender

        runtime.search_signal = build_search_signal_sender(
            getattr(runtime, "beam", None))

    # 호출 응답("저를 부르셨나요?") 재생용 TTS. 웨이크워드 + 출력이 있을 때만 만든다.
    tts = None
    if wake is not None and audio_out is not None:
        from bomi_ai_chat.tts.client import TTSClient
        tts = TTSClient(settings)

    turns = 0
    logger.info("conversation loop started (graph path)")

    while max_turns is None or turns < max_turns:
        try:
            if wake is not None:
                # 백엔드 대화(START_CONVERSATION)를 웨이크워드 대기 도중에도
                # 알아챌 수 있게, 대기를 인터럽트하는 콜백을 연결한다. 큐가
                # 없는 실행(테스트, --once 등)에서는 아무 것도 하지 않는다 —
                # 실제 WakeWordDetector 만 이 속성을 읽고, 다른 wake 대역
                # 객체는 속성이 그냥 얹힐 뿐 아무 영향이 없다.
                #
                # ★ 왜 필요한가 (CLAUDE.md §3, 이동 중 침묵)
                #   현관 인사·복약 알림·온습도 안부는 아무도 "보미야"를 부르지
                #   않는다. wait_for_wake() 가 그 사이 계속 마이크를 쥐고
                #   있으면 backend 대화가 영원히 시작되지 못한다. 인터럽트가
                #   없으면 이 세 시나리오는 시연에서 절대 말을 하지 않는다.
                if runtime.backend_conversation_queue is not None:
                    wake.interrupt_check = _queue_has_item(
                        runtime.backend_conversation_queue)

                # "보미야" 대기 = SessionState.IDLE. 이 블로킹 호출이 곧 웨이크워드
                # 게이트다 — 리턴하기 전에는 capture/STT/그래프 어디에도 닿지 않는다
                # (시나리오 A: 웨이크워드 이전 발화 무반응).
                # 대기 중 Ctrl+C = 프로그램 종료(아래 except 로 나감).
                wake.wait_for_wake()

                # wait_for_wake() 가 실제 "보미야" 때문에 돌아왔는지, 위
                # interrupt_check 때문에 조기 반환했는지는 반환값만으로 구분할
                # 수 없다(둘 다 그냥 반환) — 그래서 큐를 다시 직접 확인한다.
                # 대기 중 인터럽트되지 않고 큐가 그 사이에 채워진 경우(드문
                # 레이스)도 이 분기로 들어오는데, 그 경우 이번 한 번의 진짜
                # "보미야"는 조용히 넘어간다 — 시연 대본에서는 발생하지 않고,
                # 발생해도 다시 부르면 그만이다.
                pending = _pop_pending_backend_conversation(runtime)
                if pending is not None:
                    turns, end_reason = _run_backend_conversation(
                        runtime, audio_in, stt, turns, max_turns, pending)
                    _publish_conversation_ended(runtime, pending, end_reason)
                    _flush_extraction_after_conversation(runtime)
                    continue

                # 감지 사실을 백엔드에 알린다 (S15P11E102-349). paho 의 publish 는
                # 큐잉이라 블로킹하지 않고, 실패는 발행자가 삼킨다 — 여기서 한 번 더
                # 감싸는 이유는 가짜 발행자(테스트)나 미래의 구현 변경이 던져도
                # 대화 시작을 막지 않기 위해서다.
                # 소리 방향을 먼저 로봇 내부로 보낸다(구현계획 §0). MQTT 는
                # 백엔드를 한 번 돌아오므로 UDP 힌트가 먼저 도착한다 — 시작
                # 신호가 왔을 때 wake_search 가 쓸 각도가 이미 있어야 한다.
                if runtime.search_signal is not None:
                    runtime.search_signal.send_wake()

                if event_publisher is not None:
                    try:
                        event_publisher.publish_wake_word()
                    except Exception:  # noqa: BLE001 - 시나리오는 부가, 대화가 본체다
                        logger.warning("wake-word publish failed", exc_info=True)

                if runtime.navigation_watcher is not None:
                    # 이동 중 침묵(§3a): 짧은 응답만 하고, 실제 리슨은 도착
                    # (또는 타임아웃) 뒤에 연다. 모터 소음 속에서 마이크를
                    # 열지 않으므로 ASR 오인식 리스크가 그만큼 사라진다.
                    from bomi_ai_chat import conversation_control, policy

                    runtime.navigation_watcher.reset()
                    _speak_ack(tts, audio_out,
                              message=conversation_control.WAKE_ACK_MOVING_MESSAGE)
                    arrived = runtime.navigation_watcher.wait_for_arrival(
                        policy.WAKE_MOVEMENT_WAIT_TIMEOUT_SEC)
                    if not arrived:
                        logger.warning(
                            "ARRIVED not observed within %.0fs; starting the "
                            "conversation anyway (silence would be worse)",
                            policy.WAKE_MOVEMENT_WAIT_TIMEOUT_SEC,
                        )
                else:
                    _speak_ack(tts, audio_out)      # 호출 응답 1회 (블로킹)

                turns, _end_reason = _run_graph_conversation(
                    runtime, audio_in, stt, turns, max_turns)
                # 대화가 끝나면 로봇도 멈춘다(구현계획 결정 C). 시간 상한
                # (wake_search 의 follow_timeout_sec)은 "대화가 끝나지 않을
                # 때"의 최후 방어선이고, 정상 종료는 여기서 즉시 끈다.
                if runtime.search_signal is not None:
                    runtime.search_signal.send_stop(
                        f"conversation_ended:{_end_reason}")
                _flush_extraction_after_conversation(runtime)
            else:
                # 웨이크워드 없음(팀원 기본): 매 발화를 그냥 처리한다.
                text, duration, _ = _listen(audio_in, stt)
                if not text:
                    continue
                run_user_turn(
                    runtime.app, runtime.senior_id, text, duration_sec=duration
                )
                turns += 1
                # 응답 재생이 끝날 때까지 기다린다. _run_graph_conversation(웨이크워드
                # 경로)에는 이미 있던 호출인데, 이 분기(웨이크워드 없음 = 233 점검이
                # WAKEWORD_ENABLED=0 으로 5절까지 강제하는 바로 그 경로)에는 빠져
                # 있었다. 안 기다리면 emit 이 논블로킹이라 재생 중에 바로 다음 _listen
                # 이 열려, 로봇이 방금 한 말을 마이크가 주워 어르신 발화로 오인한다
                # (233 실기 점검에서 실제로 재현됨).
                _wait_for_playback(runtime.echo_guard)
        except KeyboardInterrupt:
            logger.info("conversation loop stopped by user after %d turns", turns)
            break
        except Exception:  # noqa: BLE001 - 한 번의 수음 실패가 루프를 죽이면 안 된다
            logger.exception("turn failed; continuing")
            continue

    # 발행자 정리. 안 하면 프로그램 종료 후에도 paho 스레드가 남는다.
    if event_publisher is not None:
        try:
            event_publisher.stop()
        except Exception:  # noqa: BLE001 - 종료 정리 실패는 무시한다
            logger.debug("event publisher stop failed", exc_info=True)

    return turns


def warm_up_intent_router() -> None:
    """기존 시작 순서를 유지하면서 값싼 의도 규칙이 import 가능한지 확인한다.

    2026-08-06 평가에서 SentenceTransformer는 키워드 기준선과 정확도가 같았지만
    시작 6.28초와 working set 약 732.5MB를 사용해 운영 경로에서 제거했다. 이 훅은
    배포 전환 중 호출부 호환성을 지키며, 더 이상 모델을 올리거나 네트워크를 쓰지 않는다.
    """
    try:
        from bomi_ai_chat.llm import router

        router.is_medical_query("워밍업")
        logger.info("intent router rules ready")
    except Exception:  # noqa: BLE001 - 준비 실패가 대화를 막으면 안 된다
        logger.warning("could not prepare intent router rules", exc_info=True)


def _speak_ack(tts, audio_out, *, message: str | None = None) -> None:
    """호출 응답을 블로킹으로 재생한다.

    기본 문구는 WAKE_ACK_MESSAGE("네, 말씀하세요.")다. 이동 중 침묵(§3a)이
    켜져 있으면 호출부가 WAKE_ACK_MOVING_MESSAGE("네, 지금 갈게요.")를
    넘긴다 — 그 다음에는 실제로 마이크를 열지 않으므로 문구가 그 사실과
    맞아야 한다.

    실패해도 대화를 막지 않는다 — 인사는 곁가지다. 재생이 블로킹이므로 이 함수가
    끝난 뒤에 녹음이 시작된다. tts 나 audio_out 이 없으면 조용히 넘어간다.
    """
    if tts is None or audio_out is None:
        return
    from bomi_ai_chat import conversation_control

    text = message or conversation_control.WAKE_ACK_MESSAGE
    try:
        audio_out.play(tts.synthesize(text))
    except Exception:  # noqa: BLE001 - 호출 응답 실패가 대화를 막으면 안 된다
        logger.exception("failed to speak wake ack")


def _advance(session, event: str):
    """세션 상태를 한 칸 전진시킨다. 부기 실수로 로봇이 죽지 않게 감싼다.

    next_state 는 정의되지 않은 전이에서 ValueError 를 던진다 — 테스트에서는 그게
    옳다(웨이크워드 게이트가 뚫린 것을 조용히 넘기면 안 된다). 하지만 라이브 루프
    에서는 상태 '기록'의 실수가 상태 '기계'(실제 루프)를 멈추면 안 되므로, 여기서
    잡아 경고만 남기고 현재 상태를 유지한다.
    """
    from bomi_ai_chat import conversation_control

    try:
        return conversation_control.next_state(session, event)
    except ValueError:
        logger.warning("session bookkeeping out of step", exc_info=True)
        return session


def _run_graph_conversation(
    runtime, audio_in, stt, turns: int, max_turns,
    *, session_turn_limit: int | None = None,
    extend_on_wake_word: bool = False,
) -> tuple[int, str]:
    """'보미야'로 시작된 하나의 대화를 여러 발화로 이어간다(그래프 경로).

    세션 상태
        conversation_control.SessionState 의 전이표를 그대로 구동한다. 진입 시점은
        웨이크워드가 이미 감지된 뒤이므로 LISTENING 에서 시작하고, 종료 사유가
        확정되면 ENDING 을 거쳐 IDLE 로 닫는다(바깥 루프가 다시 웨이크워드를
        기다린다). 상태는 여기 지역 변수다 — 세션은 재부팅을 넘어 이어지지 않는
        것이 맞고(다시 부르는 것이 자연스럽다), checkpoint 에 남길 이유가 없다.

    종료 (세 가지)
        1) 무응답: 단일 15초 리슨(_listen 의 onset 타임아웃)으로 발화 시작을 기다린다.
           없으면 로봇은 아무 말도 하지 않고 조용히 대화를 끝낸다(§14 — 침묵이 자연).
        2) 마무리 언급: is_farewell 이면 그 발화를 그래프로 처리한 뒤 끝낸다.
           종료 인사를 따로 만들지 않는다 — 마무리 발화에 대한 그래프의 응답
           ("네, 편히 쉬세요" 류)이 곧 종료 응답이고, 그 재생이 끝난 뒤에 세션을
           닫으므로 잘리지 않는다(시나리오 L).
        3) Ctrl+C: 대화만 끝내고 바깥 루프가 다시 "보미야"를 기다린다(프로그램 종료 아님).

    각 발화는 run_user_turn 으로 그래프에 태운다 -> context_read(기억 조회) +
    memory_write(대화 저장)가 여기서 돈다.

    반환값
        (turns, end_reason). end_reason 은 "max_turns" | "interrupted" |
        "no_speech" | "farewell" 중 하나다. 백엔드가 시작한 대화
        (_run_backend_conversation)는 이 값을 CONVERSATION_ENDED.outcome 으로
        옮긴다 — 웨이크워드로 시작한 대화는 백엔드가 모르는 대화이므로 이 값을
        무시해도 된다.
    """
    from bomi_ai_chat import conversation_control, policy
    from bomi_ai_chat.graph.turn import run_user_turn

    session = conversation_control.SessionState.LISTENING
    session_turns = 0
    logger.info("SESSION_STARTED senior=%s", runtime.senior_id)
    print("[대화 시작] 말씀하세요. ('보미야' 다시 부를 필요 없음)")
    end_reason = "max_turns"
    while (
        (max_turns is None or turns < max_turns)
        and (
            session_turn_limit is None
            or session_turns < session_turn_limit
        )
    ):
        try:
            text, duration, no_speech = _listen(
                audio_in, stt,
                onset_timeout_seconds=policy.CONVERSATION_IDLE_TIMEOUT_SEC,
            )
        except KeyboardInterrupt:
            session = _advance(session, "interrupted")
            end_reason = "interrupted"
            print("[대화 종료] 다시 '보미야'로 부르면 새 대화를 시작합니다.")
            break

        if no_speech:
            session = _advance(session, "no_speech")
            end_reason = "no_speech"
            logger.info(
                "conversation ended: no speech within %ss",
                policy.CONVERSATION_IDLE_TIMEOUT_SEC,
            )
            print("[대화 종료] 무응답으로 종료. 다시 '보미야'로 부르면 새 대화.")
            break

        if not text:
            # 발화는 있었으나 못 알아들었다. 되묻지 않고 다음 리슨으로 넘어간다.
            session = _advance(session, "stt_empty")
            continue

        session = _advance(session, "speech_captured")

        if extend_on_wake_word and "보미야" in text.replace(" ", ""):
            session_turn_limit = None
            logger.info(
                "homecoming wake word detected; extending to free conversation")

        # "기다려", "잠깐만" 같은 발화는 대화를 끝내자는 말이 아니라 움직이지
        # 말라는 말이다. 대화는 그대로 이어가고 로봇의 몸만 멈춘다.
        if (runtime.search_signal is not None
                and conversation_control.is_search_stop_request(text)):
            runtime.search_signal.send_stop("user_requested_wait")
            logger.info("search stop requested by the user utterance")

        closing_turn = (
            session_turn_limit is not None
            and session_turns + 1 >= session_turn_limit
        )
        run_user_turn(
            runtime.app,
            runtime.senior_id,
            text,
            duration_sec=duration,
            closing_turn=closing_turn,
        )
        session = _advance(session, "turn_done")
        turns += 1
        session_turns += 1

        # 응답 재생이 끝날 때까지 기다린다(의도적으로 barge-in 없음). 안 기다리면 재생
        # 중에 다음 리슨이 열려 마이크가 로봇 자기 목소리를 사용자 발화로 수음한다.
        _wait_for_playback(runtime.echo_guard)
        session = _advance(session, "playback_done")

        if conversation_control.is_farewell(text):
            session = _advance(session, "farewell")
            end_reason = "farewell"
            logger.info("conversation ended: farewell detected")
            print("[대화 종료] 마무리 언급 감지. 다시 '보미야'로 부르면 새 대화.")
            break

    if session is conversation_control.SessionState.ENDING:
        session = _advance(session, "session_closed")
    logger.info("SESSION_ENDED senior=%s reason=%s turns=%d",
                runtime.senior_id, end_reason, turns)
    return turns, end_reason


# ─────────────────────────────────────────────────────────────────────────────
# 백엔드가 시작하는 대화 (START_CONVERSATION, CLAUDE.md §3)
#
# 현관 인사·복약 알림·온습도 안부, 세 시나리오가 여기를 지난다. 보미야 호출은
# 로봇이 자체적으로 시작하므로 이 경로를 타지 않는다(계약 §2.2).
# ─────────────────────────────────────────────────────────────────────────────


def _queue_has_item(pending_queue: queue.Queue):
    """`wake.interrupt_check` 에 넣을 콜백을 만든다. 큐가 비어 있지 않으면 True.

    실제 WakeWordDetector.wait_for_wake() 는 1초마다 이 콜백을 확인해, True 면
    마이크 스트림을 닫고 조기 반환한다(audio_io/wakeword.py 참고) — 그래야
    아무도 "보미야"를 부르지 않아도 backend 대화가 시작될 수 있다.
    """
    return lambda: not pending_queue.empty()


def _pop_pending_backend_conversation(runtime):
    """대기 중인 backend 대화 명령을 하나 꺼낸다. 없으면 None.

    큐가 아예 없는 실행(runtime.backend_conversation_queue is None — 테스트,
    또는 MQTT 가 꺼진 실행)에서는 항상 None 이다.
    """
    pending_queue = runtime.backend_conversation_queue
    if pending_queue is None:
        return None
    try:
        return pending_queue.get_nowait()
    except queue.Empty:
        return None


def _run_backend_conversation(
    runtime, audio_in, stt, turns: int, max_turns, command
) -> tuple[int, str]:
    """백엔드가 시작한 대화 하나를 진행한다: 첫 문장 발화 -> 이어 듣기.

    무엇을 하는가
        `command.text` 를 backend_command 경로로 그래프에 태워 첫 문장을
        말한다(handle_greeting — CLAUDE.md 구 §11 재정의: 문구 선택은
        백엔드 몫, 로봇은 §14 를 지켜 말하기만 한다). 재생이 끝나면
        _run_graph_conversation 을 그대로 재사용해 이어지는 발화를 듣는다 —
        "보미야"로 연 대화든 백엔드가 연 대화든, LISTENING 이후는 완전히
        같은 세션 기계를 탄다.

    왜 run_user_turn 이 아니라 app.invoke(trigger_type="backend_command") 인가
        run_user_turn 은 "user_utterance" 경로라 note_interaction/safety_triage
        를 거친다. 이 문장은 어르신이 아니라 백엔드가 결정한 것이므로, 그
        판정을 다시 거치면 안 된다(build.py 모듈 docstring: "백엔드 명령이
        게이트를 건너뛰는 것이 의도다").

    반환값
        (turns, end_reason). end_reason 은 이 함수 자체에서 나는 "failed"
        (첫 문장 발화가 예외로 실패)이거나, 이어지는
        _run_graph_conversation 의 종료 사유를 그대로 물려받는다.

    주의사항
        - 첫 문장 발화가 실패해도 예외를 밖으로 던지지 않는다 — 호출부(메인
          루프)가 죽으면 이후 모든 웨이크워드/백엔드 대화가 멈춘다.
        - 이 함수가 실패해도 CONVERSATION_ENDED 는 호출부가 책임진다(반환된
          end_reason 을 보고 발행한다) — 실패 상황에서도 백엔드에 뭔가는
          알려야 5분 워치독까지 기다리지 않는다.
    """
    from bomi_ai_chat import policy

    config = {"configurable": {"thread_id": runtime.senior_id}}
    try:
        runtime.app.invoke(
            {
                "trigger_type": "backend_command",
                "senior_id": runtime.senior_id,
                "command": {
                    "text": command.text,
                    # 그래프의 7개 인텐트 중 "greeting" 이 정확히 이 역할이다
                    # (handle_greeting: "백엔드가 정한 문구를 발화로 옮긴다").
                    # 백엔드의 intent(WELLNESS_CHECK 등)는 그 자체로는 그래프
                    # 라우팅에 쓸 수 없는 값이라 origin 태그로만 남긴다.
                    "intent": "greeting",
                    "origin": f"scenario:{command.intent}",
                },
            },
            config,
        )
    except Exception:  # noqa: BLE001 - 한 대화의 실패가 루프를 죽이면 안 된다
        logger.exception(
            "backend conversation seed turn failed (conversationId=%s)",
            command.conversation_id,
        )
        return turns, "failed"

    turns += 1
    _wait_for_playback(runtime.echo_guard)
    # 귀가 인사는 짧은 현관 시나리오다. 두 번의 사용자 응답을 처리한 뒤
    # COMPLETED를 발행해야 백엔드가 NAVIGATE(DEFAULT) 복귀를 이어갈 수 있다.
    # 다른 능동 대화와 일반 웨이크워드 대화는 기존처럼 작별/무응답까지 계속한다.
    session_turn_limit = (
        policy.HOMECOMING_USER_TURN_LIMIT
        if command.intent == "HOMECOMING_GREETING"
        else None
    )
    result = _run_graph_conversation(
        runtime,
        audio_in,
        stt,
        turns,
        max_turns,
        session_turn_limit=session_turn_limit,
        extend_on_wake_word=(command.intent == "HOMECOMING_GREETING"),
    )
    if (
        command.intent == "HOMECOMING_GREETING"
        # 현관 인사에 답하지 않거나 작별 인사를 해도 귀가 시나리오의
        # 추종·온습도 단계는 계속 진행한다. 실패/취소만 중단한다.
        and result[1] in ("max_turns", "no_speech", "farewell")
        and os.environ.get("HOMECOMING_FOLLOW_AMBIENT_PHASE", "false").lower()
            in ("1", "true", "yes")
    ):
        return _run_homecoming_follow_ambient_phase(
            runtime, audio_in, stt, result[0])
    return result


def _run_homecoming_follow_ambient_phase(runtime, audio_in, stt, turns: int):
    """현관 대화 뒤 추종하고, 완전히 정지한 다음 최신 온습도로 대화한다."""
    from bomi_ai_chat import policy

    signal = runtime.search_signal
    subscriber = runtime.ai_command_subscriber
    ambient = getattr(subscriber, "_ambient", None)
    if signal is None or ambient is None:
        logger.warning("homecoming follow/ambient phase is unavailable")
        return turns, "max_turns"

    follow_seconds = max(0.0, float(os.environ.get("HOMECOMING_FOLLOW_SECONDS", "20")))
    send_follow = getattr(signal, "send_follow", None)
    if callable(send_follow):
        send_follow()
    else:
        signal.send_wake()
    logger.info("homecoming follow phase started for %.1f seconds", follow_seconds)
    try:
        time.sleep(follow_seconds)
    finally:
        # wake_search가 0속도와 follow_enable=false를 함께 발행한다.
        signal.send_stop("homecoming_follow_phase_complete")
    time.sleep(0.5)

    text = ambient.conversation_text()
    if text is None:
        text = "할머니, 온도와 습도 센서 값이 아직 들어오지 않았어요. 몸은 괜찮으세요?"
    config = {"configurable": {"thread_id": runtime.senior_id}}
    runtime.app.invoke({
        "trigger_type": "backend_command",
        "senior_id": runtime.senior_id,
        "command": {
            "text": text,
            "intent": "greeting",
            "origin": "homecoming:post_follow_ambient",
        },
    }, config)
    turns += 1
    _wait_for_playback(runtime.echo_guard)

    user_text, _duration, no_speech = _listen(
        audio_in, stt, onset_timeout_seconds=policy.CONVERSATION_IDLE_TIMEOUT_SEC)
    if no_speech or not user_text:
        return turns, "homecoming_follow_complete"
    from bomi_ai_chat.graph.turn import run_user_turn
    run_user_turn(
        runtime.app, runtime.senior_id, user_text,
        closing_turn=True,
    )
    _wait_for_playback(runtime.echo_guard)
    return turns + 1, "homecoming_follow_complete"


def _flush_extraction_after_conversation(runtime) -> None:
    """대화가 끝났으니 추출 큐를 바로 한 번 비운다 (S15P11E102-393).

    왜 여기인가
        방금 나눈 이야기에서 뽑을 사실이 큐에 들어 있는 순간이다. 이 호출이
        없으면 다음 스케줄러 틱까지 최대 policy.EXTRACTION_FLUSH_INTERVAL_SEC
        (60초)를 기다린다 — 어르신이 말한 약속이 보호자 화면에 뜨는 시각이
        그만큼 늦는다.

    왜 결과를 기다리지 않는가
        flush 는 대기 행마다 LLM 을 부른다. 여기서 기다리면 그 시간 동안
        웨이크워드 대기가 열리지 않아 로봇이 "보미야"에 반응하지 못한다.
        스케줄러의 다음 실행 시각을 '지금'으로 당기기만 하고 즉시 돌아온다 —
        실제 실행은 스케줄러 워커 스레드가 한다.

    주의사항
        스케줄러가 없으면(시작 실패, 테스트) 아무 일도 일어나지 않는다. 실패해도
        대화 루프를 죽이지 않는다 — 큐 행은 그대로 남아 다음 틱이 다시 집으므로
        여기서의 실패는 "조금 늦어진다" 이상이 아니다.
    """
    try:
        from bomi_ai_chat.jobs.scheduler import run_extraction_flush_now

        run_extraction_flush_now(getattr(runtime, "scheduler", None))
    except Exception:  # noqa: BLE001 - 추출은 부가 기능, 대화 루프가 본체다
        logger.warning("could not bring the post-conversation extraction flush forward",
                       exc_info=True)


def _publish_conversation_ended(runtime, command, end_reason: str) -> None:
    """대화 종료를 백엔드에 알린다. 실패해도 예외를 올리지 않는다.

    구독자가 없으면(MQTT 꺼짐, 시작 실패) 아무것도 하지 않는다 — 그 경우
    애초에 CONVERSATION_STARTED 도 안 나갔을 것이므로 ENDED 를 보낼 이유가
    없다(짝이 안 맞는 이벤트를 보내지 않는다).
    """
    subscriber = runtime.ai_command_subscriber
    if subscriber is None:
        return

    from bomi_ai_chat.contracts import ai_commands as ai_contract

    # _run_graph_conversation 의 end_reason -> CONVERSATION_ENDED.outcome.
    # "failed" 는 _run_backend_conversation 자신이 만드는 값이다.
    end_reason_to_outcome = {
        "farewell": (ai_contract.OUTCOME_COMPLETED, None),
        "max_turns": (ai_contract.OUTCOME_COMPLETED, None),
        "no_speech": (ai_contract.OUTCOME_NO_RESPONSE, None),
        "interrupted": (ai_contract.OUTCOME_CANCELLED, None),
        "failed": (ai_contract.OUTCOME_FAILED, "INTERNAL_ERROR"),
        "homecoming_follow_complete": (
            ai_contract.OUTCOME_COMPLETED, "HOMECOMING_FOLLOW_COMPLETED"),
    }
    outcome, reason_code = end_reason_to_outcome.get(
        end_reason, (ai_contract.OUTCOME_COMPLETED, None))
    try:
        subscriber.publish_conversation_ended(command, outcome, reason_code)
    except Exception:  # noqa: BLE001 - 발행 실패가 루프를 막으면 안 된다
        logger.warning("failed to publish CONVERSATION_ENDED", exc_info=True)


def _wait_for_playback(echo_guard, poll_sec: float = 0.05, max_wait_sec: float = 30.0) -> None:
    """로봇 응답 재생이 끝날 때까지(echo_guard.is_playing == False) 기다린다.

    왜 필요한가
        그래프 응답은 논블로킹으로 재생된다. 웨이크워드 대화에서는 barge-in 을 빼기로
        했으므로, 재생이 끝난 뒤에 다음 리슨을 연다. 이렇게 안 하면 재생 중에 마이크가
        열려 로봇 자기 목소리를 사용자 발화로 수음한다(에코 겹침).

    is_playing 은 재생 스레드(SpeechPlayback)가 시작/끝에 갱신한다. run_user_turn 이
    반환할 때는 이미 표시가 켜져 있으므로(재생 스레드 시작 '전에' 표시함) 경합이 없다.
    응답이 없던 턴이면 is_playing 이 False 라 즉시 반환한다.

    안전장치
        재생 스레드가 어떤 이유로 상태를 안 내려도 무한히 막히지 않게 max_wait_sec 상한.
        echo_guard 가 없으면(재생기 미연결) 즉시 반환한다.

    확장 지점
        barge-in 이 다시 필요해지면 이 대기를 없애고 EchoGuard 를 '캡처'에 연결하는
        방식으로 바꾼다(재생 중엔 입력 무시/문턱↑). 지금은 상태 공유만 해두면 그 확장이
        수월하다.
    """
    if echo_guard is None:
        return
    import time

    waited = 0.0
    while echo_guard.is_playing and waited < max_wait_sec:
        time.sleep(poll_sec)
        waited += poll_sec


def _listen(
    audio_in, stt, onset_timeout_seconds: float | None = None
) -> tuple[str, float, bool]:
    """한 번 수음해서 (텍스트, 길이, 무응답여부)를 돌려준다.

    길이를 함께 돌려주는 이유
        맞장구("응")와 진짜 끼어들기를 구분하는 데 필요하다. 텍스트만으로는
        부족하다 — "네"는 질문에 대한 진짜 대답일 수도 있다 (CLAUDE.md §13).

    onset_timeout_seconds (단일 리슨)
        값을 주면 capture 가 '발화 시작'을 그 시간까지 기다린다. 그 안에 아무 말도
        없으면 capture 가 빈 바이트를 주고, 여기서 no_speech=True 로 알린다. 대화
        세션의 '무응답 종료'가 이걸 쓴다. None 이면 기존 동작(첫 순간부터 녹음).

    반환값
        (text, duration, no_speech)
        - no_speech=True : onset 타임아웃 동안 발화 자체가 없었다(무응답).
        - text="" & no_speech=False : 발화는 있었으나 STT 가 못 알아들었다.
    """
    from bomi_ai_chat.clock import clock

    started = clock.now()
    audio = audio_in.capture(onset_timeout_seconds=onset_timeout_seconds)
    if not isinstance(audio, bytes) or not audio:
        # capture 가 빈 바이트 -> onset 모드면 '무응답', 일반 모드면 그냥 빈 수음.
        return "", 0.0, onset_timeout_seconds is not None

    text = (stt.transcribe(audio) or "").strip()

    # STT 가 실제로 뭐라고 알아들었는지 콘솔에 남긴다. pipeline.py(구 경로)는
    # 이미 이걸 찍었는데, 그래프 경로(이 함수)는 안 찍고 있었다. 그래서 인텐트
    # 분류가 왜 그렇게 나왔는지(classify_intent 는 이 텍스트를 그대로 받는다)
    # 어르신이 실제로 뭐라 말했는지 모른 채로 추측만 하게 됐다.
    print(f"[STT] 인식된 텍스트: {text or '(인식 실패)'}")

    return text, max(0.0, clock.now() - started), False
