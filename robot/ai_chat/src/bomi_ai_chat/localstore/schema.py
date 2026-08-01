"""로컬 SQLite 스키마 — 표 정의를 한곳에 모은다.

왜 Flyway 같은 마이그레이션 도구가 없는가
    이 DB 는 '사실'이 아니라 '운영 상태'다. 서버 ERD 와 달리 유실돼도 재구성되고,
    보호자 앱이 읽지 않는다. 그래서 스키마 버전을 무겁게 관리하지 않고,
    CREATE TABLE IF NOT EXISTS 로 멱등하게 만든다.

    단 하나 예외가 outbox 다. 그건 유실되면 안 되므로, 컬럼을 바꿔야 할 때는
    이 파일에 마이그레이션을 명시적으로 적는다(현재는 초기 버전이라 없다).

참고
    CLAUDE.md §5 (무엇이 로컬에 사는가), §19 (Outbox)
"""

from __future__ import annotations

import sqlite3

# 운영 상태 DB ---------------------------------------------------------------

# 어르신 한 명당 한 행. 재부팅을 넘어 살아남아야 하는 스칼라 값들이다.
#
# 왜 컬럼이 아니라 어르신별 한 행인가
#   한 대의 로봇이 한 명을 돌보지만, thread_id 가 어르신 id 인 것과 같은 이유로
#   키를 명시한다. 두 어르신의 상태가 섞이면 한 사람의 발화가 다른 사람의
#   에스컬레이션을 억제한다. 안전 시스템에서 그건 조용한 실패다.
_RUNTIME_STATE = """
CREATE TABLE IF NOT EXISTS runtime_state (
    senior_id                TEXT    NOT NULL PRIMARY KEY,
    silence_level            INTEGER NOT NULL DEFAULT 0,
    -- HOME / AWAY / UNKNOWN. 기본값이 UNKNOWN 인 이유는 현관 노드로부터 아직
    -- 아무 소식도 못 들었는데 HOME 이라고 가정하면 빈 집에 사다리가 돌기 때문이다.
    occupancy                TEXT    NOT NULL DEFAULT 'UNKNOWN',
    occupancy_observed_at    REAL    NOT NULL DEFAULT 0,
    rest_state               TEXT    NOT NULL DEFAULT 'UNKNOWN',
    last_spoke_at            REAL    NOT NULL DEFAULT 0,
    last_user_interaction_at REAL    NOT NULL DEFAULT 0,
    door_heartbeat_at        REAL    NOT NULL DEFAULT 0,
    updated_at               REAL    NOT NULL DEFAULT 0
)
"""

# 게이트를 기다리는 발화 제안.
#
# 용어 주의: 'candidate' 가 아니라 'proposal' 이다. DB(서버)가 candidate 라는 단어를
# fact_candidate 로 이미 소유하고 있다 (CLAUDE.md §4).
_PROPOSALS = """
CREATE TABLE IF NOT EXISTS speech_proposal (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    senior_id   TEXT    NOT NULL,
    intent      TEXT    NOT NULL,
    priority    TEXT    NOT NULL,
    seed        TEXT    NOT NULL DEFAULT '',
    -- NULL 이면 만료가 없다. 인사는 수십 초짜리 TTL 이 있고, 복약 알림은 보통 없다.
    -- 복약은 사라지는 대신 나중에 다시 와야 하기 때문이다.
    expires_at  REAL,
    origin      TEXT    NOT NULL DEFAULT '',
    -- 핸들러별 부가 정보(fact_candidate id, 질문 코드 등)를 JSON 문자열로.
    meta        TEXT    NOT NULL DEFAULT '{}',
    created_at  REAL    NOT NULL
)
"""

_PROPOSALS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_speech_proposal_senior
    ON speech_proposal (senior_id, created_at)
"""

# 캐시된 TTS 오디오의 '등록부'. 오디오 자체는 파일로 둔다.
#
# 왜 blob 이 아닌가
#   WAV 를 SQLite blob 으로 넣으면 DB 파일이 수십 MB 로 커지고, WAL 체크포인트마다
#   그 크기가 microSD 쓰기로 돌아온다. 파일로 두면 한 번 쓰고 계속 읽기만 한다.
#   오프라인에서 침묵 사다리가 살아 있게 하는 것이 목적이므로(§18) 읽기 전용에 가깝다.
_AUDIO_CACHE = """
CREATE TABLE IF NOT EXISTS cached_audio (
    cache_key   TEXT NOT NULL PRIMARY KEY,
    -- localstore_dir 기준 상대 경로. 절대 경로를 넣으면 SD카드를 옮길 때 깨진다.
    file_name   TEXT NOT NULL,
    text        TEXT NOT NULL,
    created_at  REAL NOT NULL
)
"""

# 발신 큐 DB ----------------------------------------------------------------

# 보호자에게 나가야 하는 알림.
#
# 이 표는 별도 DB 파일에 있고 synchronous=FULL 이다. 이유는 db.py 참고.
_OUTBOX = """
CREATE TABLE IF NOT EXISTS outbox (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    -- T1 / T2 / T3. T4 는 여기 오지 않는다. '절대 보내지 않음'이므로 큐에 들어갈
    -- 일이 없고, T4 는 기억의 공개범위로 표현된다 (CLAUDE.md §9).
    tier           TEXT    NOT NULL,
    payload        TEXT    NOT NULL,
    -- PENDING / SENT / GAVE_UP
    status         TEXT    NOT NULL DEFAULT 'PENDING',
    attempt_count  INTEGER NOT NULL DEFAULT 0,
    -- 사건이 '벌어진' 시각. 전송 시각과 다르며, 지연 표시의 기준이 된다.
    created_at     REAL    NOT NULL,
    -- 이 시각 전에는 재시도하지 않는다. 백오프가 여기 표현된다.
    next_attempt_at REAL   NOT NULL,
    sent_at        REAL,
    -- 늦게 도착했음을 보호자에게 알렸는가. 보호자가 "지금 일"과 "두 시간 전 일"을
    -- 구분하지 못하면 이미 지나간 상황에 지금 놀라게 된다.
    delayed        INTEGER NOT NULL DEFAULT 0,
    last_error     TEXT
)
"""

# flush 는 "보낼 때가 된 PENDING"만 찾는다. 대부분의 행은 곧 SENT 가 되므로
# 부분 인덱스로 대기 중인 것만 색인한다.
_OUTBOX_INDEX = """
CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON outbox (next_attempt_at)
    WHERE status = 'PENDING'
"""


# 마지막으로 성공한 대화 문맥. 어르신당 한 행.
#
# 왜 질의별이 아니라 어르신별 하나인가
#   오프라인일 때 필요한 것은 "이 질문에 딱 맞는 기억"이 아니라 "이 어르신이 누구인지"다.
#   질의별로 쌓으면 microSD 쓰기만 늘고 적중률은 오르지 않는다.
#
# 이 표는 '사실의 권위'가 아니다. 여기서 읽은 턴은 ctx_is_cached 로 표시되고,
# 그 표시가 프롬프트로 이어져 복약·일정에 대한 단정적 표현을 막는다.
_CONTEXT_CACHE = """
CREATE TABLE IF NOT EXISTS context_cache (
    senior_id TEXT NOT NULL PRIMARY KEY,
    payload   TEXT NOT NULL,
    cached_at REAL NOT NULL
)
"""


def init_runtime(connection: sqlite3.Connection) -> None:
    """운영 상태 DB 의 표를 만든다. 멱등하다."""
    connection.execute(_RUNTIME_STATE)
    connection.execute(_PROPOSALS)
    connection.execute(_PROPOSALS_INDEX)
    connection.execute(_AUDIO_CACHE)
    connection.execute(_CONTEXT_CACHE)


def init_outbox(connection: sqlite3.Connection) -> None:
    """발신 큐 DB 의 표를 만든다. 멱등하다."""
    connection.execute(_OUTBOX)
    connection.execute(_OUTBOX_INDEX)
