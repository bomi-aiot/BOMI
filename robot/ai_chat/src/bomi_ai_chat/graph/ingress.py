"""턴이 시작될 수 있는 네 가지 경로, 그리고 그 사이의 라우팅.

어디에 위치하는가
    그래프의 맨 위. CLAUDE.md §6 에서 게이트나 트리아지보다 먼저 일어나는 모든 것이
    여기 있다.

    네 개의 진입 경로이며, 일부러 '대칭이 아니다'.

      "user_utterance"  -> note_interaction -> safety_triage
            어르신이 말했다. 방금 우리에게 말을 건 사람에게 대답할 허락을 게이트에
            구하지 않는다.

      "proactive"       -> proactive_gate
            스케줄러나 침묵 사다리가 제안했다. 허락을 받아야 한다.

      "door_event"      -> door_event -> END
            센서가 발동했다. occupancy 는 세상에 대한 사실이므로 즉시 반영하고,
            **여기서 끝난다.** 인사를 제안하지 않는다.

      "backend_command" -> backend_command -> context_read -> ...
            백엔드가 말하라고 명령했다. 게이트를 거치지 않는다 — 이미 판정한 쪽이
            보낸 것이므로 여기서 다시 판정하면 심판이 둘이 된다.

왜 door_event 가 인사를 제안하지 않는가  ★ 2026-08-01 재정의
    초안에서는 door_event 가 인사 제안을 만들고 로봇의 게이트가 그것을 심판했다.
    합의된 구조는 다르다. **배웅·환영 인사 판정은 백엔드가 한다** (CLAUDE.md §11).

    백엔드는 시나리오 기록·오늘 일정·동의 상태를 갖고 있어 판단 근거가 그쪽에 있다.
    로봇에서 같은 판단을 다시 하면 같은 규칙이 두 곳에 생기고, 두 곳은 갈라진다.

    로봇의 네 게이트(§7)는 여전히 '로봇이 스스로 시작하는' 발화 전부를 심판한다 —
    일정 알림, 침묵 프로브, 재질의. 백엔드가 명령한 인사만 별도 경로다.

왜 note_interaction 이 독립 노드인가
    어르신이 말하면, 다른 무엇보다 먼저 서로 무관한 네 가지가 일어나야 한다.
    시계 리셋, 침묵 사다리 리셋, occupancy 정정, barge-in 처리. 넷 중 어느 것도
    안전 분류가 아니다. 이걸 safety_triage 안에 넣으면 그 노드가 두 가지 일을 하게
    되고 둘 다 테스트하기 어려워진다.

읽는 값   trigger_type, user_input, speaking, occupancy, last_door_event, command
쓰는 값   last_user_interaction_at, silence_level, occupancy, speaking,
          interrupted_remainder, is_backchannel, proposals, intent, user_input

참고
    CLAUDE.md §6 (아키텍처), §11 (현관 센서), §13 (barge-in)
    S15P11E102-208 (이 재정의), S15P11E102-226 (백엔드 측 인사 판정)
"""

from __future__ import annotations

import logging

from langgraph.graph import END

from bomi_ai_chat import policy
from bomi_ai_chat.clock import clock
from bomi_ai_chat.door import occupancy as occupancy_rules
from bomi_ai_chat.graph import output
from bomi_ai_chat.localstore import runtime as runtime_store
from bomi_ai_chat.state import ConvState, SpeechProposal

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 진입 라우팅
# ─────────────────────────────────────────────────────────────────────────────


def route_ingress(state: ConvState) -> str:
    """START 에서 나가는 조건부 엣지: 진입 경로를 고른다.

    무엇을 하는가
        trigger_type 을 그 경로의 첫 노드로 매핑한다.

    누가 호출하는가
        build.py:  g.add_conditional_edges(START, route_ingress, {...})

    반환값
        "note_interaction", "proactive_gate", "door_event", "backend_command" 중 하나.

    주의사항
        여기서 KeyError 가 나면 누군가 trigger_type 없이 그래프를 호출했다는 뜻이다.
        요란하게 실패하는 것이 의도다. 조용히 한쪽 경로로 기본값을 주면 능동 턴이
        게이트를 건너뛰게 되는데, 그것은 절대 일어나서는 안 되는 유일한 일이다.
    """
    return {
        "user_utterance": "note_interaction",
        "proactive": "proactive_gate",
        "door_event": "door_event",
        "backend_command": "backend_command",
    }[state["trigger_type"]]


# ─────────────────────────────────────────────────────────────────────────────
# 반응형 경로: 어르신이 말했다
# ─────────────────────────────────────────────────────────────────────────────


def _is_backchannel(text: str, duration_sec: float) -> bool:
    """진짜 끼어들기가 아니라 짧은 맞장구인가?

    무엇을 하는가
        '짧은 길이'와 'policy.BACKCHANNELS 일치'를 모두 요구한다.

    왜 두 조건 모두인가
        텍스트만으로는 부족하다. "네"는 질문에 대한 진짜 대답일 수 있다. 길이만으로도
        부족하다. 짧은 발화가 진짜 끼어들기일 수 있다("아파"). 둘 다 요구하면 오탐이
        낮아지고, 여기서의 오탐은 곧 '어르신이 실제로 한 말을 로봇이 무시하는 것'이다.

    누가 호출하는가
        note_interaction. 로봇이 말하는 중일 때만. 로봇이 조용할 때의 "응"은 그냥
        (정보가 적은) 평범한 턴이다.

    반환값
        True -> 계속 말한다. 응답 없이 이 턴을 끝낸다.

    주의사항
        policy.BACKCHANNELS 는 상상이 아니라 실제 녹취록에서 채운다.
        사투리와 개인 습관이 지배적인 영역이다.
    """
    return duration_sec < policy.BACKCHANNEL_MAX_SEC and text.strip() in policy.BACKCHANNELS


def note_interaction(state: ConvState) -> dict:
    """반응형 첫 노드: 상호작용을 기록하고 barge-in 을 처리한다.

    무엇을 하는가
        네 가지를 이 순서로 한다.
          1. last_user_interaction_at 을 찍고 silence_level 을 0으로 되돌린다.
             발화는 가장 강력한 생존 증거이므로 사다리는 처음으로 돌아간다.
          2. occupancy 를 HOME 으로 강제한다. 발화가 현관 센서를 이긴다. 집 안에서
             목소리가 들리면 센서가 뭐라 했든 집에 있는 것이다.
          3. 로봇이 말하는 중이면, 이것이 맞장구인지(계속 말한다) 진짜 끼어들기인지
             (양보한다) 판단한다.
          4. 진짜 끼어들기면 재생을 취소하고, 말하지 못한 나머지를 재큐용으로 넘긴다.

    왜 존재하는가
        어르신이 무슨 말을 했든 모든 반응형 턴이 해야 하는 기록 작업이다.
        이걸 safety_triage 밖에 두면 그 노드는 순수한 분류기로 남을 수 있다.

    누가 호출하는가
        build.py. "user_utterance" 경로의 첫 노드.

    무엇을 호출하는가
        _is_backchannel. audio/ 가 들어오면 TTS 취소 API 도 호출한다.

    반환값
        부분 state. is_backchannel 이 True 면 route_interaction 이 턴을 즉시 끝낸다.
        "응"에 대답하기 위해 전체 파이프라인을 돌리지 않는다.

    주의사항
        - 2번은 편의 기능이 아니라 안전 장치다. 실제 가정에서 센서와 발화는 어긋난다
          (방문자, 눈치채지 못한 외출). 발화가 이겨야 한다. 그러지 않으면 침묵 사다리가
          틀린 occupancy 를 근거로 추론한다.
        - 생존 확인 프로브 뒤에는 잘린 나머지를 재개하지 '않는다'. 끼어든 것 자체가
          프로브가 물으려던 것을 이미 증명했다. 재개하면 방금 대답한 사람에게 걱정스러운
          질문을 반복하는 로봇이 된다 (CLAUDE.md §13).
        - **내구 저장소에도 쓴다.** 아래 _persist_interaction 참고. 이것 없이는
          이 노드가 하는 일이 침묵 사다리에 도달하지 못한다.
    """
    now = clock.now()
    out: dict = {
        "last_user_interaction_at": now,
        "silence_level": 0,
        "occupancy": "HOME",
        "occupancy_observed_at": now,
        "is_backchannel": False,
    }

    # 대화 경계 판정 — 이어 붙일지, 새로 열지 (S15P11E102-306).
    #
    # 반드시 last_user_interaction_at 을 위에서 '덮어쓰기 전'의 값(= state 에 남아
    # 있던 지난 상호작용 시각)으로 판정해야 한다. out 은 아직 state 에 합쳐지지
    # 않았으므로 여기서 state.get(...) 을 읽는 것이 정확하다.
    out.update(_conversation_boundary(state, now))

    # 맞장구로 끝나는 턴에서도 먼저 저장한다. "응" 한마디도 생존 증거다.
    _persist_interaction(state, now)

    if not state.get("speaking"):
        return out

    text = state.get("user_input", "")
    duration = state.get("user_input_duration_sec", 0.0)

    if _is_backchannel(text, duration):
        # 계속 말한다. 여기서 턴이 끝나므로 재생에는 손대지 않는다.
        out["is_backchannel"] = True
        return out

    # 양보 우선(yield-first): 어르신의 발화가 우리 발화보다 가치 있다 (CLAUDE.md §13).
    # 양보 우선(yield-first): 어르신의 발화가 우리 발화보다 가치 있다 (CLAUDE.md §13).
    out["speaking"] = False
    out["interrupted_remainder"] = _yield_playback(state)
    return out


def _persist_interaction(state: ConvState, now: float) -> None:
    """발화가 남긴 안전 신호를 내구 저장소에도 쓴다.

    ★ 왜 이 함수가 있어야 하는가 — 208 에서 발견한 결함

        침묵 사다리(jobs/ticks.silence_tick)는 그래프를 거치지 않고 runtime_state 를
        읽는다. 그런데 이 노드는 LangGraph checkpoint 에만 썼다. 그래서 어르신이
        하루 종일 대화해도 runtime_state 의 last_user_interaction_at 은 갱신되지 않았다.

        기본값이 0 이고 아무도 쓰지 않았으므로, 실기에서 사다리는 `last_interaction
        <= 0.0` 가드에서 매번 조용히 되돌아갔다. **207 의 침묵 사다리가 production
        에서는 한 번도 돌지 않는 상태였다.** 테스트는 runtime_store 에 값을 직접
        넣어주기 때문에 통과했다.

        같은 이음이 문 이벤트에도 있다(door_event). 그래서 두 노드 모두 두 곳에 쓴다.
        수명이 다른 두 저장소이므로 중복이 아니다 — door/intake.py 의 설명 참고.

    왜 여기서 예외를 삼키지 않는가
        삼키면 이 결함이 두 번째로 조용해진다. 저장이 실패하면 사다리가 다시 멈추므로,
        요란하게 실패하는 편이 낫다. 이 경로는 이미 turn.run_user_turn 이 예외를
        잡아 한 턴만 버리도록 감싸고 있다.
    """
    senior_id = state.get("senior_id")
    if not senior_id:
        # senior_id 없이 그래프를 부른 것이다. checkpoint 는 thread_id 로 동작하니
        # 턴 자체는 굴러가지만, 내구 저장은 대상을 특정할 수 없다.
        logger.warning("note_interaction has no senior_id; the silence ladder will not "
                       "see this interaction")
        return

    runtime_store.reset_silence(senior_id)
    occupancy_rules.set_occupancy(senior_id, "HOME", observed_at=now, source="speech")


def _conversation_boundary(state: ConvState, now: float) -> dict:
    """이번 발화가 이어지는 대화인가, 새 대화의 시작인가 (S15P11E102-306).

    왜 필요한가
        conversation_id 를 무조건 이어 붙이면 로봇이 켜져 있는 내내 대화가 하나로
        무한히 커진다 — "최근 대화" 문맥 조립이 의미를 잃는다. 반대로 매 턴 새로
        열면(306 에서 고친 결함) 로봇이 방금 자기가 한 말도 기억하지 못한다.
        그래서 '유휴 시간'이라는 중간 기준이 필요하다.

    무엇을 하는가
        state 에 남아 있던(= 이번 턴이 last_user_interaction_at 을 덮어쓰기 '전'의)
        마지막 상호작용 시각과 지금 사이의 간격을 본다. 간격이
        policy.CONVERSATION_BOUNDARY_IDLE_SEC 를 넘으면 conversation_id 를 명시적으로
        None 으로 되돌린다.

    왜 {"conversation_id": None} 을 반환하는 것으로 충분한가
        state.py 의 conversation_id 에는 reducer 가 없다(기본 LastValue 채널). 이
        함수가 그 키를 돌려주면 이번 턴부터 체크포인트 값이 덮인다.
        graph/build.py 의 memory_write(_record_turn) 는 conversation_id=None 을
        "새로 열어라"는 뜻으로 백엔드에 보내고(backend_client/conversation_client.py),
        백엔드가 새 id 를 배정해 돌려준다.

    누가 호출하는가
        note_interaction. 세 반환 경로(맞장구 포함) 전부가 이 함수의 결과를 이미
        담은 out 을 공유하므로, 어느 경로로 끝나든 경계 판정은 빠지지 않는다.

    반환값
        {"conversation_id": None} -> 경계를 넘었다. 새 대화가 열린다.
        {}                        -> 아직 같은 대화다. 키를 아예 안 넣어서 체크포인트
                                      값을 그대로 둔다.

    주의사항
        - 첫 턴(콜드 스타트)의 last_user_interaction_at 은 initial_state 가 부팅
          시각으로 채운 값이다. 그 값과 지금 사이의 간격이 우연히 임계값을 넘어도
          해가 없다 — 새 thread 의 conversation_id 는 애초에 None 이었다.
        - runtime_store 에도 즉시 써 둔다. 스케줄러(jobs/scheduler.py)의
          contract_tick 은 그래프 checkpoint 를 보지 못하고 runtime_store 를 읽으므로,
          여기서 갱신하지 않으면 이미 닫힌 대화의 id 로 "한 대화에 후보 하나"를
          계속 세게 된다. memory_write 가 새 id 로 다시 덮어쓴다.
    """
    previous = state.get("last_user_interaction_at") or 0.0
    if previous <= 0.0:
        # 상호작용 기록이 없다(콜드 스타트 직후 또는 테스트가 직접 넣은 최소 state).
        # 비교할 '이전'이 없으니 경계를 판정하지 않는다.
        return {}

    idle_for = now - previous
    if idle_for < policy.CONVERSATION_BOUNDARY_IDLE_SEC:
        return {}

    logger.info(
        "conversation idle for %.0fs (boundary=%ds); starting a new conversation",
        idle_for, policy.CONVERSATION_BOUNDARY_IDLE_SEC)

    senior_id = state.get("senior_id")
    if senior_id:
        runtime_store.save(senior_id, conversation_id=None)

    return {"conversation_id": None}


def _yield_playback(state: ConvState) -> SpeechProposal | None:
    """재생을 멈추고, 말하지 못한 나머지를 재큐할 제안으로 만든다.

    무엇을 하는가
        재생 핸들을 취소하고, 그 핸들에게 '어디까지 말했는지'를 물어 나머지를
        꺼낸다. 나머지가 있으면 원래 우선순위 그대로 다시 제안한다.

    왜 state 가 아니라 핸들에게 묻는가  ★ 이 함수의 핵심
        spoken_prefix 는 주인이 둘이다 — 재생 스레드와 checkpoint 된 state.
        state 값은 그래프 실행 시점의 스냅샷이라, 그 사이 재생이 더 진행됐으면
        낡아 있다. 낡은 값을 믿으면 이미 말한 문장을 다시 말한다.
        진행 상황의 권위는 재생 스레드에 있다 (CLAUDE.md §13).

    반환값
        재큐할 SpeechProposal, 또는 None(재큐할 것이 없거나 재큐하면 안 될 때).

    주의사항
        생존 확인 프로브는 재개하지 '않는다'. 끼어든 것 자체가 프로브가 물으려던
        것을 이미 증명했다. 재개하면 방금 대답한 사람에게 "괜찮으세요?"를 다시
        묻는 로봇이 된다. barge-in 은 생존 증거다.
    """
    senior_id = state.get("senior_id") or ""
    handle = output.TTS_HANDLES.get(senior_id)
    context = output.SPEECH_CONTEXT.get(senior_id, {})

    if handle is None:
        # state 는 말하는 중이라는데 핸들이 없다. 재생기가 없는 환경이거나 이미
        # 끝난 것이다. 취소할 것이 없으니 조용히 넘어간다.
        return None

    handle.cancel()
    remaining = handle.remaining_sentences()
    output.clear_speech_state(senior_id)

    priority = context.get("priority")
    if priority == "critical":
        # 생존 확인 프로브. 나머지를 '일부러' 버린다.
        logger.info("barge-in during a liveness probe; discarding the remainder — "
                    "the interruption is the answer")
        return None

    if not remaining:
        return None

    return {
        "intent": context.get("intent") or "companion",
        "priority": priority or "medium",
        "seed": " ".join(remaining),
        # 원래 origin 에 표시를 남긴다. "왜 로봇이 이 말을 했는가"를 추적할 때
        # 이것이 이어붙인 나머지임을 알 수 있어야 한다.
        "origin": f"{context.get('origin', '')}|resumed",
        "meta": {"resumed": True},
    }


def route_interaction(state: ConvState) -> str:
    """조건부 엣지: 맞장구면 턴을 끝내고, 아니면 트리아지로 보낸다.

    왜 존재하는가
        "응"에 대답하려면 백엔드 호출 한 번, LLM 호출 한 번, TTS 호출 한 번이 들고,
        아무도 듣고 싶지 않은 결과물이 나온다. 여기서 턴을 끝내는 것은 게이트가
        침묵에 쓰는 것과 같은 방법이다. 아무것도 생성하지 않는 대신 END 에 도달한다.

    누가 호출하는가
        build.py, note_interaction 다음.
    """
    return END if state.get("is_backchannel") else "safety_triage"


# ─────────────────────────────────────────────────────────────────────────────
# 문 이벤트 경로  (CLAUDE.md §11)
# ─────────────────────────────────────────────────────────────────────────────


def door_event(state: ConvState) -> dict:
    """재실 상태를 반영한다. 그리고 여기서 끝난다.

    무엇을 하는가
        문에 무슨 일이 있었다는 사실만 state 에 반영한다. 규칙은 door.occupancy 에
        있고 이 노드는 그것을 부른다 — 같은 규칙이 두 곳에 생기지 않게.

    무엇을 하지 '않는가'  ★ 2026-08-01 재정의
        **인사를 제안하지 않는다.** 배웅·환영 판정은 백엔드 몫이다 (CLAUDE.md §11).
        백엔드가 방향을 확정하고, 말할지 정하고, backend_command 경로로 내려보낸다.

        방향도 만들지 않는다. 센서 두 개는 각자 방향을 모르고, 두 신호의 순서로만
        방향이 나온다. 그 상관 판정의 시간 창은 실측값이라 튜닝 대상이고, 로봇에 두면
        조정할 때마다 로봇을 배포해야 한다.

    왜 그런데도 로봇이 occupancy 를 만지는가
        침묵 사다리가 매 틱 이 값을 읽고, 네트워크 없이도 돌아야 한다 (§10, §18).
        방향을 모르니 HOME/AWAY 는 만들 수 없다. 그래서 항상 안전한 한 가지를 한다 —
        문에 무슨 일이 있으면 UNKNOWN. 사다리는 그것을 '보수적으로 가동'으로 읽는다.

        피하려는 실패: 오프라인 로봇이 어르신을 AWAY 라고 믿고 사다리를 영원히
        멈추는 것.

    누가 호출하는가
        build.py. "door_event" 경로의 첫 노드이자 마지막 노드.
        MQTT 로 받은 것을 door.mqtt 가 넣어준다.

    반환값
        occupancy, occupancy_observed_at. 제안은 없다.

    주의사항
        - 시각은 이벤트에 실려 온 '도착 시각'을 쓴다. 라즈베리파이가 주장한 시각이
          아니다. 정규화는 contracts.door.parse_door_event 에서 이미 끝났다.
        - 여기서도 내구 저장소에 쓴다. door.intake 를 거치지 않고 그래프만 호출되는
          경로(테스트, 백엔드가 밀어준 이벤트)가 있기 때문이다. 두 번 써도 같은 값이다.
    """
    event = state.get("last_door_event") or {}
    event_type = str(event.get("type") or "")
    # 도착 시각이 없으면 지금으로 둔다. 없는 채로 0 을 쓰면 '아주 오래된 관측'이
    # 되어 door.occupancy 가 낡은 값으로 판단해 버린다.
    observed_at = float(event.get("ts") or clock.now())

    resolved = occupancy_rules.local_occupancy_for(event_type)
    if resolved is None:
        # 문이 닫혔거나 하트비트다. 재실에 대해 아무 말도 하지 않는다.
        logger.info("door event %s says nothing about occupancy", event_type or "?")
        return {}

    senior_id = state.get("senior_id")
    if senior_id:
        occupancy_rules.set_occupancy(
            senior_id, resolved, observed_at=observed_at, source="sensor"
        )

    return {"occupancy": resolved, "occupancy_observed_at": observed_at}


# ─────────────────────────────────────────────────────────────────────────────
# 백엔드 명령 경로  (CLAUDE.md §6, §11)
# ─────────────────────────────────────────────────────────────────────────────


def backend_command(state: ConvState) -> dict:
    """백엔드가 말하라고 명령했다. 게이트를 거치지 않고 파이프라인에 올린다.

    무엇을 하는가
        명령을 그래프가 이해하는 값으로 옮긴다. intent, user_input(= 말할 내용),
        speech_priority, speech_origin. 그리고 백엔드가 확정 재실 상태를 함께 보냈으면
        그것도 반영한다.

    왜 게이트를 거치지 않는가  ★
        게이트는 "지금 말해도 되는가"를 판정한다. 이 명령은 그 판정을 이미 한 쪽에서
        왔다. 여기서 다시 판정하면 심판이 둘이 되고, 그러면 백엔드가 보낸 인사가
        로봇의 쿨다운에 조용히 삼켜지는 일이 생긴다. 백엔드는 자기가 보낸 인사가
        나갔다고 기록하고, 어르신은 아무 말도 듣지 못한다.

        대신 안전 규칙은 그대로다. 이 경로도 response_shaper 를 통과하므로 §14 의
        '한 가지만, 짧게'는 지켜진다. terse 도 백엔드가 지정할 수 있다.

    왜 문구를 백엔드가 정하는가
        인사의 내용이 백엔드만 아는 사실에 달려 있다. 오늘 일정, 미복용 약, 동의 상태.
        로봇이 그것을 다시 조회해 다시 고르면 같은 우선순위 규칙이 두 곳에 생긴다
        (CLAUDE.md §11 "one judge, one place to audit").

    누가 호출하는가
        build.py. 백엔드 명령 수신부(MQTT `bomi/v1/robot/{id}/commands` 또는 HTTP)가
        trigger_type="backend_command" 로 그래프를 부른다.

    반환값
        intent, user_input, speech_priority, speech_origin, terse, occupancy(있을 때).

    주의사항
        - `command.text` 가 비어 있으면 아무것도 하지 않는다. 빈 문장을 파이프라인에
          올리면 정제기가 빈 문자열을 만들고 TTS 가 무음을 재생한다.
        - 이동 명령(target: ENTRANCE)은 이 경로와 무관하다. 음성은 방을 건너 들리므로
          느리거나 실패한 이동이 인사를 삼켜서는 안 된다 (CLAUDE.md §11).
    """
    command = state.get("command") or {}
    text = str(command.get("text") or "").strip()

    # 백엔드가 방향까지 판정해 확정 재실 상태를 실어 보냈으면 반영한다.
    # 이것이 HOME/AWAY 가 저장소에 들어오는 두 경로 중 하나다(다른 하나는 발화).
    out: dict = {}
    occupancy = command.get("occupancy")
    senior_id = state.get("senior_id")
    if occupancy and senior_id:
        observed_at = float(command.get("occupancyObservedAt") or clock.now())
        occupancy_rules.apply_backend_occupancy(
            senior_id, str(occupancy), observed_at=observed_at
        )
        out["occupancy"] = str(occupancy)
        out["occupancy_observed_at"] = observed_at

    if not text:
        logger.warning("backend command has no text; nothing to say")
        return out

    out.update({
        "intent": command.get("intent") or "greeting",
        "user_input": text,
        "speech_priority": command.get("priority") or "event",
        "speech_origin": command.get("origin") or "backend_command",
        "terse": bool(command.get("terse")),
    })
    logger.info("backend command accepted: intent=%s origin=%s",
                out["intent"], out["speech_origin"])
    return out
