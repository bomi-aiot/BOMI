"""백그라운드 루프 — 로봇을 '능동적'으로 만드는 코드.

어디에 위치하는가
    그래프 밖. LangGraph 는 요청-응답이므로 누군가 깨워줘야 한다.
    이 함수들이 APScheduler 가 호출하는 것이고, 로봇이 먼저 말하는 유일한 이유다.

    여기 사는 루프들.
        silence_tick      -- 침묵 사다리를 올리고, 끝에서 T1 으로 에스컬레이션
        door_watch_tick   -- 현관 로그만이 볼 수 있는 패턴
        outbox_flush      -- 큐에 쌓인 보호자 알림 재시도
        schedule_tick     -- 때가 된 일상 권유를 제안으로 큐잉
        contract_tick     -- 온보딩·재질의를 제안으로 큐잉
        consent_tick      -- 누적된 정서 신호로 T3 동의 질문을 큐잉 (S15P11E102-253)
        extraction_flush  -- 큐에 쌓인 발화에서 사실을 뽑아 백엔드에 제출 (S15P11E102-255)
        daily_summary_job -- T2 일간 요약

왜 노드가 아닌가
    노드는 '턴이 시작되었기 때문에' 실행된다. 이 함수들은 '시간이 흘렀기 때문에'
    실행된다. 정반대의 트리거다. 그래프 밖에 두면 그래프는 "이 입력이 주어졌을 때
    무엇을 말할까"라는 순수 함수로 남고, 단독으로 테스트할 수 있다.

테스트에 관한 중요한 메모
    APScheduler 는 '실제' 시간에 발동하므로, 압축된 SimClock 은 이 함수들을 빠르게
    돌려주지 않는다. 테스트와 시연은 시계를 전진시키면서 이 함수들을 직접 호출해야
    한다. 그 경로를 스케줄러와 '동시에' 만들어야 하고, 나중에 만들면 안 된다
    (CLAUDE.md §15, §18).

참고
    CLAUDE.md §10 (침묵 사다리), §11 (현관 신호), §18 (오프라인과 배터리)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# 임계치는 policy 에서 읽고(함수에 박지 않는다), 시간은 clock 으로만 읽는다(§15).
from bomi_ai_chat import policy
from bomi_ai_chat.backend_client.contract_client import BackendUnavailable
from bomi_ai_chat.clock import clock
from bomi_ai_chat.door import occupancy as occupancy_rules
from bomi_ai_chat.graph import gate
from bomi_ai_chat.localstore import (
    audio_cache,
    context_cache,
    emotion,
    extraction,
    outbox,
    proposals,
)
from bomi_ai_chat.localstore import consent as consent_store
from bomi_ai_chat.localstore import runtime as runtime_store
from bomi_ai_chat.notify import GuardianNotifier, LoggingGuardianNotifier
from bomi_ai_chat.state import ConvState

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 침묵 사다리
# ─────────────────────────────────────────────────────────────────────────────


def _is_absence_expected(runtime: ConvState) -> bool:
    """지금 이 사람에게 이 침묵은 정상인가?

    무엇을 하는가
        침묵이 특별할 것 없는 네 가지 이유를 확인한다.
          1. occupancy == AWAY        -- 나가 있다
          2. rest_state == RESTING    -- 자거나 쉬는 중이다
          3. quiet hours 안           -- 밤이다
          4. 루틴 베이스라인과 일치    -- 예: 매주 화요일 오후는 원래 조용하다

    왜 이 파일에서 가장 중요한 함수인가
        1차 오탐 필터다. 이게 없으면 모든 낮잠과 모든 장보기가 사다리를 올라가고,
        보호자는 끊임없이 알림을 받고, 일주일 안에 알림을 읽지 않게 된다. 그 시점부터
        진짜 응급은 눈에 띄지 않는다. 즉 시끄러운 감지기는 단순히 짜증나는 것이 아니라
        '안전 실패'다 (CLAUDE.md §10).

    누가 호출하는가
        silence_tick. 다른 무엇보다 먼저.

    반환값
        True -> 이번 틱에서는 아무것도 하지 않는다.

    주의사항
        - 우리가 원하는 트리거는 "N시간 조용함"이 아니라 "이 사람이 조용할 리 없는
          때에 조용함"이다. 그러려면 루틴 베이스라인이 필요하고, 따라서 이 함수는
          그것을 먹여주는 이벤트 로그만큼만 좋다.
        - RESTING 은 사다리를 멈추는 것이 아니라 늦춰야 한다. 쉬다가 쓰러질 수도 있다.
          True 를 그냥 반환하지 말고 policy.RESTING_PATIENCE_MULTIPLIER 를 쓴다.
        - UNKNOWN occupancy 는 '예상된 부재가 아니다'. 보수적으로 사다리를 돌린다.
          죽은 현관 노드 때문에 생긴 UNKNOWN 이 안전 감시를 조용히 껐다는 결과가
          되어서는 안 된다.
    """
    occupancy = runtime.get("occupancy")

    # 1. 나가 있다. 사다리를 '정지'한다.
    #    집에 없는 사람이 대답하지 않는 것은 아무 정보도 아니다.
    if occupancy == "AWAY":
        return True

    # ★ UNKNOWN 은 여기서 True 가 되면 안 된다.
    #
    #   현관 노드가 죽으면 occupancy 가 UNKNOWN 으로 강등된다. 그때 이 함수가
    #   "예상된 부재"라고 답하면, 라즈베리파이 하나가 죽은 것만으로 안전 감시가
    #   통째로 꺼진다. 그리고 아무도 그 사실을 모른다.
    #
    #   그래서 UNKNOWN 은 명시적으로 통과시킨다. 아래 검사들만 적용받는다.
    #   CLAUDE.md §10 의 해석표에서 UNKNOWN 이 '보수적 가동'인 이유다.

    # 2. 밤이다. 새벽 4시의 침묵은 경고 신호가 아니라 수면이다.
    #    게이트와 '같은' 창을 쓴다. 두 곳이 어긋나면 로봇이 조용해야 할 때
    #    프로브를 던지거나, 반대로 낮에 감시를 쉰다.
    if gate.is_quiet_hours(runtime):
        return True

    # 3. 루틴 베이스라인.
    #    "N시간 조용함"이 아니라 "이 사람이 조용할 리 없는 때에 조용함"이 우리가
    #    원하는 트리거다. 그러려면 이 어르신의 평소 리듬을 알아야 한다.
    #
    #    ★ 아직 구현되지 않았다. 이벤트 로그(occupancy_event, conversation_message)가
    #      며칠 쌓여야 의미가 생기고, 그 축적이 아직 없다. 지금은 이 필터가 없는
    #      상태로 동작하며, 그만큼 오탐이 많다.
    #      → docs/carebot/PROGRESS.md 에 기록

    # 4. RESTING 은 '정지'가 아니라 '늦춤'이다.
    #
    #    쉬는 중의 침묵은 정상이지만, 쉬다가 쓰러질 수도 있다. 그래서 True 를
    #    돌려주지 않고, 임계치에 인내심 배수를 곱하는 방식으로 늦춘다.
    #    그 계산은 _rung_for 가 한다.
    return False


def silence_tick(senior_id: str, app) -> None:
    """침묵 사다리를 한 칸 올리거나, 아무것도 하지 않는다.

    무엇을 하는가
        침묵이 예상 밖이고 충분히 길면 다음 프로브를 제안한다. 단계는 이렇다.
            1  low       "점심 드셨어요?"        가볍고, 말벗처럼 들린다
            2  high      "어르신, 괜찮으세요?"   직접적이다
            3  critical  마지막 기회, 모든 게이트를 뚫는다
        3단계에도 응답이 없으면 safety_level 을 미리 세팅한 채 그래프를 호출해
        T1 으로 에스컬레이션한다. 분류할 발화가 없기 때문이다. 발화의 '부재'가 신호다.

    왜 세지 않고 프로브하는가
        수동적인 침묵은 영원히 애매하다. 자는 것, 나간 것, 의식이 없는 것이 전부
        똑같이 보인다. 질문을 하면 그것이 깔끔한 이진값으로 바뀐다. 응답했는가,
        안 했는가. 그래서 이 사다리는 침묵을 '재지' 않고 '테스트'한다 (CLAUDE.md §10).

    누가 호출하는가
        APScheduler 가 policy.SILENCE_TICK_INTERVAL_SEC 마다. 그리고 테스트가 직접.

    무엇을 호출하는가
        _is_absence_expected. 그리고 trigger_type "proactive" 로 app.invoke.

    주의사항
        - 프로브 1은 감시가 아니라 말벗처럼 들려야 한다. "점심 드셨어요?"는 안부이면서
          동시에 생존 확인이고, 그 이중 목적이 이 설계를 함께 살 만한 것으로 만든다.
        - 프로브도 게이트를 거친다. 1단계와 2단계는 정당하게 연기될 수 있다(누가
          말하는 중). 3단계만 강제로 뚫는다.
        - 에스컬레이션은 하나의 임계치가 아니라 여러 약한 신호에 대한 신뢰도 점수다.
          베이스라인 편차, 실패한 프로브 수, 주변 소리, 시간대, occupancy, rest_state.
        - 어르신이 프로브에 끼어들면 그것이 곧 답이다. 사다리를 리셋하고 프로브를
          재개하지 않는다 (CLAUDE.md §13).
    """
    state = runtime_store.load(senior_id)
    # quiet hours 판정은 어르신의 프로필(시간대·수면 창)을 본다. 게이트와 같은 값을
    # 써야 하므로 캐시된 문맥에서 가져온다. 없으면 창이 없는 것으로 취급된다.
    state["ctx"] = context_cache.load(senior_id) or {}

    # ★ 안전 확인이 먼저다. 다른 무엇보다도.
    #
    #   "가슴이 아파" 뒤의 침묵은 예상된 부재가 아니다. quiet hours 든 RESTING 이든
    #   상관없다 — 아래 _is_absence_expected 를 먼저 태우면, 증상을 말한 어르신이
    #   밤이라는 이유로 조용히 걸러진다.
    if _escalate_unanswered_safety_check(senior_id, state):
        return

    if _is_absence_expected(state):
        return

    last_interaction = state.get("last_user_interaction_at") or 0.0
    if last_interaction <= 0.0:
        # 상호작용 기록이 없다. 방금 부팅했거나 처음 만난 어르신이다.
        # 여기서 사다리를 돌리면 켜자마자 "괜찮으세요?"를 묻는다.
        return

    elapsed = clock.now() - last_interaction
    reached = _rung_for(elapsed, state.get("rest_state"))
    current = int(state.get("silence_level") or 0)

    if reached <= current:
        # 아직 다음 칸에 도달하지 않았다. 같은 칸에서 프로브를 반복하지 않는다.
        return

    # ★ 한 틱에 한 칸만 올라간다.
    #
    #   경과 시간만 보고 도달한 칸으로 바로 점프하면 프로브를 건너뛴다. 사다리
    #   2칸과 3칸의 간격이 20분뿐이라, 틱이 조금만 밀려도(절전, 재부팅, 스케줄러
    #   coalesce) 3칸을 통째로 지나쳐 곧바로 T1 이 나간다.
    #
    #   3칸은 '마지막 기회'다. 모든 게이트를 뚫고 물어보는 그 한 번이 오탐과
    #   진짜 응급을 가른다. 그것을 건너뛰면 보호자에게 갈 필요 없던 알림이 간다.
    #   오탐이 쌓이면 보호자가 알림을 읽지 않게 되고, 그때부터 진짜를 놓친다.
    level = current + 1

    runtime_store.save(senior_id, silence_level=level)

    if level >= len(policy.SILENCE_LADDER_SEC) + 1:
        _escalate_no_response(senior_id, elapsed, state)
        return

    _send_probe(senior_id, level, elapsed, app)


# 각 칸의 프로브. 문구는 seed 이고 최종 문장이 아니다 — 핸들러가 다시 쓴다.
#
# 1단계가 "점심 드셨어요?"인 것이 중요하다. 감시가 아니라 말벗처럼 들려야 하고,
# 그 이중 목적이 이 설계를 함께 살 만한 것으로 만든다 (CLAUDE.md §10).
_PROBES: dict[int, tuple[str, str, str]] = {
    1: ("low", "점심 드셨어요?", "probe.low.1"),
    2: ("high", "어르신, 괜찮으세요?", "probe.high.1"),
    3: ("critical", "어르신, 대답 좀 해주세요.", "probe.critical.1"),
}


def _rung_for(elapsed: float, rest_state: object) -> int:
    """경과 시간이 사다리의 몇 번째 칸인가. 0 이면 아직 아무것도 안 한다.

    RESTING 이면 임계치에 인내심 배수를 곱한다.
        쉬는 중의 침묵은 정상이다. 사다리를 완전히 멈추고 싶지는 않지만(쉬다가
        쓰러질 수도 있다) 훨씬 인내심 있게 동작해야 한다.

    반환값
        0            아직 이르다
        1, 2, 3      해당 프로브
        4            사다리 소진 -> T1
    """
    patience = (
        policy.RESTING_PATIENCE_MULTIPLIER if rest_state == "RESTING" else 1.0
    )

    # 사다리는 '누적' 시간이다. 3시간 -> 다시 45분 -> 다시 20분.
    threshold = 0.0
    for index, step in enumerate(policy.SILENCE_LADDER_SEC, start=1):
        threshold += step * patience
        if elapsed < threshold:
            return index - 1
    return len(policy.SILENCE_LADDER_SEC) + 1


def _escalate_unanswered_safety_check(senior_id: str, state: ConvState) -> bool:
    """확인 질문에 답이 없는 채로 마감이 지났는가. 지났으면 보호자를 부른다.

    ★ 왜 이 검사가 필요한가
        트리아지는 증상 표현을 들으면 확인 질문 하나를 던진다("많이 불편하세요?").
        어르신이 답하면 다음 턴에서 판정된다. **답하지 않으면 그 턴이 오지 않는다.**

        그래서 그래프 밖에서 마감을 봐야 한다. 이 검사가 없으면 "가슴이 아파"라고
        말하고 쓰러진 어르신이 확인 질문만 받고 잊힌다 — 이 시스템이 막으려는
        바로 그 실패다.

    왜 침묵 사다리보다 앞인가
        사다리는 예상된 부재(밤, 외출, 휴식)를 걸러낸다. 증상을 말한 뒤의 침묵에는
        그 필터를 적용하면 안 된다. 새벽 3시에 "숨이 안 쉬어져"라고 말한 뒤의 침묵은
        수면이 아니다.

    반환값
        True  -> 에스컬레이션했다. 호출부는 이번 틱을 여기서 끝낸다.
        False -> 대기 중인 확인이 없거나 아직 마감 전이다.
    """
    deadline = float(state.get("safety_check_until") or 0.0)
    if deadline <= 0.0:
        return False

    if clock.now() < deadline:
        return False

    runtime_store.save(senior_id, safety_check_until=0.0)
    outbox.enqueue("T1", {
        "reason": "emergency",
        # 어떻게 여기까지 왔는지를 남긴다. 보호자 화면과 사후 튜닝이 함께 본다.
        "confirmed_by": "no_reply_to_safety_check",
        "occupancy": state.get("occupancy"),
        "rest_state": state.get("rest_state"),
        "ts": clock.now(),
    })
    logger.warning(
        "the senior did not answer the safety confirmation within %.0fs; T1 queued",
        policy.SAFETY_CONFIRMATION_TIMEOUT_SEC)
    return True


def _send_probe(senior_id: str, level: int, elapsed: float, app) -> None:
    """프로브를 '제안'한다. 직접 말하지 않는다.

    1·2 단계는 정당하게 연기될 수 있다(누가 말하는 중, quiet hours). 3단계는
    priority critical 이라 policy.PRIORITY_POLICY 에 의해 모든 게이트를 뚫는다.
    그 예외는 여기 코드가 아니라 표에 적혀 있다.
    """
    priority, seed, cache_key = _PROBES[level]

    if level == 3:
        # critical 프로브는 미리 만들어둔 로컬 오디오를 우선한다.
        # 네트워크 없이 동작해야 하고, 그게 바로 이 프로브가 가장 중요한 상황이다
        # (CLAUDE.md §18). 없으면 평소대로 합성하지만, 없다는 사실을 남긴다.
        if audio_cache.lookup(cache_key) is None:
            logger.warning(
                "critical probe has no cached audio (%s); it will need the network "
                "at exactly the moment the network may be gone", cache_key)

    logger.info(
        "silence ladder rung %d for %s after %.0fs of silence", level, senior_id, elapsed)

    _invoke_proactive(app, senior_id, {
        "trigger_type": "proactive",
        "senior_id": senior_id,
        "proposals": [{
            "intent": "companion",
            "priority": priority,
            "seed": seed,
            "origin": f"silence_ladder:{level}",
            "meta": {"probe_level": level, "cache_key": cache_key},
        }],
    })


def _escalate_no_response(senior_id: str, elapsed: float, state: ConvState) -> None:
    """사다리를 다 올라갔는데도 응답이 없다. 보호자를 부른다.

    무엇을 하는가
        outbox 에 T1 을 적재한다. 전송은 outbox_flush 가 맡는다 — 여기서 직접
        보내면 네트워크가 끊긴 순간 그 알림이 사라지는데, 하필 그 순간이 알림이
        가장 중요한 순간이다 (CLAUDE.md §18).

    왜 신뢰도 점수를 함께 담는가
        에스컬레이션 판정은 단일 임계치가 아니라 여러 약한 신호의 조합이어야 한다
        (CLAUDE.md §10). 아직 점수를 '계산해서 문턱을 넘기는' 단계는 아니지만,
        판단 근거가 되는 신호들을 알림에 실어서 보호자와 사후 튜닝이 볼 수 있게 한다.

    주의사항
        T1 은 guardian_sharing_consent_status 와 무관하게 나간다. 생명 안전이다.
        그 대신 보호자가 1초에 무시할 수 있는 형태여야 한다 — 119 직통이 아니다.
    """
    payload = {
        "reason": "no_response",
        "silence_sec": round(elapsed),
        "probes_failed": len(policy.SILENCE_LADDER_SEC),
        # 약한 신호들. 보호자 화면과 사후 튜닝이 함께 본다.
        "occupancy": state.get("occupancy"),
        "rest_state": state.get("rest_state"),
        "ambient_sound": bool((state.get("audio_ctx") or {}).get("ambient_sound")),
    }
    outbox.enqueue("T1", payload)
    logger.warning(
        "silence ladder exhausted for %s after %.0fs; T1 queued", senior_id, elapsed)


def _invoke_proactive(app, senior_id: str, inputs: dict) -> None:
    """그래프를 능동 경로로 호출한다. 실패해도 틱을 죽이지 않는다.

    app 이 없으면(스케줄러만 돌리는 구성, 테스트) 제안을 큐에 넣어두기만 한다.
    다음 능동 턴에서 게이트가 집어간다.
    """
    if app is None:
        for proposal in inputs.get("proposals", []):
            proposals.enqueue(senior_id, proposal)
        return

    try:
        app.invoke(inputs, {"configurable": {"thread_id": senior_id}})
    except Exception:  # noqa: BLE001 - 틱이 죽으면 그 감시가 영원히 멈춘다
        logger.exception("proactive invoke failed for %s", senior_id)


# ─────────────────────────────────────────────────────────────────────────────
# 현관 감시
# ─────────────────────────────────────────────────────────────────────────────


def door_watch_tick(senior_id: str, app) -> None:
    """침묵 사다리가 구조적으로 볼 수 없는 위험 패턴.

    무엇을 하는가
        occupancy 로그에 대한 네 가지 확인과 한 가지 헬스 체크.
          1. 장시간 미귀가       -> T2, 계속되면 T1.
          2. 야간 외출           -> T2, 반복되면 T1.
          3. 문이 열린 채 방치    -> T2.
          4. 외출 빈도 급감       -> T2 추세.
          5. 하트비트 없음        -> occupancy 를 UNKNOWN 으로 강등.

    왜 별도의 루프인가
        사다리는 '집에서의 침묵'만 볼 수 있다. 이 중 두 개는 구조적으로 사다리에게
        보이지 않는다.
          - 미귀가: 집에 아무도 없으니 사다리가 아예 시작되지 않는다.
          - 배회: 새벽 외출은 침묵이 아니라 '활동'이다.
        야간 배회는 치매의 대표 증상이므로, 인지 축이 객관적 신호를 얻는 곳이 이
        루프다 (CLAUDE.md §11).

    누가 호출하는가
        APScheduler. silence_tick 과 같은 주기.

    주의사항
        - 5번은 선택 사항이 아니다. 하트비트가 없으면 "아무도 움직이지 않았다"와
          "라즈베리파이가 죽었다"를 구분할 수 없고, 낡은 occupancy 값을 신뢰하는 것은
          사다리의 가장 유용한 입력을 조용히 무력화한다.
        - 보호자에게는 '집계'를 보낸다. 이동 피드가 아니다. 매일 "14:03 외출, 15:20
          귀가"는 감시이고, "오늘 유난히 오래 나가 계셨어요"는 돌봄이다
          (CLAUDE.md §11).
        - 외출 빈도는 발화량과 함께 우리의 두 번째 활동 지표다. 급감은 우울과 건강
          신호이며, 추세이므로 절대 T1 으로 올리지 않는다.

    ★ 4번(외출 빈도 급감)은 여기서 하지 않는다  (2026-08-01 재정의)
        추세에는 이력이 필요하고, 이력은 `occupancy_event`(백엔드)에 있다. 로봇이 몇 주치
        이동 기록을 들고 있을 이유가 없다 (CLAUDE.md §11, S15P11E102-211).

        나머지 넷이 로봇에 남는 이유는 하나다. **네트워크 없이도 감지해야 하는 것은
        로봇에 남는다.** 나가서 안 돌아온 어르신은 네트워크도 함께 끊겼을 수 있는
        바로 그 경우다. 추세는 기다릴 수 있다.

    ★ 미귀가·야간 배회는 백엔드가 AWAY 를 확정해 준 뒤에만 감지된다
        로봇은 방향을 판정하지 않으므로 스스로 AWAY 를 만들지 못한다(door/occupancy.py).
        외출 순간에 네트워크가 끊겨 있으면 occupancy 는 UNKNOWN 에 머물고, 이 틱은
        미귀가를 알 수 없다. 대신 **오탐도 내지 않는다.**

        일단 AWAY 가 확정되면 그 뒤로는 네트워크 없이 계속 센다. 그게 이 검사를 로봇에
        남긴 이유다.
    """
    state = runtime_store.load(senior_id)
    # quiet hours 판정에 어르신 프로필이 필요하다. 게이트·침묵 틱과 같은 값을 쓴다.
    state["ctx"] = context_cache.load(senior_id) or {}
    now = clock.now()

    _check_heartbeat(senior_id, state, now)
    _check_door_left_open(senior_id, state, now)
    _check_absence(senior_id, state, now)


def _check_heartbeat(senior_id: str, state: ConvState, now: float) -> None:
    """현관 노드가 살아 있는가. 죽었으면 occupancy 를 UNKNOWN 으로 내린다.

    왜 선택 사항이 아닌가
        하트비트가 없으면 "아무도 움직이지 않았다"와 "라즈베리파이가 죽었다"를 구분할
        수 없다. 낡은 AWAY 를 그대로 믿으면 침묵 사다리가 정지한 채로 남고, 아무도
        그 사실을 모른다. 안전 시스템에서 그게 가장 나쁜 실패다 (CLAUDE.md §11).

    왜 보호자에게도 알리는가
        강등만 하고 조용히 있으면 '조용한 실패'를 UNKNOWN 이라는 이름으로 바꿔 부른
        것에 지나지 않는다. 현관 감시가 꺼졌다는 사실은 누군가 조치할 수 있어야 한다.
        기기 문제이므로 T2 이고, 어르신의 상태가 아니다.

    주의사항
        door_heartbeat_at 이 0 이면 아무것도 하지 않는다. "아직 한 번도 못 받았다"와
        "설치되지 않았다"를 구분할 수 없기 때문이다. 개발 노트북에서 매 분 알림이
        쌓이는 것을 막는다. 대신 프로세스당 한 번 경고를 남긴다.
    """
    last_beat = float(state.get("door_heartbeat_at") or 0.0)
    if last_beat <= 0.0:
        _warn_door_node_never_seen()
        return

    silent_for = now - last_beat
    if silent_for < policy.DOOR_HEARTBEAT_TIMEOUT_SEC:
        return

    if state.get("occupancy") != "UNKNOWN":
        occupancy_rules.set_occupancy(
            senior_id, "UNKNOWN", observed_at=now, source="heartbeat"
        )

    if runtime_store.mark_door_alert(senior_id, f"heartbeat_lost:{int(last_beat)}"):
        outbox.enqueue("T2", {
            "reason": "door_node_offline",
            "silent_sec": round(silent_for),
            "note": "occupancy degraded to UNKNOWN",
        })
        logger.warning(
            "door node silent for %.0fs; occupancy degraded to UNKNOWN and T2 queued",
            silent_for)


_door_node_warning_emitted = False


def _warn_door_node_never_seen() -> None:
    """현관 노드에서 한 번도 소식이 없다. 프로세스당 한 번만 경고한다.

    왜 경고가 필요한가
        이 상태에서 로봇은 정상처럼 보이지만 안전 신호 하나가 아예 없다. occupancy 는
        영원히 UNKNOWN 이고, 미귀가와 야간 배회는 원리적으로 감지되지 않는다.
        조용히 도는 것이 가장 위험하다.
    """
    global _door_node_warning_emitted
    if _door_node_warning_emitted:
        return
    _door_node_warning_emitted = True
    logger.warning(
        "no heartbeat has ever arrived from the door node; occupancy will stay UNKNOWN "
        "and the door watch cannot detect a missing return or night wandering. "
        "Check MQTT_ENABLED and the Raspberry Pi.")


def _check_door_left_open(senior_id: str, state: ConvState, now: float) -> None:
    """문이 오래 열려 있는가.

    ★ 이것이 로봇이 방향 없이 혼자 판정할 수 있는 유일한 현관 신호다.
        접점 센서는 열림/닫힘을 직접 보고한다. 누가 어느 쪽으로 지나갔는지 몰라도
        "열린 채로 20분"은 그 자체로 사실이다. 그래서 백엔드가 없어도, 방향을 몰라도,
        이 검사는 정확하다 (CLAUDE.md §11).

    왜 T2 인가
        안전·보안 문제이면서 인지 신호이기도 하다. 다만 응급은 아니다 — 문이 열려
        있다는 것만으로 어르신이 위험하다고 말할 수 없다.
    """
    open_since = float(state.get("door_open_since") or 0.0)
    if open_since <= 0.0:
        return

    open_for = now - open_since
    if open_for < policy.DOOR_OPEN_TOO_LONG_SEC:
        return

    if runtime_store.mark_door_alert(senior_id, f"door_open:{int(open_since)}"):
        outbox.enqueue("T2", {
            "reason": "door_left_open",
            "open_sec": round(open_for),
        })
        logger.warning("door has been open for %.0fs; T2 queued", open_for)


def _check_absence(senior_id: str, state: ConvState, now: float) -> None:
    """오래 나가 있는가. 그리고 그것이 야간 외출이었는가.

    무엇을 하는가
        away_since 를 기준으로 두 임계치를 본다. 그리고 부재가 '시작된' 시각이
        야간이었으면 배회 신호로 따로 알린다.

    왜 침묵 사다리로는 안 되는가
        집에 아무도 없으면 사다리가 아예 시작되지 않는다. 나가서 안 돌아온 어르신은
        구조적으로 사다리에게 보이지 않는다 (CLAUDE.md §11).

        야간 배회는 침묵이 아니라 '활동'이라서 더욱 보이지 않는다. 치매의 대표
        증상이므로, 인지 축이 객관적 신호를 얻는 곳이 이 검사다.

    왜 occupancy_observed_at 이 아니라 away_since 인가
        observed_at 은 "이 값을 마지막으로 관측한 시각"이라서 AWAY 를 다시 관측하면
        갱신된다. 그러면 부재 시간이 매번 0 으로 리셋되어 알림이 영원히 안 나간다
        (localstore/schema.py 의 주석 참고).

    주의사항
        - 알림은 두 단계다. ABSENCE_CONCERN_SEC 은 T2, ABSENCE_ALERT_SEC 은 T1.
          T1 로 올리는 것은 '밤을 넘긴 미귀가'가 명백한 이상이기 때문이다.
        - 배회 판정은 부재가 '시작된' 시각으로 한다. 지금 시각으로 하면 저녁에 나간
          외출이 자정을 넘기는 순간 배회로 바뀐다.
    """
    if state.get("occupancy") != "AWAY":
        return

    away_since = float(state.get("away_since") or 0.0)
    if away_since <= 0.0:
        # AWAY 인데 시작 시각이 없다. 이 컬럼이 추가되기 전의 DB 이거나, 누군가
        # occupancy 를 door.occupancy 를 거치지 않고 직접 썼다는 뜻이다.
        logger.warning("occupancy is AWAY but away_since is unset; cannot measure absence")
        return

    away_for = now - away_since

    # 야간 외출: 부재가 시작된 시각이 야간 구간이었는가.
    if _is_night_local(away_since, state):
        if runtime_store.mark_door_alert(senior_id, f"night_exit:{int(away_since)}"):
            outbox.enqueue("T2", {
                "reason": "night_exit",
                "left_at": away_since,
                "night_hours": list(policy.NIGHT_EXIT_HOURS),
            })
            logger.warning("night exit detected (left at %.0f); T2 queued", away_since)

    if away_for >= policy.ABSENCE_ALERT_SEC:
        if runtime_store.mark_door_alert(senior_id, f"absence_alert:{int(away_since)}"):
            outbox.enqueue("T1", {
                "reason": "not_returned",
                "away_sec": round(away_for),
                "left_at": away_since,
            })
            logger.warning("absent for %.0fs; T1 queued", away_for)
        return

    if away_for >= policy.ABSENCE_CONCERN_SEC:
        if runtime_store.mark_door_alert(senior_id, f"absence_concern:{int(away_since)}"):
            outbox.enqueue("T2", {
                "reason": "long_absence",
                "away_sec": round(away_for),
                "left_at": away_since,
            })
            logger.info("absent for %.0fs; T2 queued", away_for)


def _is_night_local(moment: float, state: ConvState) -> bool:
    """이 순간이 어르신의 로컬 시각으로 야간 구간인가.

    구간이 자정을 넘는다(23시~5시). gate.is_quiet_hours 와 같은 함정이므로 같은
    방식으로 다룬다 — start > end 면 조건을 뒤집는다. 낮에 테스트하면 절대 안 잡히는
    종류의 버그다.
    """
    profile = (state.get("ctx") or {}).get("profile") or {}
    local = _local_now_from(moment, profile.get("timeZone"))
    start, end = policy.NIGHT_EXIT_HOURS

    if start > end:
        return local.hour >= start or local.hour < end
    return start <= local.hour < end


def _local_now_from(moment: float, time_zone: str | None):
    """특정 순간을 어르신의 로컬 시각으로. 시간대를 모르면 UTC."""
    zone = timezone.utc
    if time_zone:
        try:
            zone = ZoneInfo(time_zone)
        except Exception:  # noqa: BLE001
            logger.warning("unknown time zone %r; using UTC for the night-exit check",
                           time_zone)
    return datetime.fromtimestamp(moment, tz=zone)


# ─────────────────────────────────────────────────────────────────────────────
# OUTBOX 와 일간 요약
# ─────────────────────────────────────────────────────────────────────────────


def outbox_flush(notifier: GuardianNotifier | None = None) -> dict[str, int]:
    """아직 전달되지 않은 보호자 알림을 재시도한다.

    왜 존재하는가
        네트워크는 언젠가 끊기고, 끊긴 연결로 발사된 T1 알림은 그냥 사라진다.
        안전 기기에서 그것은 용납이 안 되므로, 모든 알림은 먼저 저장되고 나중에
        전달된다.

    누가 호출하는가
        APScheduler. 자주(policy.OUTBOX_FLUSH_INTERVAL_SEC).

    무엇을 호출하는가
        localstore.outbox.flush. 판단과 상태 전이는 전부 그쪽에 있고, 이 함수는
        어댑터를 골라 넘기고 결과를 로그로 남기는 얇은 껍데기다.

    인자
        notifier: 채널 어댑터. 기본값은 로그 전용 임시 어댑터다. 실제 채널이
            붙기 전까지의 자리 표시자이며, 그 상태를 로그로 요란하게 남긴다.

    반환값
        {"sent": n, "failed": n, "gave_up": n}.

    주의사항
        - 늦은 전달은 원래 타임스탬프를 포함해 '지연됨'으로 표시한다. 보호자가
          "지금 벌어지는 일"과 "와이파이가 끊긴 두 시간 전에 벌어진 일"을 구분할 수
          있어야 한다.
        - 이 큐는 쓰기 내구성을 완화하지 '않는' 유일한 지점이다. 이 기기의 나머지는
          크래시 후 마지막 몇 초를 잃어도 되지만, 큐에 든 응급 알림은 안 된다
          (CLAUDE.md §18).
        - 백오프를 두고 재시도하며, 포기할 때는 요란하게 포기한다. 조용히 포기하지 않는다.
        - 예외를 밖으로 던지지 않는다. 이 함수가 스케줄러에서 죽으면 큐가 영원히
          멈추고, 그때 안 나가는 것은 응급 알림이다.
    """
    channel = notifier if notifier is not None else LoggingGuardianNotifier()
    try:
        result = outbox.flush(channel)
    except Exception:  # noqa: BLE001 - 틱이 죽으면 큐가 영원히 멈춘다
        logger.exception("outbox flush tick failed; queue stays intact for next tick")
        return {"sent": 0, "failed": 0, "gave_up": 0}

    if result["sent"] or result["failed"] or result["gave_up"]:
        logger.info(
            "outbox flush: sent=%d failed=%d gave_up=%d pending=%d",
            result["sent"],
            result["failed"],
            result["gave_up"],
            outbox.pending_count(),
        )
    return result


def schedule_tick(senior_id: str, *, time_zone: str | None = None) -> int:
    """때가 된 일상 권유를 '제안'으로 큐에 넣는다. 말하지는 않는다.

    무엇을 하는가
        어르신의 로컬 시각을 보고, 지난 식사·수분 시각에 해당하는 제안을 하루에
        한 번씩만 큐에 넣는다.

    왜 스케줄러가 직접 말하지 않는가
        말할지 여부는 게이트의 몫이다. 스케줄러가 직접 말하면 quiet hours 도
        쿨다운도 우회되고, 그 우회는 코드 어디에도 적히지 않는다 (CLAUDE.md §7).

    왜 식사·수분이 기본 루틴인가
        어르신은 배고픔과 갈증을 잘 느끼지 못해서, 거른 식사와 탈수가 복약 시각보다
        더 문제인 경우가 많다 (CLAUDE.md §1). 그리고 이 둘은 백엔드 데이터 없이도
        돌아가므로 오프라인에서도 살아 있다.

    누가 호출하는가
        jobs.scheduler(실기), 그리고 압축 시계 경로의 run_all_ticks_once.

    반환값
        새로 넣은 제안 개수.

    주의사항
        - 하루 한 번만 넣는다. slot_key 에 날짜가 들어가고, 이미 처리된 슬롯은
          건너뛴다. 안 그러면 매 틱마다 같은 제안이 쌓인다.
        - 복약은 여기서 다루지 않는다. 복약 시각은 백엔드 care_record 에 있고,
          그 스케줄을 읽어오는 경로가 아직 없다. 임의로 시각을 정하면 실제 처방과
          어긋나므로, 없는 채로 두고 이 사실을 남긴다. → PROGRESS.md
    """
    local_now = _local_now(time_zone)
    today = local_now.date().isoformat()
    added = 0

    for kind, times, intent, priority, seed in (
        ("meal", policy.MEAL_REMINDER_TIMES, "companion", "medium", "식사하셨어요?"),
        ("water", policy.WATER_REMINDER_TIMES, "companion", "low", "물 한 잔 드시겠어요?"),
    ):
        for hour, minute in times:
            if (local_now.hour, local_now.minute) < (hour, minute):
                continue  # 아직 그 시각이 안 됐다

            slot_key = f"{today}:{kind}:{hour:02d}{minute:02d}"
            if proposals.is_slot_completed(senior_id, slot_key):
                continue
            if _already_queued(senior_id, slot_key):
                continue

            proposals.enqueue(senior_id, {
                "intent": intent,
                "priority": priority,
                "seed": seed,
                # 때를 놓친 식사 권유는 그날 버린다. 저녁 7시의 점심 권유는 이상하다.
                "expires_at": clock.now() + policy.ROUTINE_REMINDER_TTL_SEC,
                "origin": f"schedule:{kind}:{hour:02d}{minute:02d}",
                "meta": {"slot_key": slot_key},
            })
            # 넣자마자 완료로 표시한다. 여기서의 '완료'는 "오늘 이 슬롯을 이미
            # 제안했다"는 뜻이고, 게이트가 그것을 다시 평가한다.
            proposals.mark_slot_completed(senior_id, slot_key)
            added += 1

    if added:
        logger.info("schedule_tick queued %d routine proposal(s) for %s", added, senior_id)
    return added


def _already_queued(senior_id: str, slot_key: str) -> bool:
    """같은 슬롯의 제안이 이미 큐에 있는가."""
    return any(
        (proposal.get("meta") or {}).get("slot_key") == slot_key
        for proposal in proposals.pending(senior_id)
    )


def _local_now(time_zone: str | None):
    """지금을 어르신의 로컬 시각으로. 시간대를 모르면 UTC 로 둔다.

    시각은 clock 을 통해서만 읽는다(§15). 압축 시계로 하루를 흘리는 시연에서
    이 틱이 함께 흘러야 하기 때문이다.
    """
    return _local_now_from(clock.now(), time_zone)


def contract_tick(
    senior_id: str,
    *,
    conversation_id: str | None = None,
    robot_id: str | None = None,
    clarification_client=None,
    onboarding_client=None,
) -> int:
    """계약 대화(온보딩·재질의)를 '제안'으로 큐에 넣는다. 말하지는 않는다.

    무엇을 하는가
        백엔드에 물을 것이 있는지 확인하고, 있으면 제안 하나를 넣는다. 게이트가
        말할지 정한다.

    왜 로봇이 스스로 시작하는가
        어르신이 먼저 "온보딩 해줘"라고 말하지는 않는다. 보류된 사실도 마찬가지다.
        누군가 꺼내야 하고, 그 '누군가'는 제안만 하고 심판은 게이트가 한다
        (CLAUDE.md §7).

    ★ 한 대화에 후보 하나  (CLAUDE.md §12)
        백엔드가 활성 후보를 하나만 내려주지만, 그것만으로는 부족하다. 한 대화 안에서
        틱이 여러 번 돌면 첫 후보가 해결된 뒤 곧바로 두 번째가 나온다. 어르신 입장에서는
        연달아 심문받는 것과 같다.

        그래서 대화별로 한 번만 제안한다. 표시는 completed_slot 에 남기며, 키에
        conversation_id 가 들어가므로 다음 대화에서는 다시 물을 수 있다.

    왜 온보딩보다 재질의를 먼저 보는가
        재질의는 이미 어르신이 말한 것에 대한 확인이고, 온보딩은 새 질문이다.
        꺼내 놓은 이야기를 마무리하는 편이 자연스럽다.

    누가 호출하는가
        jobs.scheduler(policy.CONTRACT_TICK_INTERVAL_SEC 마다), 그리고 테스트.

    반환값
        새로 넣은 제안 개수 (0 또는 1).

    주의사항
        백엔드에 못 닿으면 아무것도 하지 않는다. 계약을 서버가 강제하는데 서버에 못
        닿으면 계약이 없는 상태이고, 그 상태로 민감정보를 물으면 안 된다.
        침묵 사다리와 정반대의 판단이며, 그쪽은 네트워크가 없을 때가 가장 중요하다.
    """
    if conversation_id:
        slot_key = f"contract:{conversation_id}"
        if proposals.is_slot_completed(senior_id, slot_key):
            return 0
    else:
        # 대화 밖(대기 상태)에서는 대화별 제한을 걸 수 없다. 게이트의 쿨다운이
        # 남용을 막는다 — clarification 우선순위는 쿨다운을 무시하지만, 그때도
        # quiet hours 와 끼어들기 검사는 그대로 적용된다.
        slot_key = None

    try:
        proposal = _contract_proposal(
            senior_id, robot_id, clarification_client, onboarding_client)
    except BackendUnavailable as error:
        logger.info("contract tick skipped: %s", error)
        return 0

    if proposal is None:
        return 0

    proposals.enqueue(senior_id, proposal)
    if slot_key:
        proposals.mark_slot_completed(senior_id, slot_key)
    logger.info("contract tick queued a %s proposal for %s", proposal["intent"], senior_id)
    return 1


def _contract_proposal(
    senior_id: str,
    robot_id: str | None,
    clarification_client,
    onboarding_client,
) -> dict | None:
    """물을 것이 있으면 제안 하나를 만든다. 없으면 None.

    seed 를 최종 문구로 쓰지 않는다. 실제 문장은 핸들러가 백엔드에서 다시 받아
    만든다 — 제안이 큐에서 대기하는 동안 어르신이 앱으로 답했을 수 있고, 그러면
    이미 답한 질문을 묻게 된다.
    """
    from bomi_ai_chat.backend_client.contract_client import (
        BackendClarificationClient,
        BackendOnboardingClient,
    )

    # 1. 꺼내 놓은 이야기부터 마무리한다.
    #
    #    재질의는 이미 어르신이 말한 것에 대한 확인이고, 온보딩은 새 질문이다.
    #    꺼내 놓은 이야기를 마무리하는 편이 자연스럽다.
    clarification = clarification_client or BackendClarificationClient()
    candidate = clarification.active(senior_id)
    if candidate is not None:
        return {
            "intent": "clarification",
            "priority": "clarification",
            "seed": "",
            "origin": f"clarification:{candidate.get('factCandidateId', '')}",
            "meta": {"fact_type": candidate.get("factType", "")},
        }

    # 2. 온보딩이 남아 있는가.
    #
    #    robot_id 가 없으면 '이어받기'만 가능하다. 서버는 새 ROBOT 세션을 만들 때
    #    robot_id 를 요구하므로, 없으면 아예 시도하지 않는다 — 400 을 받아 오프라인으로
    #    오인하는 것보다 낫다.
    resolved_robot_id = robot_id or _configured_robot_id()
    if not resolved_robot_id:
        logger.info("no robot id configured; onboarding cannot be started from the robot")
        return None

    onboarding = onboarding_client or BackendOnboardingClient()
    session = onboarding.start_or_resume(senior_id, resolved_robot_id)
    if not session or not session.get("sessionId"):
        return None
    if session.get("status") != "IN_PROGRESS":
        # 이미 끝났거나 중단된 세션이다. 다시 꺼내지 않는다.
        return None

    return {
        "intent": "onboarding",
        "priority": "clarification",
        "seed": "",
        "origin": f"onboarding:{session['sessionId']}",
        "meta": {"session_id": session["sessionId"]},
    }


def _configured_robot_id() -> str | None:
    """설정된 로봇 id. 없으면 None.

    config 조회가 실패해도 틱을 죽이지 않는다. 온보딩을 못 시작할 뿐이고,
    침묵 사다리 같은 안전 경로는 이 값과 무관하다.
    """
    try:
        from bomi_ai_chat.config import get_settings

        return get_settings().robot_id
    except Exception:  # noqa: BLE001 - 설정 문제로 틱이 죽으면 안 된다
        logger.warning("could not read the robot id from settings", exc_info=True)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# T3 동의 질문  (S15P11E102-253, CLAUDE.md §9)
# ─────────────────────────────────────────────────────────────────────────────


def consent_tick(senior_id: str) -> int:
    """누적된 정서 신호가 문턱을 넘겼으면 T3 동의 질문을 '제안'으로 큐에 넣는다.

    무엇을 하는가
        handlers.handle_emotional 이 더 이상 즉시 큐잉하지 않는다(263 에서 253 으로
        바뀐 부분). 대신 이 틱이 주기적으로 다음을 전부 확인하고, 모두 통과해야만
        질문 하나를 큐에 넣는다.
          1. 기능 자체가 켜져 있는가 (policy.T3_CONSENT_ENABLED, config 킬스위치)
          2. 어르신이 애초에 가족 공유에 동의했는가 (상위 동의, S15P11E102-253)
          3. 이미 대기 중인 동의 질문이 없는가 (policy.T3_CONSENT_ONE_PENDING_ONLY)
          4. 지금 열려 있는 대화가 봉인되지 않았는가 (emotion.is_conversation_sealed)
          5. 누적 신호가 문턱을 넘었는가 (policy.T3_CONSENT_SIGNAL_THRESHOLD)
          6. 지금이 '자연스러운 창'인가 — 침묵 사다리가 0, 대기 중인 안전 확인이
             없고, occupancy 가 AWAY 가 아니다.

    왜 즉시 큐잉이 아니라 누적 문턱인가
        정서 발화 한 번에 곧바로 질문을 예약하면 지나치게 민감하다. 하루에
        스쳐 지나가듯 한 말에도 45분 뒤 "가족분께 전해도 될까요"가 날아오면
        그 자체가 감시처럼 느껴진다(policy.T3_CONSENT_SIGNAL_THRESHOLD 참고).

    왜 안전 확인·침묵 사다리·occupancy 를 함께 보는가
        어르신이 증상을 말해 안전 확인을 기다리는 중이거나, 사다리가 이미 올라가
        있거나, 집에 없는데 이 질문이 끼어들면 안 된다. T3 동의는 급하지 않고
        (priority "low"), 그런 순간에 끼어들 이유가 전혀 없다.

    누가 호출하는가
        jobs.scheduler(policy.CONTRACT_TICK_INTERVAL_SEC 마다 — 이 질문도 급하지
        않으므로 재질의·온보딩과 같은 주기를 쓴다), 그리고 압축 시계 경로의
        run_all_ticks_once, 그리고 테스트.

    반환값
        새로 넣은 제안 개수 (0 또는 1).

    주의사항
        실제로 나갈 문장(seed)을 여기서 확정한다. handle_emotional 은 이 문장을
        LLM 없이 그대로 말한다(§16) — 다시 쓰면 "무엇을 물었는가"의 기록이
        불안정해진다.
    """
    if not policy.T3_CONSENT_ENABLED:
        return 0

    from bomi_ai_chat.config import get_settings

    try:
        if not get_settings().t3_consent_enabled:
            logger.info("T3 consent is disabled by the T3_CONSENT_ENABLED env kill switch")
            return 0
    except Exception:  # noqa: BLE001 - 설정 문제로 틱이 죽으면 안 된다
        logger.warning("could not read the T3 consent kill switch; assuming enabled",
                       exc_info=True)

    if not _guardian_sharing_consented(senior_id):
        return 0

    if policy.T3_CONSENT_ONE_PENDING_ONLY and _has_pending_consent_proposal(senior_id):
        return 0

    state = runtime_store.load(senior_id)
    conversation_id = state.get("conversation_id")

    if emotion.is_conversation_sealed(senior_id, conversation_id):
        return 0

    if emotion.pending_signal_count(senior_id) < policy.T3_CONSENT_SIGNAL_THRESHOLD:
        return 0

    if int(state.get("silence_level") or 0) != 0:
        return 0
    if float(state.get("safety_check_until") or 0.0) > 0.0:
        return 0
    if state.get("occupancy") == "AWAY":
        return 0

    request_id = consent_store.create_request(senior_id, conversation_id)
    emotion.consume_pending_signals(senior_id)

    now = clock.now()
    proposals.enqueue(senior_id, {
        "intent": "emotional",
        "priority": "low",
        # seed 는 이 질문의 최종 문장이다 — handle_emotional 이 다시 쓰지 않는다.
        "seed": "아까 마음이 힘들다고 하셨던 이야기, 가족분께 전해도 괜찮을까요?",
        "expires_at": now + policy.T3_CONSENT_DELAY_SEC + policy.T3_CONSENT_TTL_SEC,
        # request_id 를 origin 에 싣는다. graph.handlers._extract_consent_request_id
        # 가 이 형식("t3_consent:<id>: ...")을 그대로 기대하므로, 둘을 같이 고친다.
        "origin": f"t3_consent:{request_id}: 어르신이 마음을 이야기하셨고, 그것을 "
                  "가족과 나눠도 되는지 아직 여쭤보지 않았습니다.",
        "meta": {
            "t3_consent": True,
            "request_id": request_id,
            "not_before": now + policy.T3_CONSENT_DELAY_SEC,
        },
    })
    logger.info("queued a T3 consent question (request_id=%d) for senior %s (asking in %ds)",
                request_id, senior_id, policy.T3_CONSENT_DELAY_SEC)
    return 1


def _has_pending_consent_proposal(senior_id: str) -> bool:
    """이미 대기 중인 동의 질문 제안이 있는가."""
    return any(
        (proposal.get("meta") or {}).get("t3_consent")
        for proposal in proposals.pending(senior_id)
    )


def _guardian_sharing_consented(senior_id: str) -> bool:
    """어르신이 '가족과 나누는 것' 자체에 동의했는가 (S15P11E102-253).

    왜 이 확인이 필요한가
        T3 동의는 두 겹이다. 위(상위 동의)는 "느낌을 가족과 나눠도 되는 범주인가"
        이고, 아래(개별 동의)는 "이번 이야기를 전해도 되는가"이다. 상위 동의가
        없는데 개별 질문을 던지면, 어르신이 이미 "그런 건 묻지 말라"고 설정해 둔
        것을 로봇이 무시하고 계속 묻는 셈이 된다 — 설정이 있으나 마나가 된다
        (CLAUDE.md §9 의 두 겹 동의).

    왜 문맥 캐시를 읽는가
        이 값의 권위는 백엔드 `app_user.guardian_sharing_consent_status` 이고,
        문맥 조립 응답의 profile 에 실려 온다. 이 틱은 배경 작업이라 백엔드를
        직접 부르지 않는다(부르면 네트워크가 끊긴 동안 틱이 통째로 멈춘다).
        마지막으로 성공한 문맥의 로컬 사본을 읽는 것으로 충분하다.

    왜 모르면 '아니오'인가
        캐시가 없거나(한 번도 문맥을 못 받음), 필드가 없거나(백엔드가 아직 이
        필드를 안 실어주는 구버전), 값이 False 면 전부 묻지 않는다. 동의 여부를
        모르는 채로 "가족분께 전해도 될까요"를 던지는 것이, 물어볼 기회를 한 번
        놓치는 것보다 훨씬 나쁜 실패다 — 서버 쪽 isGranted 와 같은 방향
        ("명시적 GRANTED 만 통과")이다.
    """
    ctx = context_cache.load(senior_id)
    if not ctx:
        return False
    profile = ctx.get("profile") or {}
    return profile.get("guardianSharingConsentGranted") is True


# ─────────────────────────────────────────────────────────────────────────────
# 사실 추출 큐 비우기  (S15P11E102-255, CLAUDE.md §8, §16)
# ─────────────────────────────────────────────────────────────────────────────


def extraction_flush(
    senior_id: str,
    *,
    llm=None,
    fact_client=None,
) -> dict[str, int]:
    """추출 큐를 비운다 — LLM 으로 사실을 뽑고, 있으면 백엔드에 제출한다.

    무엇을 하는가
        graph.build.memory_write 가 쌓아 둔 localstore.extraction 의 대기 행을
        오래된 순으로 최대 policy.EXTRACTION_FLUSH_BATCH_SIZE 개 읽는다. 행마다
        생성 LLM 을 한 번 불러 사실을 뽑고(prompts.build_memory_extraction_prompt),
        뽑힌 것이 있으면 fact_client 로 제출한다. 제출까지 성공했을 때만(또는
        애초에 뽑을 것이 없었을 때만) 그 행을 extracted=1 로 표시한다.

    왜 LLM 호출이 여기 있는가
        턴 경로(graph/build.memory_write)는 큐잉만 하고 LLM 을 부르지 않는다
        (CLAUDE.md §16 — 턴당 생성 호출 1회 예산). 이 틱은 그 예산 밖에서
        도는 배경 작업이라 행마다 생성 호출을 하나씩 써도 된다.

    누가 호출하는가
        jobs.scheduler(policy.EXTRACTION_FLUSH_INTERVAL_SEC 마다), 그리고
        압축 시계 경로의 run_all_ticks_once, 그리고 테스트.

    반환값
        {"processed": n, "submitted": n, "failed": n} — processed 는 이번
        flush 에서 extracted=1 로 표시한 행 수(뽑을 것이 없었던 행 포함),
        submitted 는 실제로 백엔드에 올라간 사실 개수, failed 는 이번에
        처리하지 못해 다음 flush 로 넘긴 행 수.

    주의사항
        - 킬스위치(policy.EXTRACTION_ENABLED / config 의 환경변수) 중 하나라도
          꺼지면 아무것도 하지 않는다.
        - LLM 호출이 실패하거나 응답을 못 알아들으면 그 행은 표시하지 않고
          다음 flush 로 넘긴다 — 다시 시도하는 것이 조용히 잃는 것보다 낫다.
        - fact_client 제출이 실패하면(FactSubmissionError) 마찬가지로 표시하지
          않는다. 여기서 표시해버리면 그 사실은 다시는 제출 시도되지 않는다
          (backend_client/fact_client.py 의 모듈 docstring 참고).
        - 예외를 밖으로 던지지 않는다. 이 틱이 죽으면 큐가 영원히 쌓이기만
          하고, 그 사실을 아무도 모르게 된다(다른 틱들과 같은 원칙).
    """
    if not policy.EXTRACTION_ENABLED:
        return {"processed": 0, "submitted": 0, "failed": 0}

    from bomi_ai_chat.config import get_settings

    try:
        if not get_settings().extraction_enabled:
            logger.info(
                "fact extraction is disabled by the EXTRACTION_ENABLED env kill switch"
            )
            return {"processed": 0, "submitted": 0, "failed": 0}
    except Exception:  # noqa: BLE001 - 설정 문제로 틱이 죽으면 안 된다
        logger.warning(
            "could not read the extraction kill switch; assuming enabled",
            exc_info=True,
        )

    try:
        rows = extraction.pending(limit=policy.EXTRACTION_FLUSH_BATCH_SIZE)
    except Exception:  # noqa: BLE001 - 틱이 죽으면 큐가 영원히 멈춘다
        logger.exception("extraction flush tick failed to read the queue")
        return {"processed": 0, "submitted": 0, "failed": 0}

    if not rows:
        return {"processed": 0, "submitted": 0, "failed": 0}

    resolved_llm = llm if llm is not None else _default_extraction_llm()
    resolved_fact_client = fact_client if fact_client is not None else _default_fact_client()

    result = {"processed": 0, "submitted": 0, "failed": 0}
    for row in rows:
        try:
            facts = _extract_facts(resolved_llm, row)
        except Exception:  # noqa: BLE001 - 한 행의 LLM 실패가 틱 전체를 죽이면 안 된다
            logger.warning(
                "extraction failed for job %s; will retry next flush",
                row["id"], exc_info=True,
            )
            result["failed"] += 1
            continue

        if facts:
            try:
                resolved_fact_client.submit_fact_candidates(
                    row["senior_id"],
                    conversation_id=row["conversation_id"],
                    source_message_id=row["source_message_id"],
                    facts=facts,
                )
            except Exception:  # noqa: BLE001 - fact_client 는 FactSubmissionError 를
                # 올리지만, 예상 못 한 예외까지도 이 행을 조용히 잃는 방향(잘못
                # extracted=1 표시)으로 새면 안 된다. 좁게 못 잡을 이유가 없어도
                # 넓게 잡아 안전한 쪽(재시도)으로 떨어뜨린다.
                logger.warning(
                    "fact candidate submission failed for job %s; will retry next flush",
                    row["id"], exc_info=True,
                )
                result["failed"] += 1
                continue
            result["submitted"] += len(facts)

        extraction.mark_extracted(row["id"])
        result["processed"] += 1

    if result["submitted"] or result["failed"]:
        logger.info(
            "extraction flush: processed=%d submitted=%d failed=%d pending=%d",
            result["processed"], result["submitted"], result["failed"],
            extraction.pending_count(senior_id),
        )
    return result


def _default_extraction_llm():
    """추출용 LLM 클라이언트를 지연 생성한다.

    왜 지연 생성인가
        graph/handlers._llm 과 같은 이유다. import 시점에 만들면 API 키가 없는
        환경에서 이 모듈을 불러오는 것만으로 실패한다.
    """
    from bomi_ai_chat.llm.client import LLMClient

    return LLMClient()


def _default_fact_client():
    """사실 제출 클라이언트를 지연 생성한다. 이유는 위와 같다."""
    from bomi_ai_chat.backend_client.fact_client import BackendFactClient

    return BackendFactClient()


def _extract_facts(llm, row: dict) -> list[dict]:
    """대기 행 하나에서 사실을 뽑는다. 못 뽑았거나 없으면 빈 리스트.

    무엇을 호출하는가
        prompts.build_memory_extraction_prompt 로 프롬프트를 조립하고, 이 턴의
        유일한 생성 호출을 한다(row 하나당 최대 1회).

    반환값
        [{"factType": ..., "content": ...}, ...]. 최대
        policy.EXTRACTION_MAX_FACTS_PER_UTTERANCE 개로 자른다 — 프롬프트가
        상한을 지키라고 지시하지만, 모델이 어겨도 여기서 한 번 더 막는다.
    """
    from bomi_ai_chat.prompts import build_memory_extraction_prompt

    prompt = build_memory_extraction_prompt(
        row.get("preceding_robot_utterance") or "", row["content"],
    )
    raw = llm.generate(prompt)
    facts = _parse_json_fact_array(raw)
    return facts[: policy.EXTRACTION_MAX_FACTS_PER_UTTERANCE]


def _parse_json_fact_array(raw: str | None) -> list[dict]:
    """모델 출력에서 사실 배열을 꺼낸다. 실패하면 빈 리스트.

    graph/handlers._parse_json_object 와 같은 원칙이다 — 코드 블록으로 감싸
    오는 경우가 흔해서 대괄호 범위만 잘라 쓴다. 다만 여긴 객체가 아니라
    배열이라 별도로 둔다(공유 헬퍼로 합치면 두 모듈이 서로를 몰라도 되는
    경계가 흐려진다).
    """
    text = (raw or "").strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        parsed = json.loads(text[start:end + 1])
    except ValueError:
        logger.warning("extraction did not return a JSON array; treating it as nothing found")
        return []
    if not isinstance(parsed, list):
        return []
    # factType 과 content 가 둘 다 있는, 비어 있지 않은 항목만 남긴다. 모델이
    # 형태를 어겨도(예: 문자열만 나열) 백엔드로 그대로 새어나가지 않게 한다.
    return [
        {"factType": str(item["factType"]), "content": str(item["content"])}
        for item in parsed
        if isinstance(item, dict) and item.get("factType") and item.get("content")
    ]


def daily_summary_job(senior_id: str) -> None:
    """하루에 한 번 T2 요약을 만들어 보낸다.

    무엇을 하는가
        하루를 집계한다. 복약 이행, 식사, 물, 수면, 기분 추세, 발화량, 외출 횟수,
        지남력 질문 반복 횟수. 그리고 알림 하나를 보낸다.

    왜 이벤트가 아니라 하나의 배치인가
        T2 는 사건이 아니라 추세다. 개별 이벤트를 흘려보내면 감시가 되고, 동시에
        보호자가 알림을 무시하도록 훈련시킨다. 그 대가는 T1 에 대한 주의력이다
        (CLAUDE.md §9).

    누가 호출하는가
        APScheduler. 어르신의 '로컬' 새벽에 하루 한 번, 백엔드의 일간 요약 배치
        시간대와 맞춰서.

    주의사항
        - 보내기 전에 guardian_sharing_consent_status 를 확인한다. T1 과 달리 T2 는
          동의 면제가 아니다.
        - 지남력 질문 반복은 여기, 오직 여기에 속한다. 절대 프롬프트에 닿아서는 안 된다.
          닿으면 로봇의 어조에 새어나가서 열 번째 답변이 짜증스럽게 들린다
          (CLAUDE.md §8).
        - 집계와 이상치만. 원본 이동 기록이나 대화 기록은 보내지 않는다.
    """
    # TODO(backend_client + notify): build_summary(...) 후 notify_guardian("T2", ...)
    ...
