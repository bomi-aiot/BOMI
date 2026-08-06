"""로컬 SQLite 연결과 내구성 정책 — 이 패키지에서 파일을 여는 유일한 곳.

어디에 위치하는가
    localstore 의 다른 모듈(runtime, proposals, outbox)이 모두 여기서 연결을 받는다.
    그래프 노드나 핸들러가 sqlite3 를 직접 만지지 않는다.

왜 DB 파일이 두 개인가  ★ 이 파일에서 가장 중요한 결정
    이 기기의 저장 매체는 microSD 이고, 끊임없는 작은 쓰기가 카드를 죽인다. 그래서
    쓰기 내구성을 의도적으로 완화한다. 크래시가 나면 마지막 몇 초의 운영 상태를
    잃는데, 그건 괜찮다. silence_level 이 몇 초 낡아도 사람은 다치지 않는다.

    그런데 '큐에 든 응급 알림'은 다르다. 그걸 잃으면 보호자가 T1 을 영원히 못 받는다.
    SQLite 의 synchronous 는 연결(=DB) 단위 설정이라 한 파일 안에서 테이블별로
    내구성을 나눌 수 없다. 그래서 파일을 나눈다.

        runtime.sqlite  synchronous=NORMAL  쓰기가 잦다. 마지막 몇 초는 버려도 된다
        outbox.sqlite   synchronous=FULL    드물게 쓰지만 한 건도 잃으면 안 된다

    LangGraph checkpointer 는 runtime 쪽에 둔다. 매 턴 쓰기가 일어나므로 완화 대상이
    맞고, 한 파일에 모여 있으면 일일 덤프가 단순해진다.

왜 WAL 인가
    기본 저널 모드는 쓰기마다 저널 파일을 만들고 지운다. WAL 은 한 파일에 이어 쓰므로
    작은 쓰기의 개수가 줄고, 읽기가 쓰기를 막지 않는다. 뒤엣것이 특히 중요한데,
    재생 스레드와 스케줄러 틱이 같은 DB 를 동시에 건드린다.

참고
    CLAUDE.md §5 (소유권 경계), §18 (SD카드 제약과 내구성 완화)
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from bomi_ai_chat.config import get_settings

# 파일 이름. 경로는 config.localstore_dir 아래로 붙는다.
RUNTIME_DB_NAME = "runtime.sqlite"
OUTBOX_DB_NAME = "outbox.sqlite"
# 캐시 TTS 오디오는 blob 이 아니라 파일로 둔다. 이유는 audio_cache 주석 참고.
AUDIO_CACHE_DIRNAME = "audio-cache"

# 연결을 프로세스 안에서 재사용한다. 매 호출마다 열고 닫으면 PRAGMA 설정 비용이
# 반복되고, WAL 체크포인트가 연결 종료마다 일어나서 쓰기가 오히려 늘어난다.
_connections: dict[str, sqlite3.Connection] = {}
_lock = threading.Lock()


def localstore_dir() -> Path:
    """운영 상태가 사는 디렉터리. 없으면 만든다."""
    path = Path(get_settings().localstore_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def audio_cache_dir() -> Path:
    """캐시된 TTS 오디오 파일이 사는 디렉터리."""
    path = localstore_dir() / AUDIO_CACHE_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _configure(connection: sqlite3.Connection, *, durable: bool) -> None:
    """새 연결에 저널 모드와 내구성 정책을 적용한다.

    인자
        durable: True 면 synchronous=FULL. 발신 큐 전용이다.

    주의사항
        synchronous 는 DB 단위 설정이다. 이 함수를 호출한 뒤 같은 연결에서
        "이 테이블만 FULL" 같은 걸 할 수 없다. 그래서 파일을 나눴다.
    """
    connection.execute("PRAGMA journal_mode = WAL")
    # FULL  = 커밋마다 fsync. 전원이 끊겨도 커밋된 건은 남는다.
    # NORMAL = OS 에 맡긴다. 크래시 시 마지막 몇 초를 잃을 수 있다.
    connection.execute(
        "PRAGMA synchronous = FULL" if durable else "PRAGMA synchronous = NORMAL"
    )
    # 다른 틱이 쓰는 중이면 즉시 실패하지 말고 잠깐 기다린다. 스케줄러 틱과 대화
    # 턴이 겹치는 것은 정상이고, 그때 예외를 던지면 알림 적재가 실패한다.
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA foreign_keys = ON")


def _connect(name: str, *, durable: bool) -> sqlite3.Connection:
    with _lock:
        existing = _connections.get(name)
        if existing is not None:
            return existing

        # check_same_thread=False 인 이유
        #   그래프를 호출하는 스레드가 하나가 아니다. emit 의 재생은 그래프 실행보다
        #   오래 살고(§13), 침묵 틱과 outbox flush 는 스케줄러 스레드에서 온다.
        #   기본값이면 그때 sqlite3 가 ProgrammingError 를 던진다.
        connection = sqlite3.connect(
            localstore_dir() / name,
            check_same_thread=False,
            isolation_level=None,  # 자동 커밋. 트랜잭션은 필요한 곳에서 명시한다
        )
        connection.row_factory = sqlite3.Row
        _configure(connection, durable=durable)
        _connections[name] = connection
        return connection


def runtime_db() -> sqlite3.Connection:
    """운영 상태용 연결. 쓰기가 잦고 내구성은 완화되어 있다."""
    return _connect(RUNTIME_DB_NAME, durable=False)


def outbox_db() -> sqlite3.Connection:
    """발신 큐용 연결. 이 기기에서 내구성을 완화하지 '않는' 유일한 지점이다."""
    return _connect(OUTBOX_DB_NAME, durable=True)


def runtime_db_path() -> Path:
    """LangGraph checkpointer 가 쓸 파일 경로. 연결을 만들지는 않는다."""
    return localstore_dir() / RUNTIME_DB_NAME


def close_all() -> None:
    """열린 연결을 모두 닫는다.

    누가 호출하는가
        프로세스 종료 훅, 그리고 '재시작'을 흉내내는 테스트. 후자가 이 함수의 주된
        존재 이유다. 연결을 캐시하기 때문에, 닫지 않으면 테스트가 재부팅을 재현할 수 없다.
    """
    with _lock:
        for connection in _connections.values():
            try:
                connection.close()
            except sqlite3.Error:
                # 종료 경로다. 닫기 실패로 프로세스 종료를 막을 이유가 없다.
                pass
        _connections.clear()
