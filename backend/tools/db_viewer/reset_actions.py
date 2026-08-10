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
#   * onboarding_* — 지우면 로봇이 다음 대화에서 온보딩 질문부터 다시 시작한다.
#     시연 도중 그것이 튀어나오면 대본이 통째로 어긋난다.
PROTECTED_TABLES = frozenset({
    "drug_permit",
    "hospital",
    "pharmacy",
    "app_user",
    "care_relationship",
    "robot",
    "onboarding_session",
    "onboarding_answer",
})

# ★ 시드 행을 알아보는 유일한 표지 (2026-08-10)
#
# 무엇인가
#   scripts/dev/seed-*.sql 이 넣는 행은 전부 **손으로 적은 고정 UUID** 다.
#   `10000000-0000-4000-8000-000000000001`, `40000000-…`, `80000000-…` 처럼
#   2·3·4번째 블록이 `0000-4000-8000` 으로 고정돼 있다.
#
#   반면 대화·화면에서 생기는 행은 UUIDv4 다 —
#   `c8fe92b3-2b6e-496c-a09b-be78d911cae6`. 세 블록이 전부 난수라 이 패턴에
#   걸릴 확률은 16^4 × 16^3 × 16^3 ≈ 7000억 분의 1이다. 실질적으로 0이다.
#
# ★ 왜 이 표지가 필요해졌나
#   그전에는 테이블 단위로만 지킬 수 있었다. 그래서 memory·fact_candidate 를 통째로
#   보호 목록에 넣었고, care_record 는 `record_type='ENVIRONMENT_OBSERVATION'` 한
#   줄만 지웠다. 결과적으로 **삭제 버튼을 눌러도 화면이 그대로였다** — 확인할 일,
#   기억, 복약, 일정이 전부 그 보호막 안에 있었기 때문이다(2026-08-10 실측:
#   확인 요청 3건·기억 31건·복약 2건·일정 2건이 삭제 후에도 남음).
#
#   지키려던 것은 "테이블"이 아니라 **"시드"** 였다. 표지를 테이블에서 행으로
#   내리면 둘 다 된다 — 시드는 남고, 테스트가 만든 것은 지워진다.
#
# 주의
#   손으로 INSERT 하면서 UUID 를 랜덤으로 넣은 '시드'는 이 표지에 걸리지 않는다.
#   시드를 추가할 때는 반드시 고정 UUID 패턴을 쓴다 — 그것이 이 규칙의 대가다.
SEED_ID_LIKE = "%-0000-4000-8000-%"

_KEEP_SEED = f"id::text NOT LIKE '{SEED_ID_LIKE}'"

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
# 두 부류가 섞여 있다.
#
#   1) **보호자 화면에 보이는 것** — 시드만 남기고 지운다(_KEEP_SEED).
#      care_record 하나에 복약·복약슬롯·일정·위급알림·건강관찰이 record_type 으로만
#      갈려 전부 들어 있다. 그래서 이 한 줄이 화면 세 블록(복약 관리·오늘의 복약
#      응답·일정 관리)을 동시에 정리한다. fact_candidate 는 "확인할 일" 카드,
#      memory 는 활동 피드의 "새로 기억한 내용" 이다.
#
#   2) **화면에 안 보이는 실행 흔적** — 전량 삭제. 대화·시나리오·영수증·감사로그는
#      시드가 없다(전부 실행 중 생긴다). 남겨 둘 이유가 없다.
#
# ★ 이 DB 에는 FK 가 하나도 없다(실측). 삭제가 연쇄되지도, 차단되지도 않으므로
#   부모·자식을 여기서 직접 짝지어 지운다 — conversation 만 지우면 메시지 826행이
#   고아로 남는다.
RESIDUE_DELETE_TARGETS: tuple[tuple[str, str | None], ...] = (
    # ── 1) 화면에 보이는 것 (시드 보존) ──
    ("care_record", _KEEP_SEED),
    ("fact_candidate", _KEEP_SEED),
    ("memory", _KEEP_SEED),
    ("known_person", _KEEP_SEED),
    # ── 2) 실행 흔적 (전량) ──
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

# 삭제와 함께 되돌려야 하는 상태 — 지울 '행'이 없는 것들.
#
# 온습도는 robot 한 행의 컬럼 세 개다. IoT 관측이 올 때마다 덮어써지므로 어떤
# DELETE 로도 사라지지 않는다. "삭제했는데 온습도가 그대로다"의 답이 이것이다.
#
# ★ 단, 파이(dht11)가 켜져 있으면 몇 초 안에 새 값이 다시 들어온다. 고장이 아니다 —
#   화면을 진짜로 비우려면 퍼블리셔를 먼저 끈다.
RESIDUE_RESET_STEPS: tuple[tuple[str, str], ...] = (
    (
        "로봇 관측값(온습도) 비우기",
        """
        UPDATE robot
           SET ambient_temperature_c    = NULL,
               ambient_humidity_percent = NULL,
               ambient_observed_at      = NULL
         WHERE is_active = TRUE
        """,
    ),
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
    """B) 잔여 데이터를 지운다. 한 트랜잭션이라 중간 실패 시 전부 되돌아간다.

    삭제가 끝나면 RESIDUE_RESET_STEPS 도 같은 트랜잭션에서 돌린다. 지울 행이 없는
    상태(온습도)까지 함께 되돌려야 "삭제했는데 화면이 그대로"가 안 남는다.
    """
    _assert_targets_are_safe()
    results = []
    with conn.transaction():
        for table, where in RESIDUE_DELETE_TARGETS:
            clause = f" WHERE {where}" if where else ""
            cur = conn.execute(f"DELETE FROM {table}{clause}")
            results.append(StepResult(label=table, affected=cur.rowcount))
        for label, statement in RESIDUE_RESET_STEPS:
            cur = conn.execute(statement)
            results.append(StepResult(label=label, affected=cur.rowcount))
    return results
