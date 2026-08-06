"""계약 주도형 대화의 백엔드 이음새 — 온보딩과 재질의 (S15P11E102-227).

context_client 와 무엇이 다른가  ★ 먼저 읽을 것
    context_client 는 실패해도 예외를 던지지 않는다. 캐시로 내려가고, 캐시도 없으면
    빈 문맥으로 계속 간다. 네트워크가 끊겼다고 로봇이 벙어리가 되면 안 되기 때문이다.

    **이 모듈은 반대다. 실패하면 예외를 올린다.**

    계약을 서버가 강제하는데 서버에 못 닿으면 계약이 없는 상태다. 그 상태로 민감정보를
    물으면 안 된다. 캐시된 질문을 되풀이하면 이미 답한 것을 또 묻게 되고, 동의 문구가
    바뀌었는데 옛 문구로 동의를 받게 된다.

    그래서 두 모듈의 실패 방식이 다르다. 잡담은 얕아져도 되고, 계약은 미뤄야 한다.
    호출부는 BackendUnavailable 을 잡아 '조용히 넘어간다'로 처리한다.

None 과 예외의 뜻이 다르다
    None       서버가 "지금은 없다"고 답했다. 물을 질문이 없거나(204/completed),
               활성 후보가 없다. **정상이고 흔한 결과다.**
    예외        서버에 못 닿았다. 아무것도 하지 않는다.

    둘을 None 하나로 합치면 "오프라인이라 안 물었다"와 "물을 게 없어서 안 물었다"가
    구분되지 않고, 온보딩이 왜 진행되지 않는지 아무도 모르게 된다.

참고
    CLAUDE.md §12 (계약 주도형 대화), §5 (API 이음새)
    S15P11E102-227 (서버 측 구현), docs/database/onboarding-rest-environment-design.md
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from bomi_ai_chat.backend_client.session import build_backend_session
from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.http import (
    ExternalServiceError,
    decode_json_object,
    is_auth_failure,
    request_with_retry,
)

logger = logging.getLogger(__name__)


class BackendUnavailable(RuntimeError):
    """계약 API 에 닿지 못했다.

    누가 잡는가
        graph/handlers.py 의 계약 주도형 핸들러, 그리고 jobs/ticks.py 의 제안 투입.
        둘 다 '아무것도 하지 않는다'로 처리한다.

    왜 조용히 넘어가도 되는가
        온보딩과 재질의는 미뤄도 되는 일이다. 침묵 사다리나 T1 과 다르다 —
        저것들은 네트워크가 없을 때가 가장 중요한 순간이고, 이것은 다음 기회에
        다시 하면 된다 (CLAUDE.md §18 의 성능 저하 순서).
    """


class _ContractClient:
    """두 클라이언트가 공유하는 호출 규약."""

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

    def _call(self, method: str, path: str, *, service: str, **kwargs) -> dict[str, Any] | None:
        """한 번 호출한다. 204 는 None, 닿지 못하면 BackendUnavailable.

        주의사항
            예외를 좁게 잡는다. Exception 을 통째로 잡으면 호출 인자를 틀린
            프로그래밍 오류까지 "네트워크 실패"로 둔갑하고, 그러면 버그가
            오프라인 동작처럼 보여서 아무도 못 찾는다.
        """
        url = f"{self.base_url}{path}"
        try:
            response = request_with_retry(
                method,
                url,
                service=service,
                timeout_seconds=self.timeout_seconds,
                max_attempts=self.max_attempts,
                backoff_seconds=self.backoff_seconds,
                max_backoff_seconds=self.max_backoff_seconds,
                session=self._session,
                **kwargs,
            )
        except (ExternalServiceError, OSError, ValueError) as error:
            if is_auth_failure(error):
                # 호출부(ticks.py, handlers.py)는 BackendUnavailable 을 "조용히
                # 넘어간다"로 잡는다(logger.info 수준). 그러면 시크릿이 틀렸다는
                # 사실이 "그냥 온보딩/재질의를 미룬 것"과 구분 없이 지나간다.
                # 여기서 먼저 명확한 경고를 남겨야 한다(S15P11E102-307).
                logger.warning(
                    "AUTH FAILURE: backend rejected the shared secret (status=%s) "
                    "calling %s; check BACKEND_SHARED_SECRET matches the backend "
                    "filter.",
                    error.status_code, service,
                )
            raise BackendUnavailable(f"{service} unreachable: {error}") from error

        # 204 No Content. "지금 물을 것이 없다"는 정상 응답이다.
        if response.status_code == 204 or not (response.content or b"").strip():
            return None

        try:
            return decode_json_object(response, service=service)
        except (ExternalServiceError, ValueError) as error:
            # 서버는 살아 있는데 응답이 계약과 다르다. 오프라인과 구분해서 올린다 —
            # 계약 불일치를 네트워크 문제로 착각하면 배포가 어긋난 것을 못 찾는다.
            raise BackendUnavailable(f"{service} returned an unusable body: {error}") from error


class BackendOnboardingClient(_ContractClient):
    """온보딩 세션을 진행한다. 상태 기계는 서버에 있다."""

    def start_or_resume(self, senior_id: str, robot_id: str) -> dict[str, Any] | None:
        """세션을 시작하거나 진행 중인 것을 이어받는다.

        앱에서 시작한 세션을 음성으로 이어받는 것이 이 호출의 존재 이유다.
        로봇이 새 세션을 만들지 결정하지 않는다 — 한 어르신의 진행 중 세션은 하나이고,
        그 판정은 서버가 한다.
        """
        return self._call(
            "POST", "/api/v1/robot/onboarding/sessions",
            service="robot-onboarding",
            json={"seniorId": senior_id, "robotId": robot_id},
        )

    def next_question(self, session_id: str) -> dict[str, Any] | None:
        """다음에 물을 질문 하나. 더 없으면 questionCode 가 None 이다.

        반환값
            {"questionCode": ..., "robotPrompt": ..., "requiredFields": [...],
             "sensitive": bool, "requiresConfirmation": bool, "status": ...}
            또는 물을 것이 없으면 None.

        주의사항
            로봇이 질문 순서를 정하지 않는다. 선행 동의가 없으면 서버가 동의 질문을
            먼저 내려준다. 여기서 순서를 손대는 코드가 생기면, 건강정보 동의 전에
            복약을 묻는 계약 위반이 기기 안에서 일어나고 아무도 감사할 수 없다.
        """
        body = self._call(
            "GET", f"/api/v1/robot/onboarding/sessions/{session_id}/next",
            service="robot-onboarding",
        )
        if body is None or not body.get("questionCode"):
            return None
        return body

    def submit_answer(
        self,
        session_id: str,
        question_code: str,
        answer_value: dict[str, Any],
        *,
        confirmed: bool,
        conversation_id: str | None = None,
        source_message_id: str | None = None,
    ) -> dict[str, Any] | None:
        """답변을 올리고 다음 행동을 받는다.

        인자
            confirmed: 어르신이 값을 '듣고' 명시적으로 확인했을 때만 True.
                침묵, 주제 변경, "글쎄", "아마도", 불명확한 STT, 다른 질문에 대한
                답변은 확인이 아니다. 그 판정은 graph/contract_dialogue.py 가 한다.

        반환값
            {"outcome": "ACCEPTED"|"NEEDS_CLARIFICATION"|"NEEDS_CONFIRMATION", ...}
        """
        return self._call(
            "POST", f"/api/v1/robot/onboarding/sessions/{session_id}/answers",
            service="robot-onboarding",
            json={
                "questionCode": question_code,
                "answerValue": answer_value,
                "confirmed": confirmed,
                "conversationId": conversation_id,
                "sourceMessageId": source_message_id,
            },
        )


class BackendClarificationClient(_ContractClient):
    """활성 fact_candidate 하나를 받아 재질의한다."""

    def active(self, senior_id: str) -> dict[str, Any] | None:
        """이 대화에서 물을 후보 하나. 없으면 None.

        서버가 하나만 내려준다. 로봇이 큐를 들지 않는 것이 계약이다 —
        보류된 사실 셋을 한꺼번에 물으면 어르신은 심문받는 기분이 된다.
        """
        return self._call(
            "GET", "/api/v1/robot/clarifications/active",
            service="robot-clarification",
            params={"seniorId": senior_id},
        )

    def answer(
        self,
        candidate_id: str,
        field_values: dict[str, Any],
        *,
        confirmed: bool,
        conversation_id: str | None = None,
        source_message_id: str | None = None,
    ) -> dict[str, Any] | None:
        """들은 값을 올리고 다음 행동을 받는다."""
        return self._call(
            "POST", f"/api/v1/robot/clarifications/{candidate_id}/answer",
            service="robot-clarification",
            json={
                "fieldValues": field_values,
                "confirmed": confirmed,
                "conversationId": conversation_id,
                "sourceMessageId": source_message_id,
            },
        )
