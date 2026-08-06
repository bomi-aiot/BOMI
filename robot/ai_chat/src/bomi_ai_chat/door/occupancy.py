"""재실 상태 규칙 — 세 가지 값 중 무엇을 언제 쓰는가.

세 값의 뜻  (CLAUDE.md §10 해석표)
    HOME     집에 있다.       침묵이 의심스러워진다 -> 사다리 가동
    AWAY     나가 있다.       침묵이 아무 정보도 아니다 -> 사다리 정지
    UNKNOWN  모른다.          보수적으로 가동한다

    UNKNOWN 이 AWAY 와 '다르게' 취급되는 것이 이 파일의 존재 이유다. 둘을 같게 다루면
    라즈베리파이 하나가 죽은 것만으로 안전 감시가 통째로 꺼지고, 아무도 그 사실을
    모른다 (jobs/ticks.py 의 _is_absence_expected 와 같은 함정).

누가 이 값을 바꿀 수 있는가
    발화    -> HOME.     graph.ingress.note_interaction. 집 안에서 목소리가 들리면
                         센서가 뭐라 했든 집에 있다. **발화가 센서를 이긴다.**
    센서    -> UNKNOWN.  door.intake. 방향을 모르므로 이것이 유일하게 안전한 값이다.
    백엔드  -> 확정값.    apply_backend_occupancy. 방향을 판정한 쪽이 진짜 값을 내려준다.
    하트비트 끊김 -> UNKNOWN. jobs.ticks.door_watch_tick.

참고
    CLAUDE.md §10 (침묵 사다리), §11 (현관과 재실)
"""

from __future__ import annotations

import logging

from bomi_ai_chat.localstore import runtime as runtime_store
from bomi_ai_chat.state import Occupancy

logger = logging.getLogger(__name__)

_VALID: frozenset[str] = frozenset({"HOME", "AWAY", "UNKNOWN"})

# 문에 '무슨 일이 있었다'를 뜻하는 이벤트. 누가 어느 쪽으로 지나갔는지는 모른다.
_DOOR_ACTIVITY = frozenset({"DOOR_OPENED", "MOTION_DETECTED"})


def local_occupancy_for(event_type: str) -> Occupancy | None:
    """이 이벤트만 보고 로봇이 확정할 수 있는 재실 상태. 없으면 None.

    무엇을 하는가
        문 열림과 현관 모션은 UNKNOWN 을 뜻한다. 나머지는 재실에 대해 아무 말도
        하지 않는다.

    왜 HOME 이나 AWAY 를 돌려주지 않는가
        방향을 모르기 때문이다. 문이 열렸다는 것만으로는 어르신이 나갔는지 들어왔는지,
        아니면 택배가 왔는지 알 수 없다. 추측해서 HOME 이라고 두면 빈 집을 상대로
        사다리가 돌고, AWAY 라고 두면 집에 있는 사람에 대한 감시가 꺼진다.
        둘 다 조용한 실패이고, UNKNOWN 은 둘 중 아무것도 아니다.

    왜 HOME 이었어도 UNKNOWN 으로 내리는가
        문이 열렸다면 나갔을 수도 있다. 옛 HOME 을 유지하는 것은 "모른다"를
        "집에 있다"로 바꿔 말하는 것이다. 어르신이 한마디만 하면 곧바로 HOME 으로
        돌아온다(note_interaction).

    반환값
        "UNKNOWN" 또는 None. 이 함수는 HOME/AWAY 를 절대 돌려주지 않는다.
    """
    return "UNKNOWN" if event_type in _DOOR_ACTIVITY else None


def set_occupancy(
    senior_id: str,
    occupancy: str,
    *,
    observed_at: float,
    source: str,
) -> dict[str, object]:
    """재실 상태를 내구 저장소에 반영한다. away_since 를 함께 유지한다.

    무엇을 하는가
        네 가지를 한 번에 처리한다.
          1. 값을 검증한다. 오타가 조용히 저장되면 사다리가 이상하게 동작한다.
          2. **낡은 관측은 무시한다.** 아래 참고.
          3. AWAY 로 '전이'할 때만 away_since 를 찍고, 아니면 0 으로 지운다.
          4. 저장한다.

    왜 낡은 관측을 무시하는가  ★ 이 함수의 핵심
        "발화가 센서를 이긴다"를 시각 비교로 표현한 것이다.

        어르신이 방금 말했다(HOME, t=100). 그런데 백엔드가 t=90 에 일어난 외출을
        이제야 판정해서 AWAY 를 내려보낸다(도착 t=105). 도착 순서대로 적용하면
        말하고 있는 사람이 AWAY 가 되고, 그 상태로 사다리가 멈춘다.

        그래서 '관측 시각'을 비교한다. observed_at 이 저장된 값보다 앞서면 버린다.
        같으면 적용한다 — 실제 시계에서 동시는 거의 없고, 동시라면 나중에 온 쪽이
        더 많은 정보를 가졌다고 본다.

    인자
        observed_at: 이 사실이 '관측된' 시각. 문 이벤트라면 DoorEvent.received_at,
            발화라면 발화 시각이다. 저장 시각이 아니다.
        source: 로그용. "sensor" | "speech" | "backend" | "heartbeat".
            "왜 로봇이 어르신을 나갔다고 생각했는가"에 답하려면 이 값이 필요하다.

    반환값
        실제로 쓴 필드. 아무것도 쓰지 않았으면 빈 dict.
    """
    if occupancy not in _VALID:
        raise ValueError(f"unknown occupancy {occupancy!r}; expected one of {sorted(_VALID)}")

    current = runtime_store.load(senior_id)
    stored_at = float(current.get("occupancy_observed_at") or 0.0)

    if observed_at < stored_at:
        logger.info(
            "ignoring stale occupancy %s from %s (observed %.0f < stored %.0f); "
            "keeping %s",
            occupancy, source, observed_at, stored_at, current.get("occupancy"),
        )
        return {}

    fields: dict[str, object] = {
        "occupancy": occupancy,
        "occupancy_observed_at": observed_at,
    }

    was_away = current.get("occupancy") == "AWAY"
    if occupancy == "AWAY":
        # 이미 AWAY 였으면 시작 시각을 건드리지 않는다. 건드리면 부재 시간이 매번
        # 리셋되어 미귀가 알림이 영원히 나가지 않는다.
        if not was_away:
            fields["away_since"] = observed_at
    else:
        fields["away_since"] = 0.0

    runtime_store.save(senior_id, **fields)
    if current.get("occupancy") != occupancy:
        logger.info("occupancy %s -> %s (source=%s)", current.get("occupancy"),
                    occupancy, source)
    return fields


def apply_backend_occupancy(
    senior_id: str,
    occupancy: str,
    *,
    observed_at: float,
) -> dict[str, object]:
    """백엔드가 방향을 판정해 내려준 확정 재실 상태를 반영한다.

    누가 호출하는가
        백엔드 명령 수신부. 로봇은 이 값을 만들지 않고 받아 쓴다 (CLAUDE.md §11).

    왜 별도 함수인가
        set_occupancy 와 하는 일은 같지만, 호출부에서 "이건 백엔드가 확정한 값"임이
        보여야 한다. HOME/AWAY 가 저장소에 들어오는 경로는 발화와 이 함수, 둘뿐이다.
        그 사실을 grep 한 번으로 확인할 수 있어야 한다.
    """
    return set_occupancy(senior_id, occupancy, observed_at=observed_at, source="backend")
