"""마지막으로 성공한 대화 문맥의 로컬 사본.

왜 존재하는가
    네트워크가 끊기면 백엔드에서 문맥을 못 받는다. 캐시가 없으면 로봇은 어르신에
    대해 아무것도 모르는 상태로 대답하거나, 아예 대답하지 못한다. 안전 기기에서
    벙어리가 되는 것은 최악의 실패 양상이므로, 대신 '얕은 대화'를 받아들인다
    (CLAUDE.md §18).

무엇을 캐시하고 무엇을 캐시하지 않는가
    문맥 응답 전체를 어르신별로 하나만 둔다. 질의별로 캐시하지 않는다. 오프라인일
    때 필요한 것은 "이 질문에 딱 맞는 기억"이 아니라 "이 어르신이 누구인지"이고,
    질의별 캐시는 microSD 에 쓰기만 늘린다.

    이 캐시는 '사실의 권위'가 아니다. 낡을 수 있고, 그래서 이걸 쓴 턴은 반드시
    ctx_is_cached 로 표시된다. 표시가 프롬프트로 이어져 단정적 표현을 막는다.

참고
    CLAUDE.md §5 (소유권), §18 (오프라인 대비)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from bomi_ai_chat.clock import clock
from bomi_ai_chat.localstore import schema
from bomi_ai_chat.localstore.db import runtime_db

logger = logging.getLogger(__name__)


def save(senior_id: str, ctx: dict[str, Any]) -> None:
    """마지막으로 성공한 문맥을 덮어쓴다.

    누가 호출하는가
        backend_client.fetch_context 가 성공했을 때.

    주의사항
        쓰기 실패로 대화 턴을 망가뜨리지 않는다. 캐시는 있으면 좋은 것이고,
        지금 진행 중인 턴은 이미 성공한 응답을 들고 있다.
    """
    try:
        connection = runtime_db()
        schema.init_runtime(connection)
        connection.execute(
            "INSERT INTO context_cache (senior_id, payload, cached_at) VALUES (?, ?, ?) "
            "ON CONFLICT(senior_id) DO UPDATE SET "
            "payload = excluded.payload, cached_at = excluded.cached_at",
            (senior_id, json.dumps(ctx, ensure_ascii=False), clock.now()),
        )
    except Exception:  # noqa: BLE001 - 캐시 저장 실패가 턴을 중단시키면 안 된다
        logger.warning("context cache write failed for %s", senior_id, exc_info=True)


def load(senior_id: str) -> dict[str, Any] | None:
    """캐시된 문맥. 없으면 None.

    누가 호출하는가
        backend_client.fetch_context 가 백엔드에 닿지 못했을 때.

    주의사항
        여기서 None 이 돌아와도 예외를 던지지 않는다. 캐시도 없는 오프라인은
        '문맥 없이 대화'가 되며, 그래도 로봇은 말은 할 수 있어야 한다.
    """
    try:
        connection = runtime_db()
        schema.init_runtime(connection)
        row = connection.execute(
            "SELECT payload FROM context_cache WHERE senior_id = ?", (senior_id,)
        ).fetchone()
    except Exception:  # noqa: BLE001
        logger.warning("context cache read failed for %s", senior_id, exc_info=True)
        return None

    if row is None:
        return None
    try:
        return json.loads(row["payload"])
    except json.JSONDecodeError:
        # 깨진 캐시는 없는 것으로 취급한다. 여기서 예외를 올리면 오프라인 상황에서
        # 두 번 실패한다.
        logger.warning("context cache payload corrupt for %s; ignoring", senior_id)
        return None
