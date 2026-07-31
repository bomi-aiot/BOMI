"""능동 발화 게이트 — 지금 로봇이 말해도 '되는지'를 결정한다.

어디에 위치하는가
    네 가지가 로봇에게 말하게 하고 싶어 한다.
        1. 스케줄러        (복약, 식사, 물 — 시간 기반)
        2. 침묵 사다리      (걱정스러운 시간 동안 아무 말이 없었다)
        3. 현관 센서        (누가 들어오거나 나갔다 — 인사해야 한다)
        4. 재질의 흐름      (fact_candidate 의 한 필드를 다시 물어야 한다)

    아무도 직접 말하지 않는다. 각자 SpeechProposal 을 제출하고, 이 모듈이 심판이
    되어 정확히 하나만 통과시키거나 침묵을 선택한다. 이 아래의 모든 것
    (context_read, 핸들러, response_shaper, emit)은 이미 허락이 떨어졌다고 가정한다.

왜 존재하는가
    타이머가 울릴 때마다 말하는 로봇은 잔소리꾼이 된다. 새벽 3시에 떠들고, TV 를
    끊고 들어오고, 5분 전에 한 알림을 또 한다. 혼자 사는 분에게 그것은 '말벗'과
    '전원을 뽑아버리는 가전' 사이의 차이다.

    그래서: '말하지 않기로 결정하는 것도 기능이다.' 오류 경로가 아니다.
    이 모듈이 "silent" 를 반환하면 build.py 가 턴을 곧바로 END 로 보내고 로봇은
    아무 말도 하지 않는다. 그것이 성공한 결과이며, route_gate 가 존재하는 이유다.

어떻게 여기에 도달하는가
    build.py 가 trigger_type "proactive" 와 "door_event" 를 여기로 보낸다.
    "user_utterance" 턴은 절대 오지 않는다. 어르신이 먼저 말했다면 대답할 허락을
    받을 필요가 없다.

읽는 값   proposals, last_spoke_at, audio_ctx, ctx.profile.quiet_hours
쓰는 값   gate_decision, terse, intent, user_input, speech_origin

참고
    CLAUDE.md §7 (우선순위 행렬), §11 (인사 TTL 이 왜 그렇게 짧은지)
    bomi_ai_chat/policy.py — 여기서 쓰는 모든 임계치
"""

from __future__ import annotations

from langgraph.graph import END

from bomi_ai_chat import policy
from bomi_ai_chat.clock import clock
from bomi_ai_chat.state import ConvState, SpeechProposal

# ─────────────────────────────────────────────────────────────────────────────
# 네 개의 게이트
#
# 각 함수는 정확히 하나의 질문에만 답하고 I/O 를 하지 않는다. 그래서 전체 캐스케이드가
# 매 스케줄러 틱마다 돌려도 될 만큼 값싸다.
# ─────────────────────────────────────────────────────────────────────────────


def is_still_valid(proposal: SpeechProposal, state: ConvState) -> bool:
    """게이트 1 — 이 제안이 아직 말할 가치가 있는가?

    무엇을 하는가
        서로 독립적인 두 가지 확인.
          (a) TTL:   큐에서 기다리는 동안 상해버렸는가?
          (b) 무효화: 그동안 근본 필요가 이미 충족됐는가?

    왜 존재하는가
        제안은 fire-and-forget 이 아니다. 기다리는 동안 세상이 움직인다.
        9시 복약 알림이 큐에 있는데 8시 55분에 어르신이 "약 먹었어"라고 말한다.
        스케줄 핸들러가 완료 처리하고, 이 알림은 이미 처리된 일을 잔소리하는 대신
        조용히 사라져야 한다.

    누가 호출하는가
        proactive_gate. 네 확인 중 첫 번째다. 가장 값싸고 가장 결정적이다.

    반환값
        True  -> 계속 평가한다.
        False -> 폐기(DISCARD). 아무도 재시도하지 않는다.

    주의사항
        폐기(discard)와 연기(defer)는 다른 결과이고, 폐기하는 게이트는 이것뿐이다.
          - 시간을 놓친 현관 인사는 무가치하다. 버린다.
          - quiet hours 에 막힌 복약 알림은 여전히 필요하다. 그건 연기이며
            아래 게이트들에서 일어난다.
        어떤 우선순위도 이 게이트를 무시할 수 없다. critical 조차도, 더 이상 사실이
        아닌 말을 해서 얻는 이득은 없다.
    """
    expires_at: float | None = proposal.get("expires_at")
    if expires_at is not None and clock.now() > expires_at:
        return False

    # TODO(schedule): 이 제안이 이미 충족됐는지 localstore 에 확인한다.
    #   예: 참조하는 복약 슬롯이 오늘 '복용 완료'로 표시됐는지.
    #   이게 들어오기 전까지는 이미 먹은 약을 다시 알릴 수 있다. 알려진 공백이며
    #   실수가 아니다. 완료 표시는 handlers.handle_schedule 이 한다.
    return True


def is_quiet_hours(state: ConvState) -> bool:
    """게이트 2 — 지금이 어르신의 수면 시간대인가?

    무엇을 하는가
        어르신의 '로컬' 시간을 quiet hours 창과 비교한다. 창 정보는 ctx.profile
        (app_user 에서 온 것)로 들어온다.

    왜 존재하는가
        새벽 3시의 "약 드실 시간이에요"는 돌봄 로봇의 전원을 영구히 뽑게 만드는
        가장 빠른 방법이다.

    누가 호출하는가
        proactive_gate.

    반환값
        quiet hours 안이면 True. 즉 이 게이트가 '막고 싶다'는 뜻이다.

    주의사항
        - 함정이 두 개다. 첫째, 이 창은 보통 자정을 넘어간다(22:00~07:00). 그래서
          단순한 `start <= now <= end` 비교는 하필 가장 중요한 시간대에서 틀린다.
          둘째, 이 창은 '로컬' 시간이다. clock.now() 는 UTC 이므로 app_user.time_zone
          으로 변환해야 한다. 안 하면 일부 사용자에게 몇 시간씩 어긋난다.
        - 같은 창을 침묵 사다리(jobs/ticks.py)도 쓴다. 새벽 4시의 침묵은 경고 신호가
          아니라 수면이다. 여기 의미를 바꾸면 거기도 확인해야 한다.
    """
    # TODO: ctx["profile"]["quiet_hours"] 와 ctx["profile"]["time_zone"] 을 읽고,
    #   clock.now() 를 로컬 시간으로 변환한 뒤, 자정을 넘는 창을 처리한다.
    raise NotImplementedError("quiet hours: 구현 전에 위 주의사항을 먼저 읽을 것")


def is_in_cooldown(state: ConvState) -> bool:
    """게이트 3 — 로봇이 너무 최근에 말했는가?

    무엇을 하는가
        last_spoke_at 이후 경과 시간을 policy.COOLDOWN_SEC 와 비교한다.

    왜 존재하는가
        쿨다운이 없으면 비슷한 시간에 몰린 여러 타이머가 독백을 만든다.
        물, 그다음 약, 그다음 날씨, 그다음 잡담. 그건 도움되는 로봇이 아니라
        잔소리하는 로봇이다.

    누가 호출하는가
        proactive_gate.

    반환값
        아직 쿨다운 중이면 True (이 게이트가 막고 싶다는 뜻).

    주의사항
        last_spoke_at 은 memory_write 에서 찍힌다. 텍스트 생성 후이지만 재생이
        끝나기 전일 수 있다. 충분하다. 쿨다운은 분 단위, 재생은 초 단위다.
    """
    last = state.get("last_spoke_at") or 0.0
    if last <= 0.0:
        return False  # 아직 한 번도 말한 적 없음(방금 부팅). 식힐 것이 없다.
    return (clock.now() - last) < policy.COOLDOWN_SEC


def is_busy(state: ConvState) -> bool:
    """게이트 4 — 지금 말하면 뭔가를 끊는 것인가?

    무엇을 하는가
        audio_ctx 의 값싼 로컬 VAD 신호를 읽어서, 지금 방에서 대화가 일어나고 있는지
        추측한다.

    왜 존재하는가
        전화 통화나 이웃의 방문을 끊는 것은 무례하고, 발화 자체도 낭비된다.
        아무도 듣고 있지 않았으니까.

    누가 호출하는가
        proactive_gate. 가장 신뢰도가 낮으므로 마지막이다.

    반환값
        뭔가 진행 중인 것 같으면 True (이 게이트가 막고 싶다는 뜻).

    주의사항
        이것은 근본적으로 불신뢰하며, 그것은 '수용된 사실'이지 고쳐야 할 버그가 아니다.
        오디오만으로는 TV 와 실제 대화를 구분할 수 없다. 여기서 똑똑해지려 하지 말 것.
        정책은 이렇다. 애매하면 낮은 우선순위는 미루고 critical 은 통과시킨다
        (policy.PRIORITY_POLICY). 잡담에 과하게 신중한 것은 아무 비용도 아니다.

        audio_ctx 는 로컬에서만 판정하며 녹음·저장하지 않는다. CLAUDE.md §10 의
        프라이버시 규칙 참고.
    """
    return bool(state.get("audio_ctx", {}).get("someone_speaking"))


# ─────────────────────────────────────────────────────────────────────────────
# 게이트 본체
# ─────────────────────────────────────────────────────────────────────────────


def proactive_gate(state: ConvState) -> dict:
    """제안된 발화들을 걸러서 최대 '하나'만 고른다.

    무엇을 하는가
        대기 중인 모든 제안을 네 게이트에 순서대로 통과시킨다. 살아남은 것들은
        policy.PRIORITY_RANK 로 경쟁하고 최고 하나가 이긴다. 아무도 살아남지 못하면
        로봇은 침묵한다.

    왜 이 순서인가
        가장 값싸고 결정적인 것이 먼저다. 이미 만료된 인사가 VAD 조회 비용을 쓸 이유가
        없고, 폐기할 수 있는 게이트는 유효성 하나뿐이다.

    누가 호출하는가
        build.py. 진입 라우터에서 trigger_type "proactive" 와 "door_event" 로 온다.

        문 이벤트의 경우, door_event() 가 이미 occupancy 변경을 반영한 뒤에 호출된다는
        점에 주의한다. 세상에 대한 '사실'은 게이트의 허락이 필요 없고, 인사만 필요하다
        (CLAUDE.md §11).

    무엇을 호출하는가
        is_still_valid, is_quiet_hours, is_in_cooldown, is_busy — 모두 값싸다.

    인자
        state: 여기서는 proposals, 런타임 타임스탬프, audio_ctx 만 의미가 있다.

    반환값
        {"gate_decision": "silent"}
            build.py 가 END 로 보낸다. 로봇은 아무 말도 하지 않는다. 이것이 성공이다.
        {"gate_decision": "speak", "intent", "user_input", "terse", "speech_origin"}
            build.py 가 context_read 와 핸들러로 진행한다.

    주의사항
        - 이긴 제안의 intent 를 반환한다. 그래서 능동 턴에서는 classify_intent 가
          아무 일도 하지 않는다. 제안한 쪽이 이미 어떤 종류의 발화인지 알고 있다.
        - 진 생존자들은 여기서 버려진다. 원래는 재큐해야 한다(아래 TODO). 없으면
          복약 알림에 밀린 수분 권유가 영구히 사라진다.
        - 이 함수에 우선순위 예외를 추가하지 않는다. policy.py 의 표를 고친다.
          로직과 정책이 섞이는 순간 아무도 동작을 예측할 수 없게 된다.
    """
    survivors: list[SpeechProposal] = []

    # terse 는 개별 제안의 속성이 아니라 '출력'의 속성이다. 밤에 우리가 말하는
    # 유일한 이유가 인사라면, 발화 전체가 짧아야 한다. 그래서 제안별로 저장하지 않고
    # 루프 전체에 걸쳐 누적한다.
    terse = False

    quiet = is_quiet_hours(state)
    busy = is_busy(state)
    cooling = is_in_cooldown(state)

    for proposal in state.get("proposals", []):
        bypass = policy.PRIORITY_POLICY[proposal["priority"]]

        # ── 게이트 1: 유효성 ─────────────────────────────────────────────────
        if not is_still_valid(proposal, state):
            continue  # 폐기 — 재시도하지 않는다

        # ── 게이트 2: quiet hours ────────────────────────────────────────────
        if quiet and "quiet_hours" not in bypass:
            if proposal["priority"] not in policy.QUIET_TERSE:
                continue  # 연기 — 여전히 필요하지만, 새벽 3시는 아니다
            # 제3의 결과: 말하되 짧게. 이유는 policy.QUIET_TERSE 참고.
            terse = True

        # ── 게이트 3: 쿨다운 ─────────────────────────────────────────────────
        if cooling and "cooldown" not in bypass:
            continue  # 연기

        # ── 게이트 4: 끼어들기 ───────────────────────────────────────────────
        if busy and "interruption" not in bypass:
            continue  # 대기 — 다음 틱에 다시 시도

        survivors.append(proposal)

    # 침묵. 정상적이고 건강한 결과다. 모듈 docstring 참고.
    if not survivors:
        return {"gate_decision": "silent"}

    # 한 턴에 정확히 하나의 발화. response_shaper 가 문장 수에 적용하는 것과 같은
    # 규칙이다(CLAUDE.md §14). 음성은 훑어 읽을 수 없으므로, 두 가지를 한 번에 말하면
    # 듣는 사람은 둘 다 기억하지 못한다.
    winner = max(survivors, key=lambda p: policy.PRIORITY_RANK[p["priority"]])

    # TODO(queue): 진 생존자들을 버리지 말고 재큐한다.
    #   게이트 1이 되돌아올 때 중복을 걸러주므로 재큐는 안전하다.

    return {
        "gate_decision": "speak",
        "terse": terse,
        "intent": winner["intent"],
        # 핸들러는 이것을 출발점으로 다루며, 최종 문구가 아니다.
        "user_input": winner.get("seed", ""),
        # 사후에 "왜 로봇이 새벽 3시에 말했는가"에 답할 수 있게 남긴다.
        "speech_origin": winner.get("origin", "unknown"),
    }


def route_gate(state: ConvState) -> str:
    """조건부 엣지: 게이트 다음에 턴은 어디로 가는가?

    무엇을 하는가
        gate_decision 을 다음 노드 이름으로 변환한다.

    왜 존재하는가
        이 짧은 함수가 '침묵도 기능'을 LangGraph 로 표현하는 방식이다.
        조건부 엣지는 END 센티넬을 반환할 수 있으므로, 말하지 않기로 하는 것은
        말 그대로 emit 에 도달하기 전에 그래프를 끝내는 엣지가 된다. 나중에 억제할
        빈 응답도 없고, 반쯤 만들어진 발화가 굴러다니지도 않는다.

    누가 호출하는가
        build.py:  g.add_conditional_edges("proactive_gate", route_gate, {...})

    반환값
        "context_read" -> 응답 파이프라인으로 진행
        END            -> 여기서 종료. 로봇은 조용히 있는다.
    """
    return "context_read" if state.get("gate_decision") == "speak" else END
