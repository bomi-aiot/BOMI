"""사람 탐지 결과의 외부 라이브러리 독립적인 계약을 정의한다.

좌표는 원본 입력 프레임의 픽셀 좌표이며 OpenCV나 Ultralytics 객체를
도메인 계층에 노출하지 않는다.
"""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PersonDetection:
    """한 명의 사람 탐지 결과를 표현한다.

    ``confidence``는 0.0 이상 1.0 이하의 탐지 신뢰도다. ``x1``, ``y1``은
    입력 프레임에서 바운딩 박스의 왼쪽 위 픽셀 좌표이고 ``x2``, ``y2``는
    오른쪽 아래 픽셀 좌표다.

    Raises:
        ValueError: 신뢰도나 좌표가 유한하지 않거나 유효 범위를 벗어난 경우.
    """

    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        """신뢰도와 바운딩 박스 계약을 검증한다.

        Raises:
            ValueError: 값이 유한하지 않거나 박스의 너비 또는 높이가 양수가 아닌 경우.
        """
        values = (self.confidence, self.x1, self.y1, self.x2, self.y2)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Detection values must be finite numbers.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Detection confidence must be between 0.0 and 1.0.")
        if self.x1 < 0.0 or self.y1 < 0.0:
            raise ValueError("Detection coordinates must not be negative.")
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("Detection bounding box must have a positive width and height.")
