"""턴이 시작될 수 있는 세 가지 경로, 그리고 그 사이의 라우팅.

어디에 위치하는가
    그래프의 맨 위. CLAUDE.md §6 에서 게이트나 트리아지보다 먼저 일어나는 모든 것이
    여기 있다.

    세 개의 진입 경로이며, 일부러 '대칭이 아니다'.

      "user_utterance"  -> note_interaction -> safety_triage
            어르신이 말했다. 방금 우리에게 말을 건 사람에게 대답할 허락을 게이트에
            구하지 않는다.

      "proactive"       -> proactive_gate
            스케줄러나 침묵 사다리가 제안했다. 허락을 받아야 한다.

      "door_event"      -> door_event -> proactive_gate
            센서가 발동했다. occupancy '변경'은 세상에 대한 사실이므로 즉시 반영하고,
            인사만 허락을 구한다.

왜 note_interaction 이 독립 노드인가
    어르신이 말하면, 다른 무엇보다 먼저 서로 무관한 네 가지가 일어나야 한다.
    시계 리셋, 침묵 사다리 리셋, occupancy 정정, barge-in 처리. 넷 중 어느 것도
    안전 분류가 아니다. 이걸 safety_triage 안에 넣으면 그 노드가 두 가지 일을 하게
    되고 둘 다 테스트하기 어려워진다.

읽는 값   trigger_type, user_input, speaking, occupancy, last_door_event
쓰는 값   last_user_interaction_at, silence_level, occupancy, speaking,
          interrupted_remainder, is_backchannel, proposals

참고
    CLAUDE.md §6 (아키텍처), §11 (현관 센서), §13 (barge-in)
"""

from __future__ import annotations

import logging

from langgraph.graph import END

from bomi_ai_chat import policy
from bomi_ai_chat.clock import clock
from bomi_ai_chat.graph import output
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
        "note_interaction", "proactive_gate", "door_event" 중 하나.

    주의사항
        여기서 KeyError 가 나면 누군가 trigger_type 없이 그래프를 호출했다는 뜻이다.
        요란하게 실패하는 것이 의도다. 조용히 한쪽 경로로 기본값을 주면 능동 턴이
        게이트를 건너뛰게 되는데, 그것은 절대 일어나서는 안 되는 유일한 일이다.
    """
    return {
        "user_utterance": "note_interaction",
        "proactive": "proactive_gate",
        "door_event": "door_event",
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
    """
    out: dict = {
        "last_user_interaction_at": clock.now(),
        "silence_level": 0,
        "occupancy": "HOME",
        "occupancy_observed_at": clock.now(),
        "is_backchannel": False,
    }

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
    """occupancy 를 반영하고, 이동을 지시하고, 인사를 제안한다.

    무엇을 하는가
        하나의 이벤트, 서로 분리된 두 효과.
          (a) occupancy 전환 — 지금 여기서 반영하며 게이트를 거치지 않는다.
              발화가 아니라 사실이기 때문이다.
          (b) 아주 짧은 TTL 을 가진 인사 제안 — 이것은 다른 발화와 똑같이 게이트를
              통과해야 한다.
        아울러 현관으로 이동하라는 명령을 내고 원본 이벤트를 기록한다.

    왜 두 효과를 분리하는가
        인사가 억제되더라도(quiet hours, 누군가 말하는 중, TTL 만료) 로봇은 어르신이
        나갔다는 사실을 '알아야' 한다. occupancy 를 게이트에 통과시키면, 억제된 인사가
        안전 상태를 조용히 오염시킨다. 이 설계가 피하려는 바로 그 종류의 조용한 실패다.

    누가 호출하는가
        build.py. "door_event" 경로의 첫 노드. MQTT 로 받은 것을 door/ 가 넣어준다.

    반환값
        occupancy, occupancy_observed_at, silence_level, proposals.

    주의사항
        - 타임스탬프를 clock.now() 로 정규화한다. 현관 라즈베리파이에는 배터리 백업
          RTC 가 없을 수 있어서 전원을 껐다 켜면 시계가 틀릴 수 있고, 틀린 문 이벤트
          시각은 루틴 베이스라인 학습과 TTL 계산을 함께 오염시킨다. 압축 시계 시연의
          일관성도 이 정규화에 달려 있다 (CLAUDE.md §11, §15).
        - 센서는 '방향'을 알고 '신원'은 모른다. 어르신이 부재중일 때 방문자가 들어오면
          귀가로 읽힌다. 이 상태를 좋은 증거로 다루되 증명으로 다루지 않고, 발화가
          덮어쓸 수 있게 한다.
        - 이동이 인사를 막아서는 안 된다. 음성은 방을 건너 들리므로, 느리거나 실패한
          이동이 발화를 삼켜서는 안 된다.
    """
    event = state["last_door_event"]
    direction = event["direction"]          # "in" | "out"
    now = clock.now()                       # 권위 있는 시각. 위 주의사항 참고

    leaving = direction == "out"

    # (b) 이동. 즉시, 그리고 발화와 독립적으로 발행한다.
    # TODO(robot): move_to_door() — 논블로킹이며, 실패가 여기서 예외를 던지면 안 된다.

    # (c) 인사 제안.
    #
    # priority "event": 쿨다운을 무시한다(방금 말했다? 누군가 문을 통과했고, 그게
    # 우리 마지막 문장보다 우선한다). 대신 quiet hours 는 "terse" 로 존중해서,
    # 새벽 2시 귀가에도 짧고 조용한 한마디가 나간다 (policy.QUIET_TERSE).
    proposal: SpeechProposal = {
        "intent": "greeting",
        "priority": "event",
        # 문구는 핸들러가 정한다. "escort" 는 날씨·미복용 약·오늘 일정을 끌어와
        # 가장 중요한 '하나'만 말하고, "welcome" 은 수분·안부·장시간 외출 후 휴식을 권한다.
        "seed": "escort" if leaving else "welcome",
        "expires_at": now + policy.GREETING_TTL_SEC,
        "origin": f"door:{direction}",
        "meta": {"direction": direction},
    }

    # TODO(localstore): occupancy_event 원장에 이 이벤트를 추가한다. 루틴 베이스라인
    #   (jobs/ticks.py)과 보호자에게 T2 로 가는 외출 빈도 추세의 입력이 된다.
    #   이것은 원본 '사실'이고, 백엔드의 `scenario` 는 인사 '실행'을 기록하는 다른 것이다.

    return {
        "occupancy": "AWAY" if leaving else "HOME",
        "occupancy_observed_at": now,
        # 귀가는 새로운 생존 증거이므로 사다리를 리셋한다. 외출은 안녕함의 증거가
        # 아니므로 레벨을 건드리지 않는다. occupancy 가 AWAY 라서 사다리는 알아서 멈춘다.
        "silence_level": 0 if not leaving else state.get("silence_level", 0),
        "proposals": [proposal],
    }
