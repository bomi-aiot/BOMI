"""기기 경계를 넘는 메시지의 형태 — 로봇이 남과 주고받는 것만 여기 있다.

왜 별도 패키지인가
    이 안의 스키마는 우리 마음대로 바꿀 수 없다. 라즈베리파이 펌웨어와 백엔드가
    같은 모양을 알고 있어야 하고, 세 곳이 동시에 배포되지 않는다. 그래서 내부
    자료구조(state.py)와 섞지 않고 한곳에 모아 둔다.

    내부 구조를 바꾸는 것은 리팩터링이고, 이 안의 필드를 바꾸는 것은 **호환성 결정**이다.
    파일을 나눠 두면 리뷰에서 그 차이가 보인다.

참고
    docs/mqtt/topic-convention.md (봉투 규약), CLAUDE.md §11(현관), §24(미결 항목)
"""

from bomi_ai_chat.contracts.door import (
    DOOR_EVENT_TYPES,
    DoorEvent,
    DoorEventError,
    parse_door_event,
)

__all__ = [
    "DOOR_EVENT_TYPES",
    "DoorEvent",
    "DoorEventError",
    "parse_door_event",
]
