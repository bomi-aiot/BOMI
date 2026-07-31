"""백그라운드 루프 — 로봇을 '능동적'으로 만드는 코드.

어디에 위치하는가
    그래프 밖. LangGraph 는 요청-응답이므로 누군가 깨워줘야 한다.
    이 함수들이 APScheduler 가 호출하는 것이고, 로봇이 먼저 말하는 유일한 이유다.

    네 개의 루프.
        silence_tick      -- 침묵 사다리를 올리고, 끝에서 T1 으로 에스컬레이션
        door_watch_tick   -- 현관 로그만이 볼 수 있는 패턴
        outbox_flush      -- 큐에 쌓인 보호자 알림 재시도
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

# 이 두 개는 아래 틱 함수들의 TODO(localstore) 본문이 채워지는 순간 바로 쓰인다.
# 임계치는 policy 에서 읽고(함수에 박지 않는다), 시간은 clock 으로만 읽는다(§15).
# 뼈대 단계에서 지우면 다음 티켓이 같은 것을 다시 추가하게 된다.
from bomi_ai_chat import policy  # noqa: F401
from bomi_ai_chat.clock import clock  # noqa: F401
from bomi_ai_chat.state import ConvState

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
    if runtime.get("occupancy") == "AWAY":
        return True
    # TODO: quiet hours(로컬 시간), 루틴 베이스라인 조회, RESTING 인내심 반영.
    raise NotImplementedError


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
    # TODO(localstore): runtime = read_runtime(senior_id)
    #   if _is_absence_expected(runtime): return
    #   elapsed = clock.now() - runtime["last_user_interaction_at"]
    #   level = rung_for(elapsed, policy.SILENCE_LADDER_SEC, runtime["rest_state"])
    #   if level == 0: return
    #   if level <= 2:
    #       priority, seed = {1: ("low", "점심 드셨어요?"),
    #                         2: ("high", "어르신, 괜찮으세요?")}[level]
    #       app.invoke({"trigger_type": "proactive",
    #                   "proposals": [{"intent": "companion", "priority": priority,
    #                                  "seed": seed, "origin": f"silence_ladder:{level}"}]},
    #                  config=thread(senior_id))
    #   elif level == 3:
    #       # 여기서는 미리 만들어둔 로컬 오디오를 우선한다. 네트워크 없이 동작해야
    #       # 하고, 그것이 바로 이 프로브가 가장 중요한 상황이다 (CLAUDE.md §18).
    #       app.invoke({"trigger_type": "proactive",
    #                   "proposals": [{"intent": "companion", "priority": "critical",
    #                                  "seed": "...", "origin": "silence_ladder:3"}]},
    #                  config=thread(senior_id))
    #   else:
    #       app.invoke({"trigger_type": "proactive", "safety_level": "T1",
    #                   "escalation": {"reason": "no_response",
    #                                  "silence_sec": elapsed}},
    #                  config=thread(senior_id))
    ...


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
    """
    # TODO(localstore + notify): 위 다섯 확인. policy.ABSENCE_*,
    #   policy.NIGHT_EXIT_HOURS, policy.DOOR_HEARTBEAT_TIMEOUT_SEC 사용.
    ...


# ─────────────────────────────────────────────────────────────────────────────
# OUTBOX 와 일간 요약
# ─────────────────────────────────────────────────────────────────────────────


def outbox_flush() -> None:
    """아직 전달되지 않은 보호자 알림을 재시도한다.

    왜 존재하는가
        네트워크는 언젠가 끊기고, 끊긴 연결로 발사된 T1 알림은 그냥 사라진다.
        안전 기기에서 그것은 용납이 안 되므로, 모든 알림은 먼저 저장되고 나중에
        전달된다.

    누가 호출하는가
        APScheduler. 자주(수십 초 단위).

    주의사항
        - 늦은 전달은 원래 타임스탬프를 포함해 '지연됨'으로 표시한다. 보호자가
          "지금 벌어지는 일"과 "와이파이가 끊긴 두 시간 전에 벌어진 일"을 구분할 수
          있어야 한다.
        - 이 큐는 쓰기 내구성을 완화하지 '않는' 유일한 지점이다. 이 기기의 나머지는
          크래시 후 마지막 몇 초를 잃어도 되지만, 큐에 든 응급 알림은 안 된다
          (CLAUDE.md §18).
        - 백오프를 두고 재시도하며, 포기할 때는 요란하게 포기한다. 조용히 포기하지 않는다.
    """
    # TODO(localstore + notify): 대기 항목을 꺼내 전달하고, 성공 표시 또는 재예약.
    ...


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
