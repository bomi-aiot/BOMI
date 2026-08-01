"""그래프 배선. 노드와 엣지만 있다. 이 파일에 비즈니스 로직은 없다.

어디에 위치하는가
    조립 지점. 여기서 import 하는 모든 노드는 다른 곳에 정의되어 있고, 이 모듈은
    무엇 다음에 무엇이 실행되는지만 말한다.

왜 배선을 따로 분리하는가
    대화의 '형태'가 곧 설계다 (CLAUDE.md §6). 그것을 짧고 읽을 수 있는 한 파일에
    두면, "로봇이 게이트를 거치지 않고 말할 수 있는가?"를 일곱 모듈을 감사하는 대신
    40줄을 읽고 답할 수 있다. 여기에 if 문을 추가하고 있다면, 그건 노드에 속한다.

그래프를 읽는 방법
    세 진입 경로가 하나의 응답 파이프라인으로 수렴하고, 판단 노드가 생성 노드보다
    위에 있다.

        어르신 발화  -> note_interaction -> safety_triage -\
        스케줄러     -> proactive_gate ---------------------> context_read -> ...
        현관 센서    -> door_event -> proactive_gate -------/

    두 개의 엣지가 일부러 일찍 종료되며, 이 파일에서 가장 중요한 엣지들이다.
        route_gate        -> END   게이트가 침묵을 선택했다
        route_interaction -> END   어르신이 "응"만 했다

참고
    CLAUDE.md §6 (아키텍처), §7 (게이트), §22 (개발 순서)
"""

from __future__ import annotations

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from bomi_ai_chat.graph import context, handlers, ingress, output, triage
from bomi_ai_chat.graph.gate import proactive_gate, route_gate
from bomi_ai_chat.localstore.db import runtime_db_path
from bomi_ai_chat.state import ConvState

# 일곱 개의 핸들러 인텐트. 한 곳에 두어서 라우터 매핑과 아래의 수렴 엣지가
# 서로 어긋날 수 없게 한다.
INTENTS = [
    "info",
    "companion",
    "schedule",
    "emotional",
    "greeting",
    "onboarding",
    "clarification",
]


def memory_write(state: ConvState) -> dict:
    """턴을 기록하고 last_spoke_at 을 찍는다.

    무엇을 하는가
        로봇의 발화를 저장하고, 사실 추출을 큐에 넣고, 쿨다운 게이트가 읽는 타임스탬프를
        찍는다.

    왜 추출을 인라인이 아니라 큐로 넘기는가
        추출은 임베딩 API 호출을 뜻하고, 어르신이 응답을 기다리는 동안 어제의 기억을
        저장할 이유는 전혀 없다. 턴 경로에서 빼는 것이 지연 예산을 지킨다
        (CLAUDE.md §16, §18).

    누가 호출하는가
        build.py, response_shaper 다음 emit 앞.

    반환값
        {"last_spoke_at": ...}

    주의사항
        - 추출된 건강·복약 사실은 fact_candidate 로 가며, care_record 로 직행하지
          않는다 (CLAUDE.md §8).
        - 이벤트 로그 쓰기는 매 턴 쓰지 말고 버퍼링한다. 이 하드웨어의 저장 매체는
          microSD 이고, 끊임없는 작은 쓰기가 그것을 죽인다 (CLAUDE.md §18).
    """
    from bomi_ai_chat.clock import clock

    # TODO(backend_client): trigger_type 과 priority 를 붙여 conversation_message 를
    #   추가한다. 사후에 "왜 로봇이 새벽 3시에 말했는가"에 답하고, 표현 다양화를 위한
    #   최근 문구를 조회할 수 있게 된다 (CLAUDE.md §19).
    # TODO(jobs): 사실 추출을 큐에 넣고, 일간 지표를 버퍼링한다.
    return {"last_spoke_at": clock.now()}


def build_graph(checkpoint_path: str | None = None):
    """대화 그래프를 컴파일한다.

    무엇을 하는가
        모든 노드를 등록하고, 엣지를 배선하고, checkpointer 를 붙인다.

    왜 checkpointer 가 로컬 SQLite 인가
        매 턴 쓰기가 일어난다. 서버 DB 를 가리키면 턴마다 네트워크 왕복이 붙고 로봇이
        오프라인에서 동작하지 못한다. 프레임워크 내부 상태이고 업무 사실이 아니므로,
        백엔드 ERD 에 속하지 않고 Flyway 관리 대상도 아니다 (CLAUDE.md §5).

    인자
        checkpoint_path: 로컬 SQLite 파일. None 이면 localstore 의 runtime DB 를
            쓴다. 그게 기본값인 이유는, 운영 상태가 한 파일에 모여 있으면 일일 덤프가
            디렉터리 하나만 복사하면 되고 SD카드 교체 시 옮길 대상이 명확해지기
            때문이다. 테스트만 별도 경로를 넘긴다.

    반환값
        컴파일된 그래프. 어르신별 thread_id 로 호출한다.
            app.invoke({...}, config={"configurable": {"thread_id": senior_id}})

    주의사항
        thread_id 는 곧 어르신 id 다. 잘못 넣으면 두 어르신이 침묵 사다리를 공유하게
        되는데, 안전 시스템에서 그것은 한 사람의 발화가 다른 사람의 에스컬레이션을
        억제한다는 뜻이다.

        SqliteSaver.from_conn_string() 을 쓰지 않는다. 그건 컨텍스트 매니저라서
        with 블록을 벗어나면 연결을 닫는다. 이 프로세스는 몇 시간 동안 살아 있어야
        하므로 연결을 직접 소유한다.
    """
    g = StateGraph(ConvState)

    # ── 노드 ─────────────────────────────────────────────────────────────────
    g.add_node("note_interaction", ingress.note_interaction)
    g.add_node("door_event", ingress.door_event)
    g.add_node("proactive_gate", proactive_gate)
    g.add_node("safety_triage", triage.safety_triage)
    g.add_node("escalation", triage.escalation)
    g.add_node("context_read", context.context_read)
    g.add_node("classify_intent", context.classify_intent)
    for name in INTENTS:
        g.add_node(f"handle_{name}", getattr(handlers, f"handle_{name}"))
    g.add_node("response_shaper", output.response_shaper)
    g.add_node("memory_write", memory_write)
    g.add_node("emit", output.emit)

    # ── 진입: 세 경로 ────────────────────────────────────────────────────────
    g.add_conditional_edges(
        START,
        ingress.route_ingress,
        {
            "note_interaction": "note_interaction",
            "proactive_gate": "proactive_gate",
            "door_event": "door_event",
        },
    )

    # 문 이벤트: occupancy 는 노드 안에서 이미 반영됐다(사실에는 허락이 필요 없다).
    # 이제 인사 제안만 게이트를 마주한다.
    g.add_edge("door_event", "proactive_gate")

    # 능동: 말하거나, 침묵한다. END 분기가 이 설계의 핵심이다.
    g.add_conditional_edges(
        "proactive_gate", route_gate, {"context_read": "context_read", END: END}
    )

    # 반응: 맞장구면 응답 없이 턴을 끝낸다.
    g.add_conditional_edges(
        "note_interaction",
        ingress.route_interaction,
        {"safety_triage": "safety_triage", END: END},
    )

    # T1 은 인텐트 라우터를 완전히 건너뛴다. 응급이 검색이나 LLM 의 성공에
    # 의존해서는 안 된다.
    g.add_conditional_edges(
        "safety_triage",
        triage.route_triage,
        {"escalation": "escalation", "context_read": "context_read"},
    )
    g.add_edge("escalation", "response_shaper")

    # ── 공통 파이프라인 ──────────────────────────────────────────────────────
    g.add_edge("context_read", "classify_intent")
    g.add_conditional_edges(
        "classify_intent",
        context.route_intent,
        {f"handle_{n}": f"handle_{n}" for n in INTENTS},
    )
    for name in INTENTS:
        g.add_edge(f"handle_{name}", "response_shaper")

    # 로봇이 말하는 모든 것은 정제기를 통과한다. 예외 없다.
    g.add_edge("response_shaper", "memory_write")
    g.add_edge("memory_write", "emit")
    g.add_edge("emit", END)

    # checkpointer = LangGraph 가 thread_id(= 어르신 id) 별로 state 를 저장하는 장치.
    # 이것이 있어서 silence_level 과 last_spoke_at 이 턴과 재부팅을 넘어 살아남는다.
    #
    # check_same_thread=False 인 이유
    #   그래프를 호출하는 스레드가 하나가 아니다. emit 의 재생은 그래프 실행보다
    #   오래 살고(§13), 침묵 틱과 현관 감시는 스케줄러 스레드에서 돌아온다(§15).
    #   기본값(True)이면 그때 sqlite3 가 ProgrammingError 를 던진다.
    path = checkpoint_path if checkpoint_path is not None else str(runtime_db_path())
    conn = sqlite3.connect(path, check_same_thread=False)
    return g.compile(checkpointer=SqliteSaver(conn))


def thread(senior_id: str) -> dict:
    """어르신 한 명에 대한 호출 설정. 직접 손으로 쓰지 말고 항상 이 함수를 쓴다."""
    return {"configurable": {"thread_id": senior_id}}
