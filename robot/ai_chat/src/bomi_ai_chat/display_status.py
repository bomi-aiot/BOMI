"""시연 LCD가 읽을 수 있도록 AI 대화 상태를 가볍게 공유한다."""

from __future__ import annotations

import os
from pathlib import Path


def publish(value: str) -> None:
    """설정된 상태 파일에 현재 상태를 원자적으로 기록한다."""
    target_value = os.getenv("BOMI_DISPLAY_STATUS_FILE", "").strip()
    if not target_value:
        return
    target = Path(target_value)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(value.strip().upper() + "\n", encoding="utf-8")
        temporary.replace(target)
    except OSError:
        # 화면 표시 실패가 대화 자체를 중단시키면 안 된다.
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
