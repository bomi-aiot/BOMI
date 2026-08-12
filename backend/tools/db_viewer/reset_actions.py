"""리허설 사이 초기화 동작 — 상태 리셋(A)과 잔여 데이터 삭제(B).

왜 SQL 이 여기에 또 있는가
    정본은 `scripts/dev/reset-demo.sql` 이다. 도커 빌드 컨텍스트가
    `backend/tools/db_viewer` 라서 그 파일을 이미지에 넣을 수 없어 여기에 옮겨 적었다.
    복붙은 반드시 갈라지므로 `tests/test_reset_actions.py` 가 두 곳의 문장을 대조해
    어긋나면 실패한다 — 사람의 규율이 아니라 테스트가 동기화를 강제한다.

왜 A 는 DELETE 를 쓰지 않는가
    reset-demo.sql 의 판단을 그대로 따른다. T1 안전 알림은 어르신 안전에 관한 관찰
    기록이고, 지우면 "언제 무엇을 감지했는지" 되짚을 근거가 사라진다. 화면 필터는
    status='ACTIVE' 하나뿐이라 상태만 바꾸면 화면에서는 사라지고 행은 남는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # psycopg 없이도 목록·안전 검사를 테스트할 수 있어야 한다
    import psycopg

# 이 테이블들은 어떤 경로로도 삭제 대상이 될 수 없다.
#
#   * drug_permit·hospital·pharmacy — 외부에서 받아온 참조 마스터(합계 14만 행).
#     지우면 재적재에 시간이 걸리고 시연 중 복구할 방법이 없다.
#   * app_user·care_relationship·robot — 온보딩으로만 생기는 신원/관계. 지우면
#     시연 자체가 불가능해진다.
#   * memory·fact_candidate — 어르신의 기억. 보미가 "지난번에 말씀하신…" 을 하려면
#     남아 있어야 한다 (2026-08-10 사용자 승인 시 명시적으로 보존 선택).
#   * known_person·onboarding_* — 재생성 경로가 없다.
PROTECTED_TABLES = frozenset({
    "drug_permit",
    "hospital",
    "pharmacy",
    "app_user",
    "care_relationship",
    "robot",
    "memory",
    "fact_candidate",
    "known_person",
    "onboarding_session",
    "onboarding_answer",
})

# ── A) 시나리오 상태 리셋 — reset-demo.sql 과 1:1 대응. 삭제 0건 ──────────────
#
# (라벨, SQL). 순서가 의미를 가진다: 1) 이 없으면 ACTIVE_SCENARIO_EXISTS 가 계속 막고,
# 3) 이 없으면 같은 복약 슬롯이 두 번째 리허설부터 조용히 침묵한다.
STATE_RESET_STEPS: tuple[tuple[str, str], ...] = (
    (
        "활성 시나리오 종료",
        """
        UPDATE scenario
           SET final_status = 'CANCELLED',
               updated_at = now(),
               active_navigation_command_id = NULL,
               active_navigation_target     = NULL
         WHERE final_status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT')
        """,
    ),
    (
        "로봇 모드 복구 (SAFE_STOP → IDLE)",
        """
        UPDATE robot
           SET current_mode = 'IDLE'
         WHERE device_id = 'bomi-AA001'
           AND is_active = TRUE
        """,
    ),
    (
        "복약 슬롯 영수증 무효화",
        """
        UPDATE scenario
           SET external_event_id = external_event_id || '-reset'
         WHERE scenario_type = 'MEDICATION_REMINDER'
           AND external_event_id LIKE 'med-%'
           AND external_event_id NOT LIKE '%-reset'
        """,
    ),
    (
        "지난 위급 알림(T1) 닫기",
        """
        UPDATE care_record
           SET status = 'COMPLETED'
         WHERE record_type = 'GUARDIAN_ALERT'
           AND status = 'ACTIVE'
        """,
    ),
)

# ── B) 테스트 잔여 데이터 삭제 — 진짜 DELETE ────────────────────────────────
#
# (테이블, WHERE 절 또는 None). None 이면 전량 삭제.
#
# ★ care_record 는 조건부다. MEDICATION / MEDICATION_SCHEDULE 행(각 2건)은 복약
#   시나리오의 시드라서 지우면 복약 알림이 아예 울리지 않는다. 온습도 관찰만 지운다.
#
# ★ 이 DB 에는 FK 가 하나도 없다(실측). 삭제가 연쇄되지도, 차단되지도 않으므로
#   부모·자식을 여기서 직접 짝지어 지운다 — conversation 만 지우면 메시지 826행이
#   고아로 남는다.
RESIDUE_DELETE_TARGETS: tuple[tuple[str, str | None], ...] = (
    ("care_record", "record_type = 'ENVIRONMENT_OBSERVATION'"),
    ("conversation_message", None),
    ("conversation_summary", None),
    ("conversation", None),
    ("scenario", None),
    ("wake_word_trigger_receipt", None),
    ("robot_mode_recovery_audit", None),
    ("operator_scenario_cancellation_audit", None),
    ("occupancy_event", None),
    ("daily_activity_metric", None),
    ("walk_request_receipt", None),
)


@dataclass(frozen=True)
class StepResult:
    label: str
    affected: int


def _assert_targets_are_safe() -> None:
    """보호 테이블이 삭제 목록에 섞이면 즉시 죽는다.

    나중에 목록에 한 줄 더 붙이는 사람이 이 검사를 통과하지 못하면, 잘못된 삭제는
    실행 시점이 아니라 임포트 시점에 드러난다.
    """
    for table, _ in RESIDUE_DELETE_TARGETS:
        if table in PROTECTED_TABLES:
            raise AssertionError(f"보호 테이블이 삭제 목록에 있다: {table}")


_assert_targets_are_safe()


def preview_residue(conn: psycopg.Connection) -> list[StepResult]:
    """삭제하지 않고, 지워질 행 수만 센다 (2단계 확인의 1단계)."""
    results = []
    for table, where in RESIDUE_DELETE_TARGETS:
        clause = f" WHERE {where}" if where else ""
        n = conn.execute(f"SELECT count(*) FROM {table}{clause}").fetchone()[0]
        results.append(StepResult(label=table, affected=n))
    return results


def run_state_reset(conn: psycopg.Connection) -> list[StepResult]:
    """A) 상태만 되돌린다. 행은 하나도 지우지 않는다."""
    results = []
    with conn.transaction():
        for label, statement in STATE_RESET_STEPS:
            cur = conn.execute(statement)
            results.append(StepResult(label=label, affected=cur.rowcount))
    return results


def run_residue_delete(conn: psycopg.Connection) -> list[StepResult]:
    """B) 잔여 데이터를 지운다. 한 트랜잭션이라 중간 실패 시 전부 되돌아간다."""
    _assert_targets_are_safe()
    results = []
    with conn.transaction():
        for table, where in RESIDUE_DELETE_TARGETS:
            clause = f" WHERE {where}" if where else ""
            cur = conn.execute(f"DELETE FROM {table}{clause}")
            results.append(StepResult(label=table, affected=cur.rowcount))
    return results
