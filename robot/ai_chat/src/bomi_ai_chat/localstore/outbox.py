"""보호자 알림 발신 큐 — 이 기기에서 내구성을 완화하지 않는 유일한 지점.

왜 존재하는가
    네트워크는 언젠가 끊기고, 끊긴 연결로 '발사'된 T1 알림은 그냥 사라진다. 게다가
    하필 네트워크가 없는 순간이 알림이 가장 중요한 순간일 수 있다. 그래서 순서를
    뒤집는다 — **전송보다 저장이 먼저다.** 쓰고, 시도하고, 실패하면 틱이 재시도한다.

    이것이 CLAUDE.md §19 에서 Outbox 가 "있으면 좋은 것"에서 "필수"로 승격된 이유다.

두 가지를 구분한다
    enqueue  기록한다. 동기 쓰기다. 여기서 반환됐다면 그 알림은 전원이 끊겨도 남는다.
    flush    보낸다. 실패해도 괜찮다. 큐가 책임진다.

    호출하는 쪽(트리아지·일일 요약)은 enqueue 만 부르고 전송 결과를 기다리지 않는다.
    전송 예외가 대화 턴을 중단시키게 두어서는 안 된다.

지연 표시
    늦게 도착한 알림은 '지연됨'으로 표시해서 보낸다. 보호자가 "지금 벌어지는 일"과
    "와이파이가 끊긴 두 시간 전에 벌어진 일"을 구분할 수 있어야 한다. 구분이 없으면
    이미 지나간 상황에 대해 지금 놀라게 되고, 그런 경험이 쌓이면 알림을 안 읽는다.

T1 은 포기하지 않는다
    T2·T3 는 시도 횟수를 넘기면 GAVE_UP 이 된다(어제의 요약을 영원히 재시도할 이유는
    없다). T1 은 그 목록에 없다. 생명 안전 알림을 시도 횟수로 버리지 않는다.

참고
    CLAUDE.md §9 (티어), §18 (오프라인은 안전 문제다), §19 (Outbox)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from bomi_ai_chat import policy
from bomi_ai_chat.clock import clock
from bomi_ai_chat.localstore import schema
from bomi_ai_chat.localstore.db import outbox_db
from bomi_ai_chat.notify.base import GuardianNotifier, NotifyError

logger = logging.getLogger(__name__)


def enqueue(tier: str, payload: dict[str, Any]) -> int:
    """알림을 큐에 '기록'한다. 전송은 하지 않는다.

    무엇을 하는가
        동기 쓰기로 한 행을 남기고 즉시 반환한다. 이 함수가 반환됐다면 전원이 끊겨도
        그 알림은 살아 있다(db.py 의 synchronous=FULL).

    누가 호출하는가
        graph.triage.escalation(T1), jobs.ticks.daily_summary_job(T2),
        T3 동의 흐름. 전송을 기다리는 쪽은 없다.

    인자
        tier: "T1" | "T2" | "T3". T4 는 오지 않는다 — 절대 보내지 않으므로 큐에
            들어갈 일이 없다. 실수로 오면 요란하게 실패한다.
        payload: 채널이 렌더링할 자료. 집계와 이상치만. 원본 기록은 넣지 않는다.

    반환값
        큐 행 id.

    주의사항
        동의 확인은 여기의 책임이 아니다. T2·T3 는 큐에 넣기 '전에'
        guardian_sharing_consent_status 를 확인해야 한다. T1 은 생명 안전이므로
        동의와 무관하게 넣는다 (CLAUDE.md §9).
    """
    if tier == "T4":
        # 조용히 무시하면 "보냈다고 믿는" 코드가 남는다. T4 는 큐가 아니라
        # 기억의 공개범위(PRIVATE)로 표현된다.
        raise ValueError("T4 는 전송 대상이 아닙니다. memory.visibility 로 표현하세요.")
    if tier not in ("T1", "T2", "T3"):
        raise ValueError(f"알 수 없는 tier: {tier}")

    connection = outbox_db()
    schema.init_outbox(connection)
    now = clock.now()
    cursor = connection.execute(
        "INSERT INTO outbox (tier, payload, status, attempt_count, created_at, next_attempt_at) "
        "VALUES (?, ?, 'PENDING', 0, ?, ?)",
        (tier, json.dumps(payload, ensure_ascii=False), now, now),
    )
    return int(cursor.lastrowid)


def pending_count() -> int:
    """아직 나가지 못한 알림 개수. 운영 지표이자 테스트용."""
    connection = outbox_db()
    schema.init_outbox(connection)
    row = connection.execute(
        "SELECT count(*) AS c FROM outbox WHERE status = 'PENDING'"
    ).fetchone()
    return int(row["c"])


def _backoff_delay(attempt_count: int) -> float:
    """다음 시도까지 기다릴 시간.

    왜 상한을 두는가
        지수 백오프를 그냥 두면 간격이 몇 시간까지 벌어진다. 와이파이가 20분 만에
        돌아왔는데 다음 시도가 3시간 뒤로 예약돼 있으면, 큐는 살아 있었지만 알림은
        여전히 늦는다. 상한이 "복구되면 늦어도 이 시간 안에는 나간다"를 보장한다.
    """
    delay = policy.OUTBOX_BACKOFF_BASE_SEC * (2 ** max(0, attempt_count - 1))
    return min(delay, policy.OUTBOX_BACKOFF_MAX_SEC)


def flush(notifier: GuardianNotifier, *, limit: int | None = None) -> dict[str, int]:
    """보낼 때가 된 알림을 전달한다.

    무엇을 하는가
        next_attempt_at 이 지난 PENDING 을 오래된 순으로 꺼내 전송한다. 성공하면
        SENT 로 표시하고, 실패하면 백오프를 걸어 재예약한다.

    왜 오래된 순인가
        큐의 순서가 사건의 순서다. 복구 직후 최신 것만 먼저 나가면 보호자가 상황을
        역순으로 읽는다.

    누가 호출하는가
        jobs.ticks.outbox_flush(APScheduler). 다른 곳에서 부르지 않는다.

    인자
        notifier: 실제 채널 어댑터. 주입받는 이유는 채널이 아직 미정이고,
            테스트가 실패를 재현할 수 있어야 하기 때문이다.
        limit: 한 번에 처리할 최대 건수. 기본값은 policy 에서 온다.

    반환값
        {"sent": n, "failed": n, "gave_up": n} — 틱이 로그로 남긴다.

    주의사항
        - 전송 성공을 기록하는 UPDATE 가 실패하면 같은 알림을 두 번 보낼 수 있다.
          중복 알림은 누락보다 훨씬 나은 실패이므로 이 방향을 택했다.
        - 포기할 때는 요란하게 포기한다(ERROR 로그). 조용히 버리면 아무도 모른다.
    """
    connection = outbox_db()
    schema.init_outbox(connection)
    batch_size = limit if limit is not None else policy.OUTBOX_FLUSH_BATCH_SIZE

    rows = connection.execute(
        "SELECT * FROM outbox WHERE status = 'PENDING' AND next_attempt_at <= ? "
        "ORDER BY created_at, id LIMIT ?",
        (clock.now(), batch_size),
    ).fetchall()

    result = {"sent": 0, "failed": 0, "gave_up": 0}

    for row in rows:
        payload = json.loads(row["payload"])
        now = clock.now()

        # 사건이 벌어진 뒤 오래 지났으면 보호자에게 그 사실을 함께 알린다.
        # 원래 시각도 넣어서, 보호자가 "언제 일이었는지"를 알 수 있게 한다.
        age = now - row["created_at"]
        delayed = age > policy.OUTBOX_DELAYED_THRESHOLD_SEC
        if delayed:
            payload = {
                **payload,
                "delayed": True,
                "occurred_at": row["created_at"],
                "delayed_by_sec": round(age, 1),
            }

        attempt_count = row["attempt_count"] + 1
        try:
            notifier.notify_guardian(row["tier"], payload)
        except NotifyError as error:
            max_attempts = policy.OUTBOX_MAX_ATTEMPTS.get(row["tier"])
            # T1 은 max_attempts 에 없다. 생명 안전 알림을 시도 횟수로 버리지 않는다.
            if max_attempts is not None and attempt_count >= max_attempts:
                connection.execute(
                    "UPDATE outbox SET status = 'GAVE_UP', attempt_count = ?, "
                    "last_error = ? WHERE id = ?",
                    (attempt_count, str(error), row["id"]),
                )
                result["gave_up"] += 1
                logger.error(
                    "outbox giving up after %d attempts: tier=%s id=%s error=%s",
                    attempt_count,
                    row["tier"],
                    row["id"],
                    error,
                )
                continue

            connection.execute(
                "UPDATE outbox SET attempt_count = ?, next_attempt_at = ?, "
                "last_error = ? WHERE id = ?",
                (attempt_count, now + _backoff_delay(attempt_count), str(error), row["id"]),
            )
            result["failed"] += 1
            logger.warning(
                "outbox delivery failed, will retry: tier=%s id=%s attempt=%d error=%s",
                row["tier"],
                row["id"],
                attempt_count,
                error,
            )
            continue

        connection.execute(
            "UPDATE outbox SET status = 'SENT', attempt_count = ?, sent_at = ?, "
            "delayed = ? WHERE id = ?",
            (attempt_count, now, 1 if delayed else 0, row["id"]),
        )
        result["sent"] += 1

    return result
