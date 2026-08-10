"""여러 사람이 보일 때 대표 한 명을 고른다 (구현계획 결정 9).

왜 필요한가
    기본 안전 규칙은 "두 명 이상이면 멈춘다"이다. 누구를 따라갈지 모르는 채
    움직이는 것보다 서는 편이 안전하기 때문이다. 그런데 시연장에는 구경꾼이
    있고, 그 규칙 그대로면 추종이 시작조차 하지 않는다.

왜 여기서 거르는가 (설계에서 가장 중요한 결정)
    "다중 인물 중 하나 고르기"를 상태 기계 안에서 하려면 세 곳의 안전 불변식을
    동시에 고쳐야 한다:
        position.py             2명 이상이면 위치 계산 자체를 하지 않는다
        domain/tracking.py      TRACKING 은 person_count == 1 일 때만 성립한다
        core/person_follower.py 다중 인물이면 정지한다
    셋 다 "여러 명일 때 함부로 대상을 정하지 않는다"는 같은 규칙의 세 얼굴이다.
    이걸 풀면 안전망이 통째로 헐거워진다(robot/AGENTS.md §4 "안전 제한을 약화해
    구현을 통과시키지 않는다").

    그래서 이 모듈은 **상태 기계 앞에서** 후보 목록 자체를 한 명으로 줄인다.
    그러면 하류는 "원래 한 명이었다"고 보므로 불변식이 하나도 깨지지 않고,
    기존 테스트도 그대로 통과한다. 꺼 두면(기본값) 목록을 손대지 않으므로
    동작이 1비트도 달라지지 않는다.

왜 신뢰도가 아니라 화면 중앙인가
    YOLO 의 confidence 는 "사람일 확률"이지 "이 사람이 부른 사람일 확률"이
    아니다. 멀리 정면으로 선 낯선 사람이 가까이 옆으로 앉은 어르신보다 높게
    나오는 일이 흔하다. 반면 이 로봇은 소리 방향으로 이미 몸을 돌린 뒤라서,
    화면 중앙에 있는 사람이 부른 사람일 확률이 가장 높다.
    신뢰도는 "후보에서 뺄 사람"을 고르는 데만 쓴다.

왜 한 번 고르면 붙잡는가 (히스테리시스)
    신뢰도도 중심 거리도 프레임마다 흔들린다. 매 프레임 다시 고르면 대상이
    두 사람 사이를 오가고 로봇이 좌우로 떤다. 그래서 고른 track_id 가 화면에
    남아 있는 동안에는 그 사람을 유지한다.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PrimaryPersonConfig:
    """대표 인물 선택 설정.

    enabled: 꺼져 있으면(기본) 목록을 손대지 않는다 — 기존 안전 동작 그대로다.
    min_confidence: 이 값 미만인 탐지는 후보에서 뺀다. 오탐이 대상이 되는 것을
        막는 용도이며, 선택 기준으로는 쓰지 않는다.
    min_height_ratio: 화면 높이 대비 사람 상자 높이의 하한. 너무 멀리 있는
        사람(복도 끝의 행인 등)을 후보에서 뺀다. 0.0 이면 거리 제한 없음.
    """

    enabled: bool = False
    min_confidence: float = 0.5
    min_height_ratio: float = 0.0

    def __post_init__(self) -> None:
        """설정값의 단위와 허용 범위를 시작 시점에 검증한다."""
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a boolean")
        _require_ratio(self.min_confidence, "min_confidence")
        _require_ratio(self.min_height_ratio, "min_height_ratio")


def _require_ratio(value: float, name: str) -> None:
    """0.0 이상 1.0 이하의 유한한 실수인지 확인한다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")


class PrimaryPersonSelector:
    """여러 사람 중 대표 한 명만 남기는 전처리기.

    상태
        마지막으로 고른 track_id 하나만 기억한다(히스테리시스). 이 값은 사용자
        신원이 아니라 현재 영상 흐름의 임시 번호이며, 그 사람이 화면에서
        사라지면 즉시 버린다.

    스레드 안전성
        보장하지 않는다. 프레임 루프(run_person_tracking) 한 곳에서만 부른다.
    """

    def __init__(self, config: PrimaryPersonConfig | None = None) -> None:
        """설정을 검증하고 잠금을 비운 상태로 시작한다."""
        self._config = config if config is not None else PrimaryPersonConfig()
        self._locked_track_id: int | None = None

    @property
    def config(self) -> PrimaryPersonConfig:
        """이 선택기가 쓰는 설정."""
        return self._config

    @property
    def locked_track_id(self) -> int | None:
        """지금 붙잡고 있는 대표 Track ID. 없으면 None."""
        return self._locked_track_id

    def reset(self) -> None:
        """대표 잠금을 푼다. 새 시나리오를 시작할 때 부른다."""
        self._locked_track_id = None

    def select(
        self,
        tracked_people: Sequence,
        frame_width: int,
        frame_height: int,
    ) -> Sequence:
        """대표 한 명만 남긴 목록을 돌려준다.

        역할: 여러 사람이 보일 때 하나를 골라 하류가 "한 명"만 보게 한다.
        입력값:
            tracked_people - 이번 프레임에서 추적된 사람들(TrackedPerson).
            frame_width, frame_height - 픽셀 단위 프레임 크기.
        반환값: 길이 0 또는 1의 목록, 또는 입력 그대로.

        언제 입력을 그대로 돌려주는가 (전부 "함부로 정하지 않는다"의 표현이다)
            - 기능이 꺼져 있을 때
            - 사람이 0명이거나 1명일 때 (고를 것이 없다)
            - 조건을 통과한 후보가 하나도 없을 때
              → 기존 안전 규칙(다중 인물이면 정지)이 그대로 작동한다.
                여기서 억지로 하나를 고르면 신뢰할 수 없는 대상을 따라간다.
        """
        _require_frame_size(frame_width, frame_height)
        people = list(tracked_people)

        if not self._config.enabled:
            return tracked_people

        if len(people) <= 1:
            # 한 명이면 그 사람이 곧 대표다. 잠금을 맞춰 두면 다음 프레임에
            # 사람이 늘어나도 원래 보던 사람을 계속 따라간다.
            self._locked_track_id = (
                _track_id_of(people[0]) if people else None)
            return tracked_people

        candidates = [
            person for person in people
            if self._is_candidate(person, frame_height)
        ]
        if not candidates:
            # 조건을 통과한 사람이 없다. 대상을 만들어 내지 않는다.
            self._locked_track_id = None
            return tracked_people

        locked = self._locked_candidate(candidates)
        chosen = locked if locked is not None else _closest_to_center(
            candidates, frame_width)

        self._locked_track_id = _track_id_of(chosen)
        return [chosen]

    # ── 내부 ────────────────────────────────────────────────────────────────

    def _is_candidate(self, person, frame_height: int) -> bool:
        """신뢰도와 크기 하한을 통과하는지 본다."""
        confidence = float(getattr(person, "confidence", 0.0))
        if not math.isfinite(confidence):
            return False
        if confidence < self._config.min_confidence:
            return False
        if self._config.min_height_ratio > 0.0:
            height_ratio = _height_ratio(person, frame_height)
            if height_ratio < self._config.min_height_ratio:
                return False
        return True

    def _locked_candidate(self, candidates: list):
        """지난 프레임에 고른 사람이 아직 후보에 있으면 그 사람을 돌려준다."""
        if self._locked_track_id is None:
            return None
        for person in candidates:
            if _track_id_of(person) == self._locked_track_id:
                return person
        return None


# ── 순수 계산 ───────────────────────────────────────────────────────────────


def _closest_to_center(candidates: list, frame_width: int):
    """화면 중앙에 가장 가까운 사람을 고른다.

    같은 거리면 상자가 큰(= 가까운) 사람을 고른다. 정렬 키를 하나만 쓰면
    좌우 대칭 위치에서 프레임마다 대상이 뒤집힐 수 있다.
    """
    center_x = frame_width / 2.0

    def sort_key(person):
        horizontal_offset = abs(_center_x_of(person) - center_x)
        box_height = _box_height(person)
        return (horizontal_offset, -box_height, _track_id_of(person))

    return min(candidates, key=sort_key)


def _center_x_of(person) -> float:
    """사람 상자의 가로 중심 좌표."""
    return (float(person.x1) + float(person.x2)) / 2.0


def _box_height(person) -> float:
    """사람 상자의 높이(픽셀)."""
    return max(0.0, float(person.y2) - float(person.y1))


def _height_ratio(person, frame_height: int) -> float:
    """화면 높이 대비 사람 상자 높이 비율."""
    if frame_height <= 0:
        return 0.0
    return _box_height(person) / float(frame_height)


def _track_id_of(person) -> int:
    """추적 번호를 정수로 돌려준다."""
    return int(person.track_id)


def _require_frame_size(frame_width: int, frame_height: int) -> None:
    """프레임 크기를 검증한다. 중심 계산의 분모라 0이면 안 된다."""
    for value, name in ((frame_width, "frame_width"),
                        (frame_height, "frame_height")):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        if value <= 0:
            raise ValueError(f"{name} must be greater than zero")
