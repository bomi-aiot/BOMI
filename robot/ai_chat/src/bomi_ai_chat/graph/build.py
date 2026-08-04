"""그래프 배선. 노드와 엣지만 있다. 이 파일에 비즈니스 로직은 없다.

어디에 위치하는가
    조립 지점. 여기서 import 하는 모든 노드는 다른 곳에 정의되어 있고, 이 모듈은
    무엇 다음에 무엇이 실행되는지만 말한다.

왜 배선을 따로 분리하는가
    대화의 '형태'가 곧 설계다 (CLAUDE.md §6). 그것을 짧고 읽을 수 있는 한 파일에
    두면, "로봇이 게이트를 거치지 않고 말할 수 있는가?"를 일곱 모듈을 감사하는 대신
    40줄을 읽고 답할 수 있다. 여기에 if 문을 추가하고 있다면, 그건 노드에 속한다.

그래프를 읽는 방법
    네 진입 경로가 하나의 응답 파이프라인으로 수렴하고, 판단 노드가 생성 노드보다
    위에 있다.

        어르신 발화  -> note_interaction -> safety_triage -\
        스케줄러     -> proactive_gate ---------------------> context_read -> ...
        백엔드 명령  -> backend_command --------------------/
        현관 센서    -> door_event -> END

    세 개의 엣지가 일부러 일찍 종료되며, 이 파일에서 가장 중요한 엣지들이다.
        route_gate        -> END   게이트가 침묵을 선택했다
        route_interaction -> END   어르신이 "응"만 했다
        door_event        -> END   사실만 반영했다. 인사는 백엔드가 판정한다 (§11)

    백엔드 명령이 게이트를 '건너뛰는' 것이 의도다. 게이트는 "지금 말해도 되는가"를
    판정하고, 이 명령은 그 판정을 이미 한 쪽에서 왔다. 여기서 다시 판정하면 심판이
    둘이 되고, 백엔드가 보낸 인사가 로봇의 쿨다운에 조용히 삼켜진다.

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
        어르신의 발화와 로봇의 발화를 백엔드에 남기고, 쿨다운 게이트가 읽는
        타임스탬프를 찍는다.

    왜 추출을 인라인이 아니라 큐로 넘기는가
        추출은 임베딩 API 호출을 뜻하고, 어르신이 응답을 기다리는 동안 어제의 기억을
        저장할 이유는 전혀 없다. 턴 경로에서 빼는 것이 지연 예산을 지킨다
        (CLAUDE.md §16, §18).

    누가 호출하는가
        build.py, response_shaper 다음 emit 앞.

    반환값
        {"last_spoke_at": ..., "conversation_id": ..., "last_message_id": ...}
        conversation_id 와 last_message_id 는 얻었을 때만 넣는다 — 못 얻었으면 키
        자체를 빼서 체크포인트에 있던 이전 값이 그대로 남게 한다(state.py 참고).

    주의사항
        - 추출된 건강·복약 사실은 fact_candidate 로 가며, care_record 로 직행하지
          않는다 (CLAUDE.md §8).
        - 대화 적재는 실패해도 턴을 막지 않는다. 통계 때문에 대화를 망치지 않는다.
    """
    from bomi_ai_chat.clock import clock
    from bomi_ai_chat.localstore import runtime as runtime_store

    # TODO(jobs): 사실 추출을 큐에 넣고, 일간 지표를 버퍼링한다.
    now = clock.now()
    conversation_id, senior_message_id = _record_turn(state, now)

    # 내구 저장소에도 찍는다.
    #
    # 왜 checkpoint 만으로 부족한가
    #   재부팅 후 복원의 출처가 runtime_state 다. 여기 안 쓰면 로봇이 재시작한 직후
    #   쿨다운이 0 으로 보이고, 방금 말했는데도 알림이 바로 또 나간다.
    #   같은 이음이 note_interaction 과 door_event 에도 있다(ingress.py 참고).
    #
    # conversation_id 는 '얻었을 때만' 함께 찍는다 (S15P11E102-306). 실패해서 None 이
    # 돌아온 경우까지 여기 넣으면, 방금 전 턴이 남겨둔 유효한 id 를 실패 한 번으로
    # 지워버린다 — 스케줄러의 contract_tick 이 그 지워진 값을 읽는다
    # (jobs/scheduler.py). 경계를 넘어 '의도적으로' 비우는 결정은
    # graph/ingress._conversation_boundary 가 그 순간에 직접 한다.
    senior_id = state.get("senior_id")
    if senior_id:
        fields: dict = {"last_spoke_at": now}
        if conversation_id:
            fields["conversation_id"] = conversation_id
        runtime_store.save(senior_id, **fields)

    out: dict = {"last_spoke_at": now}
    if conversation_id:
        # 다음 턴이 같은 대화에 이어 붙도록 서버가 배정한 id 를 들고 간다.
        out["conversation_id"] = conversation_id
    if senior_message_id:
        # fact_candidate 추출(255)의 sourceMessageId 가 필요로 한다 (state.py 참고).
        out["last_message_id"] = senior_message_id
    return out


# 대화 적재 클라이언트. LLM 과 같은 이유로 지연 생성한다 — import 시점에 만들면
# 백엔드 주소가 없는 환경에서 모듈을 불러오는 것만으로 실패한다.
_CONVERSATION_CLIENT = None


def _conversation_client():
    global _CONVERSATION_CLIENT
    if _CONVERSATION_CLIENT is None:
        from bomi_ai_chat.backend_client import BackendConversationClient

        _CONVERSATION_CLIENT = BackendConversationClient()
    return _CONVERSATION_CLIENT


def set_conversation_client(client) -> None:
    """대화 적재 클라이언트를 교체한다. 테스트와 부트스트랩에서 쓴다."""
    global _CONVERSATION_CLIENT
    _CONVERSATION_CLIENT = client


def _record_turn(state: ConvState, now: float) -> tuple[str | None, str | None]:
    """이 턴을 백엔드에 남긴다. 실패해도 턴을 막지 않는다.

    무엇을 올리는가
        어르신이 말한 턴이면 두 행(어르신 + 로봇), 능동 턴이면 로봇 한 행.
        T2 요약의 발화량 지표가 이 행들에서 나온다 (S15P11E102-211).

    ★ 왜 어르신 발화를 먼저 올리는가
        서버가 순번을 매기므로 올린 순서가 곧 기록 순서다. 로봇 발화를 먼저 올리면
        나중에 대화를 읽을 때 로봇이 먼저 말한 것으로 보인다.

    ★ 왜 실패를 삼키는가
        발화량 지표는 유실돼도 생명에 지장이 없다. 기록을 남기지 못했다고 어르신에게
        대답을 못 하게 만들면, 통계 때문에 대화를 망치는 것이다.
        같은 이유로 outbox 에 넣지 않는다 — 거기에 통계를 섞으면 T1 알림이 통계 뒤에
        줄을 서게 된다 (backend_client/conversation_client.py).

    반환값
        (conversation_id, senior_message_id) — S15P11E102-306 에서 단일 값에서 넓혔다.

        conversation_id: 서버가 배정한 id. 이번 턴에서 아무것도 못 올렸으면 턴이
            시작될 때 들고 있던 값 그대로(둘 다 없으면 None).
        senior_message_id: '어르신 발화' 행에 대해 서버가 돌려준 메시지 id.
            어르신 발화가 없는 턴(능동 발화 등)에는 항상 None 이다 — 이 값은
            fact_candidate 추출(255)이 sourceMessageId 로 요구하는데, 그 사실은
            어르신이 실제로 한 말에서만 나와야 한다. 로봇 혼잣말에는 근거가 없다.
    """
    from bomi_ai_chat.graph import context as context_node

    senior_id = state.get("senior_id")
    if not senior_id:
        return None, None

    client = _conversation_client()
    conversation_id = state.get("conversation_id")
    senior_message_id: str | None = None
    trigger, priority = _provenance(state)

    utterance = (state.get("user_input") or "").strip()
    if state.get("trigger_type") == "user_utterance" and utterance:
        returned_conversation_id, returned_message_id = client.record_turn(
            senior_id,
            role="SENIOR",
            content=utterance,
            occurred_at=state.get("last_user_interaction_at") or now,
            conversation_id=conversation_id,
            trigger_type="USER",
            # 지남력 질문의 '반복'은 T2 추세로만 간다. 이 플래그가 프롬프트로
            # 되돌아가면 어조에 새어나가서 열 번째 답변이 짜증스럽게 들린다 (§8).
            orientation_question=context_node.is_orientation_question(utterance),
        )
        conversation_id = returned_conversation_id or conversation_id
        senior_message_id = returned_message_id

    spoken = (state.get("final_utterance") or state.get("response") or "").strip()
    if spoken:
        # 로봇 행의 messageId 는 여기서 버린다 — state 에 남기는 것은 '어르신' 행의
        # id 뿐이다(위 반환값 설명 참고).
        returned_conversation_id, _returned_robot_message_id = client.record_turn(
            senior_id,
            role="ROBOT",
            content=spoken,
            occurred_at=now,
            conversation_id=conversation_id,
            trigger_type=trigger,
            priority=priority,
        )
        conversation_id = returned_conversation_id or conversation_id

    return conversation_id, senior_message_id


def _provenance(state: ConvState) -> tuple[str, str | None]:
    """이 로봇 발화가 왜 나왔는지, 게이트가 어떤 우선순위를 줬는지.

    반응형 턴은 우선순위가 없다. 방금 말을 건 사람에게 대답하는 것은 게이트를 거치지
    않으므로, 우선순위를 붙이면 있지도 않았던 판정을 지어내는 것이다 (CLAUDE.md §7).
    """
    trigger_type = state.get("trigger_type")
    if trigger_type == "user_utterance":
        return "USER", None

    priority = state.get("speech_priority")
    normalized = str(priority).upper() if priority else None

    if trigger_type == "door_event" or state.get("intent") == "greeting":
        return "DOOR_EVENT", normalized
    if state.get("intent") == "clarification":
        return "CLARIFICATION", normalized
    origin = state.get("speech_origin") or ""
    if origin.startswith("silence_ladder"):
        return "SILENCE_PROBE", normalized
    return "SCHEDULE", normalized


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
    g.add_node("backend_command", ingress.backend_command)
    g.add_node("proactive_gate", proactive_gate)
    g.add_node("safety_triage", triage.safety_triage)
    g.add_node("safety_confirm", triage.safety_confirm)
    g.add_node("escalation", triage.escalation)
    g.add_node("context_read", context.context_read)
    g.add_node("classify_intent", context.classify_intent)
    for name in INTENTS:
        g.add_node(f"handle_{name}", getattr(handlers, f"handle_{name}"))
    g.add_node("response_shaper", output.response_shaper)
    g.add_node("memory_write", memory_write)
    g.add_node("emit", output.emit)

    # ── 진입: 네 경로 ────────────────────────────────────────────────────────
    g.add_conditional_edges(
        START,
        ingress.route_ingress,
        {
            "note_interaction": "note_interaction",
            "proactive_gate": "proactive_gate",
            "door_event": "door_event",
            "backend_command": "backend_command",
        },
    )

    # 문 이벤트는 여기서 끝난다.
    #
    # occupancy 는 노드 안에서 이미 반영됐다 — 사실에는 허락이 필요 없다. 그리고
    # 인사 제안을 만들지 않으므로 게이트를 마주할 것이 없다. 배웅·환영 판정은
    # 백엔드가 하고, 그 결과는 backend_command 로 들어온다 (CLAUDE.md §11).
    g.add_edge("door_event", END)

    # 백엔드 명령은 게이트를 건너뛰고 곧바로 파이프라인에 올라탄다.
    # 이유는 이 파일 상단 주석 참고. 정제기(§14)는 여전히 통과한다.
    g.add_edge("backend_command", "context_read")

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
        {
            "escalation": "escalation",
            # 확인 질문도 문맥 조회와 LLM 을 건너뛴다. "가슴이 아파" 직후에 로봇이
            # 무슨 말을 할지가 네트워크 상태에 달려서는 안 된다.
            "safety_confirm": "safety_confirm",
            "context_read": "context_read",
        },
    )
    g.add_edge("escalation", "response_shaper")
    g.add_edge("safety_confirm", "response_shaper")

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
