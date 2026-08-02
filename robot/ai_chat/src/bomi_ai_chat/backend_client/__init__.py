"""백엔드 API 클라이언트 — 어르신의 사실과 기억은 전부 여기를 통한다.

검색의 권위는 백엔드에 있다. 로봇은 벡터 검색을 직접 하지 않는다 (CLAUDE.md §5).
의료 '참조' 조회(병원·약국·의약품)는 db/ 가 계속 담당한다. 둘을 섞지 않는다.
"""

from bomi_ai_chat.backend_client.context_client import (
    BackendContextClient,
    ContextResult,
)
from bomi_ai_chat.backend_client.door_client import BackendDoorClient

__all__ = ["BackendContextClient", "BackendDoorClient", "ContextResult"]
