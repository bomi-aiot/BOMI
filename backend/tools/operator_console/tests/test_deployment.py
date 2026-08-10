"""운영자 콘솔의 공개 경로와 접근 제어 배포 계약을 검증한다."""

from pathlib import Path
import tomllib
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class OperatorConsoleDeploymentTest(unittest.TestCase):
    """Streamlit, Compose, Nginx 설정이 같은 공개 경로를 사용하는지 검증한다."""

    def test_streamlit_uses_operator_console_base_path(self) -> None:
        """Streamlit 정적 파일과 WebSocket이 하위 경로에서 제공되어야 한다."""

        config_path = REPOSITORY_ROOT / "backend/tools/operator_console/.streamlit/config.toml"
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(config["server"]["baseUrlPath"], "operator-console")

    def test_compose_healthcheck_and_nginx_mount_match_public_path(self) -> None:
        """상태 확인과 인증 파일 마운트가 배포 구성에서 빠지면 안 된다."""

        compose = (REPOSITORY_ROOT / "infra/compose.prod.yml").read_text(encoding="utf-8")

        self.assertIn("/operator-console/_stcore/health", compose)
        self.assertIn("NGINX_OPERATOR_CONSOLE_HTPASSWD_FILE", compose)
        self.assertIn("operator-console:\n        condition: service_healthy", compose)

    def test_nginx_requires_authentication_before_proxying(self) -> None:
        """공개 도메인에서 인증 없이 안전 제어 화면을 열 수 없어야 한다."""

        nginx = (REPOSITORY_ROOT / "infra/nginx/conf.d/bomi.conf").read_text(encoding="utf-8")
        location_start = nginx.index("location ^~ /operator-console/")
        location_end = nginx.index("\n    }", location_start)
        location = nginx[location_start:location_end]

        self.assertIn('auth_basic "BOMI Operator Console"', location)
        self.assertIn("auth_basic_user_file /etc/nginx/operator-console.htpasswd", location)
        self.assertIn("proxy_pass http://operator-console:8501", location)
        self.assertIn("proxy_set_header Upgrade $http_upgrade", location)


if __name__ == "__main__":
    unittest.main()
