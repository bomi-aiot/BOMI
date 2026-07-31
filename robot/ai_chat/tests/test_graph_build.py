"""그래프 배선이 실제로 컴파일되는지 검증한다.

왜 이 테스트가 있는가
    배선은 이 티켓의 구조적 산출물이고, 뼈대 단계에서 깨져 있으면 다음 티켓들이
    전부 그 위에 쌓인다. 그런데 배선 오류는 import 만으로는 드러나지 않는다.
    compile() 을 실제로 불러야 checkpointer 타입 오류와 존재하지 않는 노드를
    가리키는 엣지가 잡힌다.

    실제로 이 테스트가 처음 잡은 것은 checkpointer 였다. SqliteSaver.from_conn_string()
    은 컨텍스트 매니저를 돌려주기 때문에 그대로 compile() 에 넘기면 TypeError 다.

무엇을 확인하지 '않는가'
    노드의 동작. 이 시점의 핸들러는 전부 스텁이고 일부는 의도적으로
    NotImplementedError 다. 여기서는 '형태'만 본다.

참고
    CLAUDE.md §5 (checkpointer 는 로컬 SQLite), §6 (아키텍처)
"""

from langgraph.graph import END

from bomi_ai_chat.graph.build import INTENTS, build_graph, thread


def test_graph_compiles(tmp_path):
    """배선이 컴파일된다 — 존재하지 않는 노드를 가리키는 엣지가 없다."""
    app = build_graph(checkpoint_path=str(tmp_path / "checkpoint.sqlite"))

    assert app is not None


def test_checkpointer_is_attached_and_local(tmp_path):
    """checkpointer 가 붙어 있고, 로컬 파일에 만들어진다.

    서버 DB 를 가리키면 매 턴 네트워크 왕복이 붙어 지연 예산이 무너지고 오프라인에서
    죽는다(CLAUDE.md §5). 그래서 '파일이 생겼는지'가 의미 있는 확인이다.
    """
    path = tmp_path / "checkpoint.sqlite"
    app = build_graph(checkpoint_path=str(path))

    assert app.checkpointer is not None
    assert path.exists(), "로컬 SQLite 파일이 만들어져야 한다"


def test_every_intent_has_a_handler_node():
    """INTENTS 표와 실제 핸들러가 어긋나지 않는다.

    어긋나면 build_graph 가 컴파일 단계에서 터진다. 그 실패를 여기서 이름으로
    확인해두면 원인을 찾는 시간이 줄어든다.
    """
    from bomi_ai_chat.graph import handlers

    for name in INTENTS:
        assert hasattr(handlers, f"handle_{name}"), f"handle_{name} 이 없다"


def test_silence_is_a_terminal_path(tmp_path):
    """게이트의 침묵 분기가 END 로 이어져 있다.

    '말하지 않기로 결정하는 것도 기능이다'(CLAUDE.md §7). 침묵은 emit 에 도달하지
    않는 것으로 표현되므로, 이 엣지가 사라지면 로봇이 침묵할 수 없게 된다.
    """
    app = build_graph(checkpoint_path=str(tmp_path / "checkpoint.sqlite"))
    graph = app.get_graph()

    # proactive_gate 에서 나가는 엣지 중 하나는 반드시 END 여야 한다.
    targets = {e.target for e in graph.edges if e.source == "proactive_gate"}
    assert END in targets or "__end__" in targets, (
        f"게이트에서 END 로 가는 엣지가 없다. 실제 대상: {targets}"
    )


def test_thread_config_uses_senior_id():
    """thread_id 는 어르신 id 다.

    잘못 넣으면 두 어르신이 침묵 사다리를 공유하고, 한 사람의 발화가 다른 사람의
    에스컬레이션을 억제한다. 안전 시스템에서 이것은 조용한 실패다.
    """
    assert thread("senior-42") == {"configurable": {"thread_id": "senior-42"}}
