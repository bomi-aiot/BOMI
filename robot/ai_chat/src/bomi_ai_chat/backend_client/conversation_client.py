"""대화 이벤트를 백엔드에 적재하는 클라이언트 (S15P11E102-211).

왜 필요한가
    T2 요약의 발화량 지표(senior_utterance_count / robot_utterance_count)가
    conversation_message 행에서 나온다. 203 은 읽기 전용 문맥 조립만 만들었으므로,
    이 경로가 없으면 두 칸이 영원히 NULL 이고 보호자는 "오늘 누가 말을 했나"라는
    가장 기본적인 신호를 못 받는다.

★ 실패해도 예외를 올리지 않는다 — 계약 API 와 정반대
    contract_client 는 못 닿으면 예외를 올린다. 계약을 서버가 강제하는데 서버가
    없으면 계약이 없는 상태이고, 그 상태로 민감정보를 물으면 안 되기 때문이다.

    여기는 반대다. **발화량 지표는 유실돼도 생명에 지장이 없다.** 기록을 남기지
    못했다고 어르신에게 대답을 못 하게 만들면, 통계 때문에 대화를 망치는 것이다.
    실패하면 경고를 남기고 그 턴은 그대로 진행한다.

    같은 이유로 outbox 에 넣지 않는다. outbox 는 '잃으면 안 되는 것'을 위한 곳이고,
    거기에 통계를 섞으면 T1 알림이 통계 뒤에 줄을 서게 된다 (CLAUDE.md §18).

    → 이 공백은 docs/carebot/PROGRESS.md 에 기록한다.

참고
    CLAUDE.md §16 (지연 예산), §18 (오프라인), §19 (DB 작업)
    S15P11E102-211 (서버 측 수신 API)
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.http import (
    ExternalServiceError,
    decode_json_object,
    request_with_retry,
)

logger = logging.getLogger(__name__)


class BackendConversationClient:
    """턴 하나를 백엔드에 남긴다."""

    def __init__(
        self,
        settings: Settings | None = None,
        session: requests.Session | None = None,
    ):
        settings = settings or get_settings()
        self.base_url = settings.backend_base_url.rstrip("/")
        self.timeout_seconds = settings.backend_timeout_seconds
        self.backoff_seconds = settings.http_backoff_seconds
        self.max_backoff_seconds = settings.http_max_backoff_seconds
        self._session = session or requests

    def record_turn(
        self,
        senior_id: str,
        *,
        role: str,
        content: str,
        occurred_at: float,
        conversation_id: str | None = None,
        trigger_type: str | None = None,
        priority: str | None = None,
        orientation_question: bool | None = None,
    ) -> tuple[str | None, str | None]:
        """발화 하나를 올린다. 예외를 던지지 않는다.

        인자
            occurred_at: 말한 시각(epoch 초). 서버 도착 시각이 아니다 — 늦게 올라간
                턴이 엉뚱한 날로 집계되면 추세가 틀어진다.
            trigger_type: 왜 이 발화가 일어났는가. 로봇이 이미 안다. 서버가 본문을
                다시 분석하지 않도록 여기서 실어 보낸다.
            orientation_question: 어르신이 지남력 질문을 했는가.
                **None 은 False 가 아니다** — 분류하지 않았다는 뜻이고, 서버는 그것을
                "안 물었다"로 세지 않는다.

        왜 max_attempts=1 인가
            이 호출은 턴 지연 예산(약 2초) 안에 있다. 통계를 남기려고 어르신을
            기다리게 하지 않는다. 한 번 실패하면 그 턴의 기록은 포기한다.

        반환값
            (conversationId, messageId) — S15P11E102-306 에서 단일 값에서 넓혔다.
            실패하면 (None, None). 호출부(graph/build.py)는 conversationId 를 다음
            턴에 넘겨 같은 대화에 이어 붙이고, messageId 는 어르신 발화 행에 대해서만
            state 에 남긴다(fact_candidate 추출(255)의 sourceMessageId 근거).

            ★ messageId 는 아직 서버가 안 돌려줄 수 있다. 이 티켓 시점에는 백엔드가
              그 필드를 보내도록 바뀌지 않았다(255 번이 그 작업이다). body 에 없으면
              .get() 이 조용히 None 을 준다 — 로봇 쪽은 이미 그 None 을 다룰 준비가
              되어 있고, 서버가 나중에 필드를 채우기 시작하면 코드 변경 없이 이어진다.
        """
        url = f"{self.base_url}/api/v1/robot/conversation-events"
        payload: dict[str, Any] = {
            "seniorId": senior_id,
            "conversationId": conversation_id,
            "role": role,
            "content": content,
            "occurredAt": _to_iso(occurred_at),
            "triggerType": trigger_type,
            "priority": priority,
            "orientationQuestion": orientation_question,
        }

        try:
            response = request_with_retry(
                "POST",
                url,
                service="conversation-events",
                timeout_seconds=self.timeout_seconds,
                max_attempts=1,
                backoff_seconds=self.backoff_seconds,
                max_backoff_seconds=self.max_backoff_seconds,
                session=self._session,
                json=payload,
            )
            body = decode_json_object(response, service="conversation-events")
        except (ExternalServiceError, OSError, ValueError) as error:
            # 좁게 잡는다. Exception 을 통째로 잡으면 호출 인자를 틀린 프로그래밍
            # 오류까지 "네트워크 실패"로 둔갑한다.
            logger.warning(
                "conversation event not recorded (%s); the turn continues, but the T2 "
                "utterance count will be short by one", error)
            return None, None

        return body.get("conversationId"), body.get("messageId")


def _to_iso(epoch_seconds: float) -> str:
    """epoch 초를 타임존이 붙은 ISO 8601 로.

    타임존 없이 보내면 서버가 자기 시간대로 해석하고, 자정 근처 발화가 엉뚱한 날로
    집계된다. UTC 로 명시해서 보내고 서버가 어르신의 로컬 날짜로 환산한다
    (CLAUDE.md §11, §15).
    """
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat()
