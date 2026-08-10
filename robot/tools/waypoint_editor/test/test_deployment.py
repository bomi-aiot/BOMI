"""웨이포인트 편집기의 운영 배포 계약을 검증한다."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_streamlit_uses_waypoint_editor_base_path() -> None:
    """정적 파일과 WebSocket이 공개 하위 경로를 사용해야 한다."""

    config_path = REPOSITORY_ROOT / "robot/tools/waypoint_editor/.streamlit/config.toml"
    config = config_path.read_text(encoding="utf-8")

    assert 'baseUrlPath = "waypoint-editor"' in config


def test_compose_runs_read_only_authenticated_editor() -> None:
    """운영 컨테이너는 직접 저장 없이 인증 프록시 뒤에서 실행되어야 한다."""

    compose = (REPOSITORY_ROOT / "infra/compose.prod.yml").read_text(encoding="utf-8")
    nginx = (REPOSITORY_ROOT / "infra/nginx/conf.d/bomi.conf").read_text(encoding="utf-8")
    location_start = nginx.index("location ^~ /waypoint-editor/")
    location_end = nginx.index("\n    }", location_start)
    location = nginx[location_start:location_end]

    assert 'WAYPOINT_EDITOR_ALLOW_SERVER_WRITE: "false"' in compose
    assert "/waypoint-editor/_stcore/health" in compose
    assert "location ^~ /waypoint-editor/" in nginx
    assert "NGINX_WAYPOINT_EDITOR_HTPASSWD_FILE" in compose
    assert "auth_basic_user_file /etc/nginx/waypoint-editor.htpasswd" in location
    assert "operator-console.htpasswd" not in location
    assert "proxy_pass http://waypoint-editor:8501" in location
