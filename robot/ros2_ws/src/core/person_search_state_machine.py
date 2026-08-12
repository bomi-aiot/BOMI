"""웨이포인트 순찰 기반 사용자 탐색의 순수 상태 전환을 관리한다."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import math
from typing import Any


class PersonSearchState(str, Enum):
    """사용자 탐색 임무의 현재 실행 상태다."""

    IDLE = "idle"
    PATROLLING = "patrolling"
    CANCELING_NAV2 = "canceling_nav2"
    FOLLOWING = "following"
    NOT_FOUND = "not_found"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class PersonSearchDecision:
    """입력 처리 후 외부 노드가 실행할 탐색 결정을 나타낸다."""

    state: PersonSearchState
    person_confirmed: bool = False
    reason: str = ""
    track_id: int | None = None


def parse_person_detection(raw_message: str) -> tuple[str, int | None]:
    """비전 JSON에서 검증된 추적 상태와 track ID를 읽는다."""
    try:
        payload: Any = json.loads(raw_message)
    except json.JSONDecodeError as error:
        raise ValueError("비전 결과가 올바른 JSON 형식이 아닙니다.") from error
    if not isinstance(payload, dict):
        raise ValueError("비전 결과는 JSON 객체여야 합니다.")

    status = payload.get("status")
    track_id = payload.get("track_id")
    if not isinstance(status, str) or not status.strip():
        raise ValueError("비전 결과의 status는 비어 있지 않은 문자열이어야 합니다.")
    if track_id is not None and (
        isinstance(track_id, bool) or not isinstance(track_id, int) or track_id < 0
    ):
        raise ValueError("비전 결과의 track_id는 null 또는 음이 아닌 정수여야 합니다.")
    return status.strip().lower(), track_id


class PersonSearchStateMachine:
    """순찰, 사람 확정, Nav2 취소와 추종 전환 순서를 강제한다."""

    def __init__(self, target_confirm_sec: float = 0.5) -> None:
        """사람을 확정하기 위한 동일 대상 유지 시간을 설정한다."""
        if (
            isinstance(target_confirm_sec, bool)
            or not isinstance(target_confirm_sec, (int, float))
            or not math.isfinite(target_confirm_sec)
            or target_confirm_sec <= 0.0
        ):
            raise ValueError("target_confirm_sec는 유한한 양수여야 합니다.")
        self.target_confirm_sec = float(target_confirm_sec)
        self.state = PersonSearchState.IDLE
        self._candidate_track_id: int | None = None
        self._candidate_started_at: float | None = None

    def start(self) -> PersonSearchDecision:
        """대기 상태에서 한 바퀴 사용자 탐색을 시작한다."""
        if self.state not in {
            PersonSearchState.IDLE,
            PersonSearchState.NOT_FOUND,
            PersonSearchState.FAILED,
            PersonSearchState.CANCELLED,
            PersonSearchState.FOLLOWING,
        }:
            return self._decision(reason="already_running")
        self.state = PersonSearchState.PATROLLING
        self._reset_candidate()
        return self._decision(reason="search_started")

    def observe(
        self, status: str, track_id: int | None, now_sec: float
    ) -> PersonSearchDecision:
        """비전 관측을 반영하고 안정된 단일 사람인지 판정한다."""
        if self.state != PersonSearchState.PATROLLING:
            return self._decision(reason="not_patrolling")
        if not math.isfinite(now_sec):
            raise ValueError("now_sec는 유한해야 합니다.")
        if status != "tracking" or track_id is None:
            self._reset_candidate()
            return self._decision(reason="person_not_confirmed")

        if self._candidate_track_id != track_id:
            self._candidate_track_id = track_id
            self._candidate_started_at = now_sec
            return self._decision(reason="candidate_started", track_id=track_id)

        if self._candidate_started_at is None:
            self._candidate_started_at = now_sec
            return self._decision(reason="candidate_started", track_id=track_id)
        if now_sec - self._candidate_started_at < self.target_confirm_sec:
            return self._decision(reason="candidate_confirming", track_id=track_id)

        self.state = PersonSearchState.CANCELING_NAV2
        return self._decision(
            person_confirmed=True,
            reason="person_confirmed",
            track_id=track_id,
        )

    def nav2_cancelled(self) -> PersonSearchDecision:
        """Nav2 목표 취소가 끝난 뒤에만 추종 상태로 전환한다."""
        if self.state != PersonSearchState.CANCELING_NAV2:
            return self._decision(reason="cancel_not_expected")
        self.state = PersonSearchState.FOLLOWING
        return self._decision(
            reason="following_started",
            track_id=self._candidate_track_id,
        )

    def complete_without_person(self) -> PersonSearchDecision:
        """모든 지점을 확인했으면 사람 없음으로 임무를 종료한다."""
        if self.state != PersonSearchState.PATROLLING:
            return self._decision(reason="completion_not_expected")
        self.state = PersonSearchState.NOT_FOUND
        self._reset_candidate()
        return self._decision(reason="all_waypoints_checked")

    def fail(self, reason: str) -> PersonSearchDecision:
        """복구할 수 없는 Nav2 또는 내부 오류로 탐색을 실패 처리한다."""
        self.state = PersonSearchState.FAILED
        self._reset_candidate()
        return self._decision(reason=reason)

    def cancel(self) -> PersonSearchDecision:
        """외부 취소 요청을 반영해 탐색을 종료한다."""
        self.state = PersonSearchState.CANCELLED
        self._reset_candidate()
        return self._decision(reason="search_cancelled")

    def _reset_candidate(self) -> None:
        self._candidate_track_id = None
        self._candidate_started_at = None

    def _decision(
        self,
        *,
        person_confirmed: bool = False,
        reason: str,
        track_id: int | None = None,
    ) -> PersonSearchDecision:
        return PersonSearchDecision(self.state, person_confirmed, reason, track_id)
