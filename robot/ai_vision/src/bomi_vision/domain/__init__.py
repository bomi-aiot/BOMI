"""외부 비전 라이브러리와 무관한 핵심 데이터 구조를 제공한다."""

from bomi_vision.domain.detection import PersonDetection
from bomi_vision.domain.position import (
    UserPosition,
    VisionPositionResult,
    VisionResultStatus,
)

__all__ = [
    "PersonDetection",
    "UserPosition",
    "VisionPositionResult",
    "VisionResultStatus",
]
