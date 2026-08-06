"""로그로만 내보내는 임시 어댑터 — 채널이 정해지기 전의 자리 표시자.

왜 이런 것이 있는가
    채널 구현(웹앱 푸시·SMS)은 후속 티켓이다. 그런데 그때까지 트리아지·사다리·
    일일 요약을 테스트할 수 없으면 안 된다. 이 어댑터가 있으면 "무엇이 언제 어떤
    티어로 나갔는가"를 지금 검증할 수 있다.

왜 조용한 no-op 이 아닌가
    아무것도 하지 않는 어댑터를 두면, 배포에서 실수로 이게 남았을 때 알림이 사라지는데
    아무 흔적이 없다. 안전 기기에서 그건 최악의 실패 모양이다. 그래서 최소한
    로그로는 요란하게 남긴다. T1 은 WARNING 으로 올려서 눈에 걸리게 한다.

주의사항
    운영에 이걸 쓰면 보호자는 아무것도 받지 못한다. 실제 채널이 붙기 전까지의
    임시 수단임을 잊지 말 것.

참고
    CLAUDE.md §9 (티어), §24 (보호자 채널 미결)
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class LoggingGuardianNotifier:
    """알림을 로그로만 남긴다. GuardianNotifier 를 만족한다."""

    def notify_guardian(self, tier: str, payload: dict[str, Any]) -> None:
        # T1 은 생명 안전이다. 실제 채널이 없는 상태를 운영자가 알아채야 하므로
        # 나머지 티어보다 높은 레벨로 남긴다.
        level = logging.WARNING if tier == "T1" else logging.INFO
        logger.log(
            level,
            "guardian notification not delivered (no channel configured): "
            "tier=%s payload=%s",
            tier,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
