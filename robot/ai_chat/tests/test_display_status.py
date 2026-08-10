"""AI 대화 상태의 LCD 공유 파일을 검증한다."""

from bomi_ai_chat.display_status import publish


def test_publish_is_disabled_without_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("BOMI_DISPLAY_STATUS_FILE", raising=False)
    publish("LISTENING")
    assert list(tmp_path.iterdir()) == []


def test_publish_replaces_current_status(monkeypatch, tmp_path):
    target = tmp_path / "status"
    monkeypatch.setenv("BOMI_DISPLAY_STATUS_FILE", str(target))
    publish("listening")
    publish("thinking")
    assert target.read_text(encoding="utf-8") == "THINKING\n"
