"""로봇 로컬 운영 상태 저장소 — 로컬 SQLite 를 만지는 유일한 패키지.

무엇이 여기 사는가 (CLAUDE.md §5)
    발화 제안 큐, silence_level, occupancy, last_spoke_at, LangGraph checkpointer,
    캐시 TTS 오디오, 보호자 알림 발신 큐.

무엇이 여기 살지 '않는가'
    사실(fact). 프로필·기억·복약·동의는 백엔드 Postgres 가 권위이고 backend_client
    를 통해 온다. 복약 스케줄의 진실이 두 곳에 있는 것은 품질 문제가 아니라 안전
    버그다.

절대 규칙
    핸들러와 그래프 노드는 sqlite3 를 직접 만지지 않는다. 이 패키지를 통한다.

파일이 두 개인 이유
    runtime.sqlite 는 쓰기가 잦아 내구성을 완화했고(microSD 수명),
    outbox.sqlite 만 synchronous=FULL 이다. 마지막 몇 초의 운영 상태는 잃어도 되지만
    큐에 든 응급 알림은 안 된다. 자세한 근거는 db.py 참고.

참고
    CLAUDE.md §5 (소유권 경계), §18 (SD카드와 오프라인), §19 (Outbox)
"""

from bomi_ai_chat.localstore import (
    audio_cache,
    context_cache,
    outbox,
    proposals,
    runtime,
)
from bomi_ai_chat.localstore.db import (
    close_all,
    localstore_dir,
    outbox_db,
    runtime_db,
    runtime_db_path,
)

__all__ = [
    "audio_cache",
    "context_cache",
    "outbox",
    "proposals",
    "runtime",
    "close_all",
    "localstore_dir",
    "outbox_db",
    "runtime_db",
    "runtime_db_path",
]
