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
    # 재생기(재생 상태를 표시)와 대화 루프(재생 끝날 때까지 대기)가 공유하는 에코 가드.
    # 응답 재생 중에 다음 리슨을 열지 않기 위한 근거(is_playing)를 여기서 읽는다.
    echo_guard: Any = None

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

    runtime = Runtime(app=app, senior_id=senior_id, echo_guard=echo_guard)
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
                # "보미야" 대기 = SessionState.IDLE. 이 블로킹 호출이 곧 웨이크워드
                # 게이트다 — 리턴하기 전에는 capture/STT/그래프 어디에도 닿지 않는다
                # (시나리오 A: 웨이크워드 이전 발화 무반응).
                # 대기 중 Ctrl+C = 프로그램 종료(아래 except 로 나감).
                wake.wait_for_wake()
                _speak_ack(tts, audio_out)          # 호출 응답 1회 (블로킹)
                turns = _run_graph_conversation(runtime, audio_in, stt, turns, max_turns)
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


def _speak_ack(tts, audio_out) -> None:
    """호출 응답(WAKE_ACK_MESSAGE, 현재 "네, 말씀하세요.")을 블로킹으로 재생한다.

    실패해도 대화를 막지 않는다 — 인사는 곁가지다. 재생이 블로킹이므로 이 함수가
    끝난 뒤에 녹음이 시작된다. tts 나 audio_out 이 없으면 조용히 넘어간다.
    """
    if tts is None or audio_out is None:
        return
    from bomi_ai_chat import conversation_control

    try:
        audio_out.play(tts.synthesize(conversation_control.WAKE_ACK_MESSAGE))
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


def _run_graph_conversation(runtime, audio_in, stt, turns: int, max_turns) -> int:
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
    """
    from bomi_ai_chat import conversation_control, policy
    from bomi_ai_chat.graph.turn import run_user_turn

    session = conversation_control.SessionState.LISTENING
    logger.info("SESSION_STARTED senior=%s", runtime.senior_id)
    print("[대화 시작] 말씀하세요. ('보미야' 다시 부를 필요 없음)")
    end_reason = "max_turns"
    while max_turns is None or turns < max_turns:
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
        run_user_turn(runtime.app, runtime.senior_id, text, duration_sec=duration)
        session = _advance(session, "turn_done")
        turns += 1

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
    return turns


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
