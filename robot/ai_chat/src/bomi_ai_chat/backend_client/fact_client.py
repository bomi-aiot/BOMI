"""추출된 사실 후보를 백엔드에 제출하는 클라이언트 (S15P11E102-255).

conversation_client 와 무엇이 다른가  ★ 먼저 읽을 것
    conversation_client(대화 적재)는 실패해도 예외를 올리지 않는다. 발화량
    지표는 유실돼도 생명에 지장이 없고, 통계 때문에 대화를 망칠 이유가
    없기 때문이다.

    **이 모듈은 반대다. 실패하면 예외를 올린다.**

    이유는 큐 쪽에 있다. localstore.extraction 의 행은 "백엔드 제출까지
    성공했다"는 뜻으로만 extracted=1 이 되고 지워진다(jobs/ticks 참고). 여기서
    실패를 삼키면 jobs/ticks.extraction_flush 가 그 행을 성공으로 착각해
    지워버리고, 그 사실은 다시는 제출되지 않는다 — outbox 와 정반대 방향의
    실패다. outbox 는 "실패해도 잃으면 안 된다"이고, 여기는 "성공한 척하면
    안 된다"이다.

    contract_client(BackendUnavailable)와는 같은 방향이다. 다만 그쪽은 "서버가
    강제하는 계약이 없는 상태로 진행하면 안 된다"는 이유이고, 여기는 "큐 행을
    잘못 지우면 안 된다"는 이유다 — 근거는 다르지만 둘 다 침묵하지 않고 예외로
    알린다.

한 요청에 사실 하나
    서버의 POST /api/v1/robot/fact-candidates 는 사실 하나를 받아 후보 한 행을
    만든다(요청 본문이 곧 FactCandidateIntakeRequest 하나다). 그래서 이 모듈은
    사실 묶음을 받아 '사실마다 한 번씩' 호출한다. 중간에 하나가 실패하면 그
    자리에서 예외를 올린다 — 이미 성공한 앞의 것들은 서버에 남지만, 서버가
    (senior, source_message_id, factType) 조합으로 중복을 걸러내므로 다음
    flush 의 재시도가 같은 사실을 두 번 만들지 않는다.

참고
    CLAUDE.md §8 (사실은 fact_candidate 를 거친다), §12 (계약 실패 방식과 대비),
    S15P11E102-255 (이 API 의 서버 측 구현)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import requests

from bomi_ai_chat.backend_client.fact_contract import to_intake_payload
from bomi_ai_chat.backend_client.session import build_backend_session
from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.http import (
    ExternalServiceError,
    is_auth_failure,
    is_permanent_rejection,
    request_with_retry,
)

logger = logging.getLogger(__name__)


class FactSubmissionError(RuntimeError):
    """사실 후보 제출에 실패했다.

    누가 잡는가
        jobs.ticks.extraction_flush. 잡으면 그 큐 행을 extracted=1 로 표시하지
        '않고' 다음 flush 로 넘긴다 — 재시도가 이 예외의 존재 이유다.

    permanent
        재시도해도 결과가 달라지지 않는 실패인가 (S15P11E102-393). True 면
        호출부가 그 행을 포기로 닫는다(extraction.mark_given_up). 판정은
        is_permanent_rejection 이 하고, 기본값 False 는 "모르면 재시도" 다 —
        틀린 쪽으로 기울 때 기억을 잃지 않는 방향이다.
    """

    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


class BackendFactClient:
    """추출된 사실 후보 묶음을 한 번에 올린다."""

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

    def submit_fact_candidates(
        self,
        senior_id: str,
        *,
        conversation_id: str | None,
        source_message_id: str | None,
        facts: list[dict[str, Any]],
        now_local: datetime | None = None,
        utterance: str | None = None,
    ) -> None:
        """추출된 사실을 백엔드에 올린다. 실패하면 FactSubmissionError 를 올린다.

        인자
            source_message_id: 이 사실이 나온 '어르신 발화' 행의 id. 백엔드의
                FactCandidate.fromConversationMessage 가 이 값을 requireNonNull
                로 강제하므로(255 티켓 본문), 호출부(jobs/ticks)는 이 값이 없는
                행을 애초에 여기까지 들고 오지 않아야 한다 — 여기서는 값을
                검증하지 않고 그대로 실어 보낸다(빈 값이면 서버가 400 으로
                거절하고, 그 400 은 재시도해도 나아지지 않는다).
            facts: [{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}]
                형태(추출 프롬프트의 어휘). 서버 계약으로의 변환은
                fact_contract.to_intake_payload 가 맡는다. 빈 리스트면 아무것도
                하지 않는다 — 호출할 이유가 없다.
            utterance: 이 사실들이 나온 어르신 발화 **원문**. 약속의 요일 검산에만
                쓴다(fact_contract._appointment_starts_at). 모델이 만든 content 가
                아니라 원문이어야 채점이 성립한다.

        왜 max_attempts 를 설정값 그대로 쓰는가(conversation_client 와 다르게
        max_attempts=1 로 낮추지 않는가)
            이 호출은 턴 지연 예산(약 2초) 밖에 있다. extraction_flush 는
            배경 틱이라 몇 번 더 재시도해도 어르신을 기다리게 하지 않는다.
        """
        if not facts:
            return

        url = f"{self.base_url}/api/v1/robot/fact-candidates"
        for fact in facts:
            payload: dict[str, Any] = to_intake_payload(
                fact,
                senior_id=senior_id,
                conversation_id=conversation_id,
                source_message_id=source_message_id,
                now_local=now_local,
                utterance=utterance,
            )
            try:
                request_with_retry(
                    "POST",
                    url,
                    service="robot-fact-candidates",
                    timeout_seconds=self.timeout_seconds,
                    max_attempts=self.max_attempts,
                    backoff_seconds=self.backoff_seconds,
                    max_backoff_seconds=self.max_backoff_seconds,
                    session=self._session,
                    json=payload,
                )
            except (ExternalServiceError, OSError) as error:
                # 좁게 잡는다. Exception 을 통째로 잡으면 호출 인자를 틀린 프로그래밍
                # 오류까지 "네트워크 실패"로 둔갑한다(conversation_client 와 같은 원칙).
                if is_auth_failure(error):
                    logger.warning(
                        "AUTH FAILURE: backend rejected the shared secret (status=%s) "
                        "while submitting fact candidates; this is a config problem, "
                        "not a retryable failure. Check BACKEND_SHARED_SECRET.",
                        error.status_code,
                    )
                raise FactSubmissionError(
                    f"fact candidate submission failed: {error}",
                    # 400 처럼 "요청이 틀렸다"는 답은 재시도가 의미 없다. 호출부가
                    # 그 행을 포기로 닫아야 뒤에 쌓인 발화가 흐른다 (S15P11E102-393).
                    permanent=is_permanent_rejection(error),
                ) from error

    def cancel_conversation(self, senior_id: str, conversation_id: str) -> None:
        """"기억하지 마" — 이 대화의 미확정 후보를 서버에서도 닫는다 (S15P11E102-348).

        로컬 절반(localstore.extraction.forget_conversation)은 아직 안 보낸 대기
        행을 지우고, 이 호출이 이미 제출된 후보를 닫는다 — 둘이 합쳐져야 약속이
        온전히 지켜진다. 서버 쪽이 대화 단위·멱등이라(0건 취소도 200) 재시도
        중복 전송이 안전하다.

        실패하면 FactSubmissionError 를 올린다 — 제출과 같은 방향이다. 여기서
        삼키면 호출부(jobs/ticks)가 큐 행을 done 으로 착각해 지우고, 그 취소는
        다시는 시도되지 않는다.
        """
        url = f"{self.base_url}/api/v1/robot/fact-candidates/cancel"
        try:
            request_with_retry(
                "POST",
                url,
                service="robot-fact-cancel",
                timeout_seconds=self.timeout_seconds,
                max_attempts=self.max_attempts,
                backoff_seconds=self.backoff_seconds,
                max_backoff_seconds=self.max_backoff_seconds,
                session=self._session,
                json={"seniorId": senior_id, "conversationId": conversation_id},
            )
        except (ExternalServiceError, OSError) as error:
            if is_auth_failure(error):
                logger.warning(
                    "AUTH FAILURE: backend rejected the shared secret (status=%s) "
                    "while cancelling fact candidates. Check BACKEND_SHARED_SECRET.",
                    error.status_code,
                )
            raise FactSubmissionError(
                f"fact candidate cancellation failed: {error}"
            ) from error
