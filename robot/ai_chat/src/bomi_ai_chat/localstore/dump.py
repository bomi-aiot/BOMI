"""로컬 DB 일일 덤프 — 카드 사망을 '사고'에서 '불편'으로 바꾼다.

왜 필요한가
    이 기기의 저장 매체는 microSD 다. 쓰기를 줄이고 내구성을 완화해도 카드는
    언젠가 죽는다. 팀은 그 위험을 받아들였지만, 시연 당일에 죽으면 그건 여전히
    프로젝트 사고다. 하루 한 번 복사해두면 잃는 것이 최대 하루치가 된다.

왜 파일 복사(cp)가 아닌가  ★ 중요
    WAL 모드에서는 방금 커밋된 내용이 아직 -wal 파일에만 있을 수 있다. 그 상태에서
    .sqlite 파일만 복사하면 최근 쓰기가 빠지거나, 최악의 경우 손상된 사본이 된다.
    그래서 SQLite 의 백업 API 를 쓴다. 이건 잠금과 WAL 을 이해하고, 실행 중인
    프로세스를 멈추지 않고도 일관된 사본을 만든다.

사용법
    python -m bomi_ai_chat.localstore.dump /mnt/usb/bomi-backup

    개발 키트에 USB 3.2 포트가 네 개 있다. cron 또는 systemd timer 로 하루 한 번.

참고
    CLAUDE.md §18 (SD카드 제약, 일일 덤프)
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from bomi_ai_chat.clock import clock
from bomi_ai_chat.localstore.db import (
    OUTBOX_DB_NAME,
    RUNTIME_DB_NAME,
    localstore_dir,
    outbox_db,
    runtime_db,
)

logger = logging.getLogger(__name__)


def _backup(source: sqlite3.Connection, destination: Path) -> None:
    """실행 중인 DB 의 일관된 사본을 만든다.

    백업 API 는 대상 DB 로 페이지를 옮긴다. 진행 중에 원본이 바뀌면 알아서 다시
    읽으므로, 프로세스를 멈추지 않아도 된다.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(destination) as target:
        source.backup(target)


def dump(destination_root: Path) -> Path:
    """런타임 DB 와 발신 큐 DB 를 날짜별 디렉터리로 복사한다.

    무엇을 하는가
        destination_root/YYYY-MM-DD/ 아래에 두 DB 를 백업 API 로 복사한다.

    왜 날짜 디렉터리인가
        하나를 덮어쓰면, 어제 카드가 조용히 손상되고 있었을 때 그 손상까지 덮어쓴다.
        날짜별로 남기면 하루 전으로 돌아갈 수 있다. 보관 기간 정리는 운영 몫이다.

    반환값
        만들어진 디렉터리 경로.

    주의사항
        캐시 오디오는 복사하지 않는다. 재생성 가능하고(온라인일 때 다시 렌더링),
        용량이 커서 매일 USB 로 옮길 이유가 없다. 잃으면 안 되는 것은 두 DB 다.
    """
    # 파일명에 쓸 날짜. clock 을 통해서만 시간을 읽는다(CLAUDE.md §15) —
    # 압축 시계로 며칠을 흘리는 시연에서도 덤프가 날짜별로 갈리게 하려면 이래야 한다.
    stamp = datetime.fromtimestamp(clock.now(), tz=timezone.utc).strftime("%Y-%m-%d")
    target_dir = destination_root / stamp

    _backup(runtime_db(), target_dir / RUNTIME_DB_NAME)
    _backup(outbox_db(), target_dir / OUTBOX_DB_NAME)

    logger.info("localstore dumped: source=%s target=%s", localstore_dir(), target_dir)
    return target_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="로봇 로컬 운영 상태 DB 를 날짜별 디렉터리로 백업한다."
    )
    parser.add_argument(
        "destination",
        type=Path,
        help="백업을 둘 루트 디렉터리 (예: /mnt/usb/bomi-backup)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        target = dump(args.destination)
    except (OSError, sqlite3.Error) as error:
        # 조용히 실패하면 백업이 몇 달째 안 되고 있는 줄 아무도 모른다.
        logger.error("localstore dump failed: %s", error)
        return 1

    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
