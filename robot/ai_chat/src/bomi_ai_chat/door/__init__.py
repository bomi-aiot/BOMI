"""현관 신호 — 로봇이 센서로부터 알 수 있는 것과, 알 수 없는 것.

이 패키지의 한 문장 요약
    **로봇은 방향을 판정하지 않는다.** 문에서 무슨 일이 있었다는 사실만 반영하고,
    그것이 귀가인지 외출인지는 백엔드가 정해서 내려준다 (CLAUDE.md §11).

모듈
    occupancy  재실 상태 규칙. 순수 함수 + 내구 저장 반영
    intake     들어온 이벤트 하나를 처리한다(하트비트, 문 개폐, 보수적 재실, 전달)
    mqtt       브로커 구독 어댑터. 기본 비활성이며 paho-mqtt 를 선택 의존으로 쓴다

왜 로봇이 재실 상태를 아예 안 들고 있으면 안 되는가
    침묵 사다리가 매 틱 이 값을 읽고, 네트워크 없이도 돌아야 한다 (§10, §18).
    그런데 방향이 없으면 Jetson 은 HOME 과 AWAY 를 구분할 수 없다. 그래서 항상 안전한
    한 가지를 한다 — 문에 무슨 일이 있으면 UNKNOWN 으로 두고, 사다리는 그것을
    '보수적으로 가동'으로 해석한다.

    이 배치가 피하려는 실패는 이것이다. 오프라인 로봇이 어르신을 AWAY 라고 믿고
    사다리를 영원히 멈추는 것. UNKNOWN 이 정직한 답이다.

참고
    CLAUDE.md §11 (현관과 재실), §10 (침묵 사다리), §18 (오프라인)
    S15P11E102-208 (이 패키지), S15P11E102-226 (백엔드 방향 판정)
"""

from bomi_ai_chat.door.intake import ingest
from bomi_ai_chat.door.occupancy import (
    apply_backend_occupancy,
    local_occupancy_for,
    set_occupancy,
)

__all__ = [
    "apply_backend_occupancy",
    "ingest",
    "local_occupancy_for",
    "set_occupancy",
]
