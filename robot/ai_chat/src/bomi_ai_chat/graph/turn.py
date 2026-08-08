"""반응형 1왕복 — 어르신이 말하면 로봇이 대답하는 최소 경로.

어디에 위치하는가
    pipeline.py(오디오 캡처와 STT)와 그래프 사이. STT 가 만든 '텍스트'를 받아
    그래프를 돌리고, emit 이 재생을 시작한 뒤 즉시 돌아온다.

왜 pipeline.py 를 고치지 않고 여기 두는가
    pipeline 은 이미 동작하는 입력 루프 드라이버다(캡처 -> STT -> 응답 -> 재생).
    그걸 다시 쓰는 대신, '판단과 생성'만 그래프로 옮긴다. 역할 분담은 그대로다.
        pipeline = 입력 루프 드라이버
        이 모듈  = 한 턴을 그래프에 태우고 지연을 잰다
        emit     = 재생 시작(논블로킹)

    205 번에서 barge-in 을 붙일 때 확인해야 할 전제도 그대로다. 재생 완료를 기다리는
    구조면 barge-in 이 원리적으로 불가능하다 (CLAUDE.md §13).

참고
    CLAUDE.md §6 (진입 경로), §16 (지연 예산), §22 2단계
"""

from __future__ import annotations

import logging
from typing import Any

from bomi_ai_chat import degradation
from bomi_ai_chat.state import ConvState
from bomi_ai_chat.turn_timer import TurnTimer

logger = logging.getLogger(__name__)


def run_user_turn(
    app: Any,
    senior_id: str,
    text: str,
    *,
    conversation_id: str | None = None,
    duration_sec: float = 0.0,
    closing_turn: bool = False,
    timer: TurnTimer | None = None,
) -> ConvState:
    """어르신 발화 한 번을 그래프에 태운다.

    무엇을 하는가
        trigger_type="user_utterance" 로 그래프를 호출한다. 이 경로는 게이트를
        거치지 않는다 — 우리에게 말을 건 사람에게 대답할 허락을 받을 필요는 없다.

    누가 호출하는가
        pipeline(실기), 그리고 테스트.

    인자
        app: build_graph() 가 컴파일한 그래프.
        senior_id: checkpointer 의 thread_id 이자 문맥 조회 키.
        text: STT 결과.
        conversation_id: 명시적으로 이어 붙일 대화 id. 보통은 넘기지 않는다 — 실기
            호출부(bootstrap.py)는 넘기지 않고, 체크포인터에 저장된 값이 이어진다
            (S15P11E102-306). 테스트가 특정 대화를 강제로 지정하고 싶을 때만 쓴다.
        duration_sec: VAD 가 잰 발화 길이. 맞장구 판별에 쓰인다 — 텍스트만으로는
            "응"이 맞장구인지 짧은 대답인지 구분되지 않는다.
        timer: 지연 측정기. 없으면 새로 만든다. 호출부가 STT 단계까지 함께 재고
            싶으면 자기 것을 넘긴다.

    반환값
        그래프 실행 후의 state. final_utterance 가 None 이면 침묵을 선택한 것이다.

    주의사항
        - 반환 시점에 재생은 '시작만' 됐다. 끝나기를 기다리지 않는다.
        - 예외를 밖으로 던지지 않는다. 한 턴의 실패가 입력 루프를 죽이면 로봇이
          그대로 멈춘다.
        - conversation_id=None 은 "대화 없음"이 아니라 "이 호출은 관여하지 않는다"는
          뜻이다. 진짜 "새 대화를 열어라"는 graph/ingress.note_interaction 의 유휴
          경계 판정이 결정한다 (policy.CONVERSATION_BOUNDARY_IDLE_SEC).
    """
    timer = timer or TurnTimer()
    thread = {"configurable": {"thread_id": senior_id}}

    inputs: ConvState = {
        "trigger_type": "user_utterance",
        "senior_id": senior_id,
        "user_input": text,
        "user_input_duration_sec": duration_sec,
        "closing_turn": closing_turn,
    }

    # conversation_id 는 '조건부로만' 넣는다 (S15P11E102-306).
    #
    # ★ 여기서 있었던 결함
    #   예전에는 "conversation_id": conversation_id 를 무조건 넣었다. 이 함수의
    #   실런타임 호출부(bootstrap.py 의 run_conversation_loop)는 이 인자를 넘기지
    #   않으므로 값은 늘 None 이었다. state.py 의 conversation_id 에는 reducer 가
    #   없어(기본 LastValue 채널) 매 턴 그 None 이 체크포인터에 저장돼 있던 값을
    #   덮어썼다. 백엔드는 conversationId=null 을 "새 대화를 열어라"로 해석하므로,
    #   실제로는 발화마다 새 conversation 행이 생겼다 — "최근 대화" 문맥 조립이
    #   항상 비어 있던 이유다.
    #
    #   키 자체를 안 넣으면 LangGraph 가 이 채널을 건드리지 않고, 체크포인트에 있던
    #   이전 값이 그대로 살아남는다. 값을 넘기고 싶은 호출부(테스트 등)를 위해 인자는
    #   남겨두되, None 이면 아무것도 하지 않는다.
    if conversation_id is not None:
        inputs["conversation_id"] = conversation_id

    try:
        with timer.activate(), timer.stage("graph"):
            state = app.invoke(inputs, thread)
    except Exception:  # noqa: BLE001 - 한 턴의 실패가 루프를 죽이면 안 된다
        logger.exception("turn failed for senior=%s", senior_id)
        # 실패한 턴의 시간은 저하 판단에 넣지 않는다. 예외로 0.1초에 끝난 턴이
        # '빠른 턴'으로 세어지면, 고장 중에 저하가 풀린다.
        timer.finish(senior_id=senior_id, intent="error")
        return {}

    elapsed = timer.finish(senior_id=senior_id, intent=str(state.get("intent") or ""))
    # 저하 단계는 어르신이 실제로 느끼는 것(왕복 시간)으로 움직인다 (S15P11E102-212).
    # 8GB 램이 얼마나 찼는지는 어르신에게 아무 의미가 없고, 대답이 4초 뒤에 오는 것은
    # 의미가 있다.
    degradation.note_turn_latency(elapsed)
    return state
