"""백엔드 문맥 조립 API 클라이언트 — 어르신의 '사실과 기억'으로 가는 유일한 길.

db/ 와의 경계  ★ 혼동 주의
    db/medical_repository.py = 의료 '참조' 데이터(병원·약국·의약품 허가). 정확·지오
        조회이며 그 경로는 유지한다.
    이 모듈                  = 어르신의 사실과 기억(프로필, memory, care_record).
        반드시 백엔드 API 를 통한다. ssh_tunnel 로 기억을 직접 조회하지 않는다.
    섞으면 선필터·visibility·동의 규칙의 구현이 두 곳이 된다 (CLAUDE.md §5).

이 모듈의 규칙: 예외를 밖으로 던지지 않는다
    문맥 조회 실패는 턴을 '중단'시키는 것이 아니라 '저하'시켜야 한다. 네트워크가
    끊겼다고 로봇이 벙어리가 되면, 하필 그 순간이 말이 가장 필요한 순간일 수 있다.
    실패하면 캐시로 내려가고, 캐시도 없으면 빈 문맥으로 계속 간다.

참고
    CLAUDE.md §5 (API 이음새), §8 (RAG 경계), §18 (오프라인은 안전 문제다)
    S15P11E102-203 (서버 측 구현)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from bomi_ai_chat import policy
from bomi_ai_chat.backend_client.session import build_backend_session
from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.http import (
    ExternalServiceError,
    decode_json_object,
    is_auth_failure,
    request_with_retry,
)
from bomi_ai_chat.localstore import context_cache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextResult:
    """문맥과, 그것을 어디서 얻었는지.

    is_cached 가 왜 결과의 일부인가
        호출부가 반드시 알아야 하는 값이기 때문이다. 캐시는 낡았을 수 있고, 낡은
        복약 정보를 단정적으로 말하는 것은 품질 문제가 아니라 안전 문제다.
        이 값이 ConvState 의 ctx_is_cached 가 되고, 프롬프트의 '주의' 섹션이 된다.
    """

    ctx: dict[str, Any]
    is_cached: bool


class BackendContextClient:
    """대화 문맥 조립 API 를 호출한다."""

    def __init__(
        self,
        settings: Settings | None = None,
        session: requests.Session | None = None,
    ):
        settings = settings or get_settings()
        self.base_url = settings.backend_base_url.rstrip("/")
        self.timeout_seconds = settings.backend_timeout_seconds
        self.max_attempts = settings.http_max_attempts
        self.backoff_seconds = settings.http_backoff_seconds
        self.max_backoff_seconds = settings.http_max_backoff_seconds
        self._session = session or build_backend_session(settings)

    def fetch_context(
        self,
        senior_id: str,
        *,
        query: str,
        conversation_id: str | None = None,
        top_k: int = policy.MEMORY_TOP_K,
        documents: bool = False,
    ) -> ContextResult:
        """이번 턴의 문맥을 가져온다. 실패하면 캐시로 내려간다.

        무엇을 하는가
            203 의 엔드포인트를 호출하고, 성공하면 캐시를 갱신한다. 실패하면 마지막
            캐시를 돌려주며 is_cached=True 를 세운다.

        왜 POST 인가
            요청에 어르신의 발화가 들어간다. 건강·개인 발화를 URL 에 실으면 액세스
            로그와 프록시에 남는다. 서버 쪽도 같은 이유로 POST 로 열려 있다.

        인자
            top_k: 성능 저하 모드에서 policy.MEMORY_TOP_K_DEGRADED 로 낮춰 부른다.
            documents: info 인텐트에서만 True. 잡담에 문서를 검색하면 지연을
                낭비하고 프롬프트를 오염시킨다 (CLAUDE.md §8).

        반환값
            ContextResult. 절대 예외를 던지지 않는다.
        """
        url = f"{self.base_url}/api/v1/seniors/{senior_id}/conversation-context"
        payload = {
            "query": query,
            "conversationId": conversation_id,
            "memoryTopK": top_k,
            "includeDocuments": documents,
        }

        try:
            response = request_with_retry(
                "POST",
                url,
                service="conversation-context",
                timeout_seconds=self.timeout_seconds,
                max_attempts=self.max_attempts,
                backoff_seconds=self.backoff_seconds,
                max_backoff_seconds=self.max_backoff_seconds,
                session=self._session,
                json=payload,
            )
            ctx = decode_json_object(response, service="conversation-context")
        except (ExternalServiceError, OSError, ValueError) as error:
            # 좁게 잡는다. 처음에는 Exception 을 통째로 잡았는데, 그러자 호출 인자를
            # 틀린 프로그래밍 오류까지 "네트워크 실패"로 둔갑해 캐시로 조용히
            # 내려갔다. 버그가 오프라인 동작처럼 보이면 아무도 못 찾는다.
            # 여기서 예외를 올리면 네트워크 한 번 끊긴 것으로 대화가 끝난다.
            if is_auth_failure(error):
                # 401/403 은 네트워크 장애가 아니라 설정 오류(시크릿 불일치/누락)다.
                # 아래 캐시 폴백과 똑같은 문구로 남으면, 배포 때 시크릿을 안 맞춘
                # 실수가 "그냥 오프라인이었나 보다"에 묻힌다(S15P11E102-307).
                logger.warning(
                    "AUTH FAILURE: backend rejected the shared secret (status=%s) "
                    "while fetching context for senior %s; falling back to cache — "
                    "this is a config problem, not a network outage. Check "
                    "BACKEND_SHARED_SECRET.",
                    error.status_code, senior_id,
                )
            else:
                logger.warning("context fetch failed (%s); falling back to cache", error)
            cached = context_cache.load(senior_id)
            if cached is None:
                # 캐시도 없다. 문맥 없이라도 말은 해야 한다.
                logger.warning("no cached context for %s; continuing with empty context",
                               senior_id)
                return ContextResult(ctx={}, is_cached=True)
            return ContextResult(ctx=cached, is_cached=True)

        context_cache.save(senior_id, ctx)
        return ContextResult(ctx=ctx, is_cached=False)
