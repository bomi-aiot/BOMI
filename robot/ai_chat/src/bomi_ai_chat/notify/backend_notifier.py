"""보호자 알림을 백엔드로 전달하는 어댑터 (S15P11E102-211).

★ 왜 로봇이 푸시 서버에 직접 보내지 않는가
    자격증명을 로봇에 놓으면 푸시 토큰이 기기마다 내려가고, **로봇 한 대가 털리면
    그 토큰도 함께 털린다.** 어르신 집에 놓인 기기는 서버보다 물리적으로 훨씬
    가져가기 쉽다.

    그래서 로봇은 전달만 하고, 보호자에게 닿는 것은 서버가 한다. 채널이 웹앱이든
    푸시든 SMS든 로봇 코드는 바뀌지 않는다 (CLAUDE.md §24 는 채널을 미결로 둔다).

동의 판정을 여기서 하지 않는다
    T2·T3 의 동의 확인은 서버 몫이다. 어댑터가 판단하게 두면 채널마다 안전 규칙이
    갈라지고, 로봇에 없는 데이터(guardian_sharing_consent_status)를 로봇이 알아야
    한다 (notify/base.py).

★ 거절과 실패를 구분한다 — 이 파일에서 가장 중요한 부분
    서버가 "동의가 없어 보내지 않는다"고 답하는 것은 **실패가 아니다.** 그것을
    NotifyError 로 올리면 outbox 가 영원히 재시도하고, 매 재시도가 배터리를 깎는
    라디오 깨우기가 된다. 그리고 그 결정은 재시도로 바뀌지 않는다.

    반대로 네트워크 단절은 반드시 NotifyError 여야 한다. 조용히 성공 처리하면
    T1 알림이 사라지고, 하필 그 순간이 알림이 가장 중요한 순간이다.

참고
    CLAUDE.md §9 (티어와 동의), §18 (발신 큐), §20 (어댑터 규칙)
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
from bomi_ai_chat.notify.base import NotifyError

logger = logging.getLogger(__name__)


class BackendGuardianNotifier:
    """알림 하나를 백엔드에 올린다. outbox 만 이 클래스를 부른다."""

    def __init__(
        self,
        senior_id: str,
        settings: Settings | None = None,
        session: requests.Session | None = None,
    ):
        settings = settings or get_settings()
        self.senior_id = senior_id
        self.base_url = settings.backend_base_url.rstrip("/")
        self.timeout_seconds = settings.backend_timeout_seconds
        self.max_attempts = settings.http_max_attempts
        self.backoff_seconds = settings.http_backoff_seconds
        self.max_backoff_seconds = settings.http_max_backoff_seconds
        self._session = session or requests

    def notify_guardian(self, tier: str, payload: dict[str, Any]) -> None:
        """알림을 전달한다. 재시도할 만한 실패에만 NotifyError 를 던진다.

        무엇을 하는가
            서버에 올리고, 응답의 delivered 를 확인한다.

        왜 delivered=False 에 예외를 던지지 않는가
            서버가 접수는 했고 보호자에게 전달만 하지 않은 상태다. 이유는 둘뿐이다.
                CONSENT_NOT_GRANTED  동의가 없다. 재시도로 바뀌지 않는다
                NO_GUARDIAN          아직 연결된 보호자가 없다. 마찬가지다
            둘 다 로봇이 할 수 있는 일이 없으므로 큐에서 내려놓는다. 기록은 서버에
            남아 있어서, 동의를 받거나 보호자가 연결되면 그때 화면에 나타난다.

        주의사항
            payload 에 어르신의 발화 원문을 넣지 않는다. 보호자에게 필요한 것은
            "가서 봐 주세요"이지 원문이 아니고, 원문을 실으면 T4("우리끼리 얘기")가
            T1 알림에 묻어 나가는 경로가 생긴다 (CLAUDE.md §9).
            지금 이 어댑터는 payload 를 그대로 전달하므로, 그 규칙은 payload 를
            만드는 쪽(graph.triage.escalation, jobs.ticks)이 지킨다.
        """
        url = f"{self.base_url}/api/v1/robot/guardian-alerts"
        body = {"seniorId": self.senior_id, "tier": tier, "payload": payload}

        try:
            response = request_with_retry(
                "POST",
                url,
                service="guardian-alerts",
                timeout_seconds=self.timeout_seconds,
                max_attempts=self.max_attempts,
                backoff_seconds=self.backoff_seconds,
                max_backoff_seconds=self.max_backoff_seconds,
                session=self._session,
                json=body,
            )
        except (ExternalServiceError, OSError, ValueError) as error:
            # 좁게 잡는다. Exception 을 통째로 잡으면 호출 인자를 틀린 프로그래밍
            # 오류까지 "네트워크 실패"로 둔갑하고, 그러면 버그가 오프라인 동작처럼
            # 보여서 아무도 못 찾는다 (backend_client/context_client.py 와 같은 이유).
            raise NotifyError(f"guardian alert not delivered: {error}") from error

        _log_outcome(tier, response)


def _log_outcome(tier: str, response) -> None:
    """서버가 실제로 보호자에게 닿았는지 로그로 남긴다.

    본문을 못 읽어도 실패로 보지 않는다. 서버는 201 로 접수를 확정했고, 여기서
    NotifyError 를 던지면 이미 접수된 알림을 다시 보내게 된다.
    """
    try:
        outcome = decode_json_object(response, service="guardian-alerts")
    except (ExternalServiceError, ValueError):
        logger.info("%s alert accepted (response body unreadable)", tier)
        return

    if outcome.get("delivered"):
        logger.info("%s alert delivered to the guardian", tier)
        return

    reason = outcome.get("reason") or "unspecified"
    if tier == "T1":
        # T1 이 보호자에게 못 닿는 것은 조용히 지나가서는 안 되는 상태다.
        # 재시도로 풀리지 않으므로 사람이 봐야 한다.
        logger.warning(
            "T1 alert was accepted but will NOT reach anyone (%s). "
            "Check the guardian connection and sharing consent.", reason)
    else:
        logger.info("%s alert accepted but not delivered (%s)", tier, reason)
