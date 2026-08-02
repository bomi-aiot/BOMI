"""현관 이벤트를 백엔드로 올리는 클라이언트.

왜 로봇이 판정하지 않고 올리는가
    방향(IN/OUT) 판정과 인사 결정은 백엔드 몫이다 (CLAUDE.md §11). 백엔드는 시나리오
    기록·오늘 일정·동의 상태를 가지고 있어 판단 근거가 그쪽에 있고, 로봇에서 같은
    판단을 다시 하면 같은 규칙이 두 곳에 생겨 갈라진다.

    그래서 로봇은 '사실'만 올린다. 무엇이 언제 도착했는가.

실패했을 때 재시도하지 않는다  ★ 의도된 결정
    outbox(보호자 알림)와 다르게 다룬다.

    이 이벤트로 만들 인사는 TTL 이 45초다(policy.GREETING_TTL_SEC). 네트워크가
    2분 끊겼다 돌아온 뒤에 문 이벤트를 재전송해도, 그 인사는 이미 폐기 대상이다.
    빈 현관에 "어서오세요"를 외치는 것보다는 못 보내는 편이 낫다.

    잃는 것은 외출 빈도 추세(T2)의 데이터 한 점이다. 추세는 기다릴 수 있다는 것이
    §11 의 분담 원칙이다. 안전 판정은 로봇 로컬에 남아 있으므로(door_watch_tick)
    전송 실패가 감시를 끄지는 않는다.

    → 이 공백은 docs/carebot/PROGRESS.md 에 기록한다. 문 이벤트 전용 큐가 필요해지면
      그때 만든다. 보호자 알림 outbox 에 섞으면 안 된다 — 그건 알림이 아니다.

참고
    CLAUDE.md §11 (현관), §18 (오프라인), S15P11E102-226 (백엔드 측 판정)
"""

from __future__ import annotations

import logging

import requests

from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.contracts.door import DoorEvent
from bomi_ai_chat.http import ExternalServiceError, request_with_retry

logger = logging.getLogger(__name__)


class BackendDoorClient:
    """현관 이벤트 전달 전용 클라이언트."""

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

    def forward_event(self, senior_id: str, event: DoorEvent) -> bool:
        """이벤트 하나를 백엔드에 올린다. 예외를 던지지 않는다.

        무엇을 보내는가
            정규화된 시각과 원본 시각을 **둘 다** 보낸다. 백엔드가 방향을 상관시킬 때
            쓰는 것은 정규화된 시각이지만, 라즈베리파이 시계가 어긋난 것을 서버 쪽에서도
            볼 수 있어야 한다.

        왜 max_attempts=1 인가
            위 모듈 docstring 참고. 늦게 도착한 문 이벤트는 가치가 거의 없고, 재시도로
            턴 지연 예산을 쓰는 쪽이 더 나쁘다.

        반환값
            True  전달됨.
            False 실패. 호출부는 계속 진행한다 — 로컬 재실 반영은 이미 끝나 있다.
        """
        url = f"{self.base_url}/api/v1/seniors/{senior_id}/door-events"
        payload = {
            "eventId": event.event_id,
            "type": event.type,
            "sourceId": event.source_id,
            # 권위 있는 시각. 백엔드의 방향 상관 판정이 이 값을 쓴다.
            "receivedAt": event.received_at,
            # 라즈베리파이가 주장한 시각. 참고용이며 서버도 계산에 쓰지 않는다.
            "reportedAt": event.reported_at,
            "direction": event.direction,
            "payload": dict(event.payload),
        }

        try:
            request_with_retry(
                "POST",
                url,
                service="door-events",
                timeout_seconds=self.timeout_seconds,
                max_attempts=1,
                backoff_seconds=self.backoff_seconds,
                max_backoff_seconds=self.max_backoff_seconds,
                session=self._session,
                json=payload,
            )
        except (ExternalServiceError, OSError, ValueError) as error:
            # 좁게 잡는다. Exception 을 통째로 잡으면 호출 인자를 틀린 프로그래밍
            # 오류까지 "네트워크 실패"로 둔갑하고, 버그가 오프라인 동작처럼 보인다.
            logger.warning(
                "door event forward failed (%s); the local occupancy update stands, "
                "but the backend cannot resolve direction for this event", error)
            return False

        return True
