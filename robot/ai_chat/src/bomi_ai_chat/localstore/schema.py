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
    -- occupancy 가 AWAY 로 '전이한' 시각. 0 이면 지금 나가 있지 않다.
    --
    -- 왜 occupancy_observed_at 으로 대신하지 않는가
    --   그 값은 "이 값을 마지막으로 관측한 시각"이다. AWAY 를 다시 관측하면 갱신되고,
    --   그러면 부재 시간이 매번 0 으로 리셋되어 미귀가 알림이 영원히 안 나간다.
    --   부재 '시작' 시각은 따로 들고 있어야 한다.
    away_since               REAL    NOT NULL DEFAULT 0,
    -- 문이 열린 시각. 0 이면 닫혀 있거나 아직 모른다.
    -- 재부팅을 넘어 살아남아야 한다 — 재부팅 사이에 열린 채 방치된 문이 바로
    -- 알려야 할 상황이다.
    door_open_since          REAL    NOT NULL DEFAULT 0,
    -- 지금 열려 있는 대화의 id. NULL 이면 열린 대화가 없다(유휴 임계값을 넘겼거나
    -- 아직 시작 전). graph/ingress.note_interaction 이 경계를 넘을 때 여기를 지우고,
    -- graph/build.memory_write 가 서버가 배정한 id 로 다시 채운다.
    --
    -- 왜 여기 있는가 (S15P11E102-306)
    --   스케줄러(jobs/scheduler.py)의 contract_tick 은 그래프 checkpoint 를 직접
    --   보지 못한다(별도 스레드). "지금 이 대화" 를 알아야 "한 대화에 후보 하나"
    --   규칙(CLAUDE.md §12)을 지킬 수 있으므로, 다른 운영 상태와 같은 자리에 둔다.
    conversation_id          TEXT,
    updated_at               REAL    NOT NULL DEFAULT 0
)
"""

# runtime_state 에 뒤늦게 추가된 컬럼.
#
# 왜 이 목록이 필요한가
#   CREATE TABLE IF NOT EXISTS 는 '이미 있는' 표에 컬럼을 더해주지 않는다. 그래서
#   이미 돌고 있던 로봇의 DB 는 새 컬럼 없이 남고, SELECT * 로 읽는 쪽이 KeyError 로
#   죽는다. 스키마 버전을 무겁게 관리하지는 않지만, 이 정도는 명시해야 한다.
#
#   (컬럼명, 타입과 기본값) 순서. ALTER TABLE ADD COLUMN 은 되돌릴 수 없으므로
#   기본값이 '아직 모른다'를 뜻하는 값이어야 한다. 여기서는 둘 다 0 이다.
_RUNTIME_STATE_ADDED_COLUMNS = (
    ("away_since", "REAL NOT NULL DEFAULT 0"),
    ("door_open_since", "REAL NOT NULL DEFAULT 0"),
    # 안전 확인 질문의 마감 시각. 0 이면 대기 중인 확인이 없다.
    #
    # 왜 내구 저장소에 있는가
    #   어르신이 확인 질문에 아예 대답하지 않으면 그래프는 다시 호출되지 않는다.
    #   틱이 마감을 보려면 그래프 밖에서 읽을 수 있어야 하고, 재부팅을 넘어야 한다 —
    #   증상을 말한 직후에 로봇이 재시작했다고 그 확인이 사라지면 안 된다.
    ("safety_check_until", "REAL NOT NULL DEFAULT 0"),
    # 마지막으로 보호자 알림을 큐에 넣은 시각과 그 사유. 같은 사유의 알림이
    # 짧은 시간에 반복되는 것을 막는 데 쓴다(graph/triage.py 의 escalation).
    # 0 은 '아직 한 번도 없음'이다.
    ("last_escalation_at", "REAL NOT NULL DEFAULT 0"),
    ("last_escalation_reason", "TEXT"),
    # 지금 열려 있는 대화의 id. NULL 허용 — "아직 모른다"가 아니라 "열린 대화가
    # 없다"는 뜻이라 0 같은 자리표시자 대신 진짜 NULL 이 맞다 (S15P11E102-306).
    ("conversation_id", "TEXT"),
)

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


# 오늘 이미 처리된 슬롯.
#
# 게이트 1 이 "9시 복약 알림을 아직 말할 가치가 있는가"를 판정할 때 본다.
# 8시 55분에 어르신이 "약 먹었어"라고 하면 여기 한 행이 생기고, 9시 알림은 폐기된다.
#
# slot_key 에 날짜가 들어간다. 안 넣으면 어제 완료가 오늘 알림을 영원히 막는다.
_COMPLETED_SLOT = """
CREATE TABLE IF NOT EXISTS completed_slot (
    senior_id    TEXT NOT NULL,
    slot_key     TEXT NOT NULL,
    completed_at REAL NOT NULL,
    PRIMARY KEY (senior_id, slot_key)
)
"""


# 이미 보낸 현관 알림.
#
# 왜 필요한가
#   door_watch_tick 은 60초마다 돈다. 부재 6시간을 넘긴 상태는 그 뒤로 계속 참이므로,
#   중복 방지가 없으면 매 분 T2 가 하나씩 쌓인다. 보호자 화면이 같은 알림으로 도배되고,
#   그러면 보호자가 알림을 읽지 않게 되고, 그때부터 진짜를 놓친다.
#
#   completed_slot 을 재사용하지 않는 이유는 그 표의 뜻이 "오늘 이 권유 슬롯을 이미
#   다뤘다"이고 게이트 1 이 그것을 읽기 때문이다. 뜻이 다른 값을 같은 표에 넣으면
#   나중에 둘 중 하나를 지우기 어려워진다.
#
#   alert_key 에 '상태가 시작된 시각'을 넣는다. 그래야 어르신이 돌아왔다가 다시 나가면
#   새 키가 되어 다시 알릴 수 있다. 날짜를 넣으면 하루에 한 번으로 묶여버린다.
_DOOR_ALERT = """
CREATE TABLE IF NOT EXISTS door_alert (
    senior_id  TEXT NOT NULL,
    alert_key  TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (senior_id, alert_key)
)
"""


# 발화 이력 — 같은 종류의 알림에서 최근에 뭐라고 말했는지 (S15P11E102-256).
#
# 왜 필요한가
#   §17.8 은 "같은 권유가 사흘 연속 토씨까지 같지 않아야 한다"를 요구한다. 그런데
#   프롬프트 빌더(prompts/builder.py._format_recent_phrasings)는 이미 오래전부터
#   그 문구를 받을 자리를 갖고 있었고, 채워주는 코드만 없었다 — 이 표가 그 값을
#   만드는 쪽이다.
#
# phrasing_key 는 graph/phrasing.phrasing_key(origin, intent) 가 만든다. 이 표는
# 그 키가 무엇을 뜻하는지 모른다 — 그냥 문자열로 저장하고 그대로 조회에 쓴다.
_SPOKEN_PHRASING = """
CREATE TABLE IF NOT EXISTS spoken_phrasing (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    senior_id    TEXT    NOT NULL,
    phrasing_key TEXT    NOT NULL,
    text         TEXT    NOT NULL,
    spoken_at    REAL    NOT NULL
)
"""

# 조회(같은 senior_id + phrasing_key, 최신순)와 정리(보관 기간·개수 상한) 모두
# 이 세 컬럼으로 걸러진다. 색인이 없으면 발화 이력이 쌓일수록 매 턴 전체 스캔이다.
_SPOKEN_PHRASING_INDEX = """
CREATE INDEX IF NOT EXISTS idx_spoken_phrasing_lookup
    ON spoken_phrasing (senior_id, phrasing_key, spoken_at)
"""


# 정서 신호 누적 표 (S15P11E102-253).
#
# 왜 발화 원문을 저장하지 않는가
#   이 표는 "정서 발화가 몇 번 있었는가", "이 대화가 봉인됐는가"만 알면 되고,
#   무슨 말을 했는지는 몰라도 된다. 원문을 담으면 T4("우리끼리 얘기") 약속이
#   이 표 자체에서 깨진다 — 아무에게도 보내지 않는다고 해놓고 로컬 DB에 그대로
#   남아 있으면, 언젠가 이 표를 읽는 코드가 생기는 순간 약속이 깨진다.
#
# sealed 컬럼이 있는 이유
#   "우리끼리 얘기" 같은 봉인 표지가 나온 대화는 이후 그 대화로는 절대 동의
#   질문을 만들지 않는다(CLAUDE.md §9 T4). 신호 누적과 봉인 표시를 같은 표에
#   두는 이유는 chat.py 의 ticket 본문이 요구하는 모양이 그대로다 — 표지 종류,
#   시각, sealed, conversation_id 만 담는다.
#
# consumed 컬럼이 있는 이유
#   동의 질문을 한 번 올리면 그 질문에 기여한 신호들을 다시 세면 안 된다.
#   안 지우면(또는 안 지웠다 표시하면) 다음 틱이 같은 신호를 또 세어, 답이
#   오기도 전에 두 번째 질문이 큐에 쌓인다.
#
# ★ 253 은 이 표를 '문턱 하나만 넘으면 큐잉'하는 최소 형태로 쓴다. 우울·고립
#   추세를 보는 정교한 누적(S15P11E102-255)은 이 표를 확장해서 붙는다 —
#   그래서 인터페이스(record_signal/pending_signal_count 등)를 명확히 남겨둔다.
_EMOTIONAL_SIGNAL = """
CREATE TABLE IF NOT EXISTS emotional_signal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    senior_id       TEXT    NOT NULL,
    conversation_id TEXT    NOT NULL DEFAULT '',
    -- 'emotional' = 정서 발화 신호. 'seal' = 봉인 표지("우리끼리 얘기" 등).
    signal_type     TEXT    NOT NULL,
    sealed          INTEGER NOT NULL DEFAULT 0,
    consumed        INTEGER NOT NULL DEFAULT 0,
    created_at      REAL    NOT NULL
)
"""

_EMOTIONAL_SIGNAL_INDEX = """
CREATE INDEX IF NOT EXISTS idx_emotional_signal_lookup
    ON emotional_signal (senior_id, conversation_id)
"""


# T3 동의 요청의 생애주기 (S15P11E102-253).
#
# 왜 별도 표인가
#   speech_proposal 은 "말할 것을 제안한다"는 뜻이고, 게이트가 이기거나 지면
#   지워진다(§7). 동의 요청은 그보다 오래 살아야 한다 — 질문을 '한' 뒤에도
#   어르신의 "응"/"아니" 답을 어느 요청에 대한 것인지 알아야 하고, 그 요청은
#   질문 제안이 큐에서 지워진 뒤에도 PENDING 으로 남아 있어야 한다.
#
# status 가 왜 네 가지인가
#   PENDING    질문을 올렸지만(또는 올리기로 확정했지만) 아직 답이 없다.
#   GRANTED    "응". outbox 에 T3 한 건이 나갔다.
#   DECLINED   "아니". 아무것도 나가지 않는다. 다시 묻지 않는다.
#   EXPIRED    질문 자체가 TTL 을 넘겨 게이트에서 폐기됐다. 답을 들을 기회가
#              없었다는 뜻이라 GRANTED/DECLINED 와 구분한다.
_CONSENT_REQUEST = """
CREATE TABLE IF NOT EXISTS consent_request (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    senior_id       TEXT    NOT NULL,
    conversation_id TEXT,
    status          TEXT    NOT NULL DEFAULT 'PENDING',
    created_at      REAL    NOT NULL,
    resolved_at     REAL
)
"""

_CONSENT_REQUEST_INDEX = """
CREATE INDEX IF NOT EXISTS idx_consent_request_senior
    ON consent_request (senior_id, status)
"""


# 대화에서 뽑아낼 '사실 추출' 대기열 (S15P11E102-255).
#
# 어디서 채워지고 어디서 비워지는가
#   graph/build.memory_write 가 반응형 턴이 끝날 때마다(스킵 조건을 통과하면)
#   한 행을 남긴다. LLM 호출은 여기서 하지 않는다 — jobs/ticks.extraction_flush
#   가 턴 밖에서 이 표를 읽어 뽑고, backend_client/fact_client 로 제출한 뒤에만
#   extracted = 1 로 표시한다.
#
# 왜 conversation_id / source_message_id 가 nullable 인가
#   서버가 이번 턴의 대화·메시지 id 를 못 돌려준 경우(오프라인, 일시 장애)가
#   있다. memory_write 는 그 경우 애초에 큐잉하지 않지만(sourceMessageId 없이
#   넣으면 백엔드의 FactCandidate.fromConversationMessage 가 항상 거절한다),
#   표 자체는 두 값이 비어 있는 행을 받아들일 수 있어야 한다 — 그래야 이후
#   호출부가 바뀌어도(예: 로봇이 스스로 판단해 넣는 경로가 생겨도) 스키마를
#   다시 손대지 않는다.
#
# 왜 발화 원문(content)을 그대로 담는가
#   emotional_signal 과 다르다. 저 표는 "정서 발화가 있었다"는 사실만 있으면
#   되지만, 이 표는 LLM 이 나중에(flush 시점에) 실제로 무엇을 뽑을지 다시
#   읽어야 하므로 원문이 필요하다. 대신 이 표는 처리되고 나면(extracted=1)
#   더 이상 아무도 읽지 않는 죽은 행이 된다 — 원문을 영구 보관하는 표가 아니다.
#
# preceding_robot_utterance 가 왜 필요한가
#   "요즘 손자가 자주 놀러 와요"만 보면 자연스러운 문장이지만, 로봇이 방금
#   "요즘 가족들은 잘 지내세요?"라고 물었다는 맥락이 있어야 추출 프롬프트가
#   무엇에 대한 답인지 안다. 이 값이 없으면 LLM 이 맥락 없는 한 문장만 보고
#   추측하게 된다.
_EXTRACTION_JOB = """
CREATE TABLE IF NOT EXISTS extraction_job (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    senior_id                 TEXT    NOT NULL,
    conversation_id           TEXT,
    source_message_id         TEXT,
    content                   TEXT    NOT NULL,
    preceding_robot_utterance TEXT    NOT NULL DEFAULT '',
    -- 0 = 아직 flush 가 처리하지 않았다. 1 = 처리 완료(뽑을 것이 없었거나,
    -- 뽑아서 백엔드 제출까지 성공했다). 제출에 실패하면 0 인 채로 남아
    -- 다음 flush 가 다시 시도한다 (jobs/ticks.extraction_flush 참고).
    extracted                 INTEGER NOT NULL DEFAULT 0,
    created_at                REAL    NOT NULL
)
"""

# flush 는 "아직 처리 안 된" 행만, 오래된 순으로 찾는다. outbox 와 같은 이유로
# 부분 인덱스를 쓴다 — 대부분의 행은 곧 extracted=1 이 되므로 대기 중인 것만
# 색인하는 편이 표가 커져도 조회가 느려지지 않는다.
_EXTRACTION_JOB_INDEX = """
CREATE INDEX IF NOT EXISTS idx_extraction_job_pending
    ON extraction_job (created_at)
    WHERE extracted = 0
"""


def init_runtime(connection: sqlite3.Connection) -> None:
    """운영 상태 DB 의 표를 만든다. 멱등하다."""
    connection.execute(_RUNTIME_STATE)
    _add_missing_columns(connection, "runtime_state", _RUNTIME_STATE_ADDED_COLUMNS)
    connection.execute(_PROPOSALS)
    connection.execute(_PROPOSALS_INDEX)
    connection.execute(_AUDIO_CACHE)
    connection.execute(_CONTEXT_CACHE)
    connection.execute(_COMPLETED_SLOT)
    connection.execute(_DOOR_ALERT)
    connection.execute(_SPOKEN_PHRASING)
    connection.execute(_SPOKEN_PHRASING_INDEX)
    # 등록을 빠뜨리면 "no such table" 이 조용히 삼켜져(핸들러의 예외 방어) 정서
    # 신호가 하나도 안 쌓인다 — 티켓 본문이 특별히 경고하는 함정이다.
    connection.execute(_EMOTIONAL_SIGNAL)
    connection.execute(_EMOTIONAL_SIGNAL_INDEX)
    connection.execute(_CONSENT_REQUEST)
    connection.execute(_CONSENT_REQUEST_INDEX)
    connection.execute(_EXTRACTION_JOB)
    connection.execute(_EXTRACTION_JOB_INDEX)


def _add_missing_columns(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[tuple[str, str], ...],
) -> None:
    """이미 존재하는 표에 빠진 컬럼을 더한다. 멱등하다.

    왜 try/except 가 아니라 PRAGMA 로 확인하는가
        "duplicate column name" 만 삼키려면 예외 메시지를 문자열로 비교해야 하고,
        그러면 SQLite 버전이 문구를 바꿀 때 조용히 깨진다. 있는지 먼저 보는 편이
        읽기도 쉽다.
    """
    existing = {
        row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, definition in columns:
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_outbox(connection: sqlite3.Connection) -> None:
    """발신 큐 DB 의 표를 만든다. 멱등하다."""
    connection.execute(_OUTBOX)
    connection.execute(_OUTBOX_INDEX)
