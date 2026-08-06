"""오프라인용 캐시 TTS 오디오 등록부.

왜 존재하는가
    네트워크가 없으면 TTS API 를 부를 수 없고, 로봇은 한 마디도 못 한다. 그런데
    하필 그 순간이 침묵 사다리가 마지막 프로브를 던져야 할 때일 수 있다. 그래서
    critical 프로브 몇 문장("어르신, 괜찮으세요?")은 미리 렌더링해 파일로 둔다.
    오프라인 대비 필수 2건 중 하나다 (CLAUDE.md §18).

왜 blob 이 아니라 파일 + 등록부인가
    WAV 를 SQLite blob 으로 넣으면 DB 가 수십 MB 가 되고, WAL 체크포인트마다 그
    크기가 microSD 쓰기로 돌아온다. 파일은 한 번 쓰고 계속 읽기만 한다.
    등록부에는 경로만 둔다.

    경로는 localstore_dir '기준 상대 경로'로 저장한다. 절대 경로를 넣으면 SD카드를
    다른 기기로 옮기거나 덤프를 복원할 때 전부 깨진다.

참고
    CLAUDE.md §10 (프로브), §18 (오프라인 대비)
"""

from __future__ import annotations

from pathlib import Path

from bomi_ai_chat.clock import clock
from bomi_ai_chat.localstore import schema
from bomi_ai_chat.localstore.db import audio_cache_dir, runtime_db


def register(cache_key: str, audio_bytes: bytes, text: str) -> Path:
    """오디오를 파일로 쓰고 등록부에 남긴다.

    누가 호출하는가
        프로비저닝 스크립트, 또는 온라인일 때 미리 렌더링해두는 준비 작업.
        대화 턴 경로에서 부르지 않는다.

    인자
        cache_key: 안정적인 식별자(예: "probe.critical.1"). 파일명이 되므로
            경로 구분자가 들어가면 안 된다.

    반환값
        기록된 파일의 절대 경로.
    """
    if "/" in cache_key or "\\" in cache_key:
        raise ValueError(f"cache_key 에 경로 구분자를 쓸 수 없습니다: {cache_key}")

    file_name = f"{cache_key}.wav"
    path = audio_cache_dir() / file_name
    path.write_bytes(audio_bytes)

    connection = runtime_db()
    schema.init_runtime(connection)
    connection.execute(
        "INSERT INTO cached_audio (cache_key, file_name, text, created_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(cache_key) DO UPDATE SET "
        "file_name = excluded.file_name, text = excluded.text, "
        "created_at = excluded.created_at",
        (cache_key, file_name, text, clock.now()),
    )
    return path


def lookup(cache_key: str) -> Path | None:
    """캐시된 오디오 경로를 찾는다. 없으면 None.

    주의사항
        등록부에 있어도 파일이 사라졌을 수 있다(SD카드 손상, 수동 삭제). 그래서
        존재 여부를 실제로 확인한다. 여기서 없는 파일 경로를 돌려주면, 호출부는
        오프라인 상황에서 두 번 실패한다.
    """
    connection = runtime_db()
    schema.init_runtime(connection)
    row = connection.execute(
        "SELECT file_name FROM cached_audio WHERE cache_key = ?", (cache_key,)
    ).fetchone()
    if row is None:
        return None

    path = audio_cache_dir() / row["file_name"]
    return path if path.exists() else None
