# robot/ai_chat/src/bomi_ai_chat/db/ssh_tunnel.py
"""EC2에 도커로 떠 있는 Postgres 접근용 SSH 터널.
프로세스 실행 중 한 번만 터널을 열고, 이후 요청은 로컬 포트로 재사용한다."""
import atexit

from bomi_ai_chat.config import get_settings

_tunnel = None


def get_local_port() -> int:
    """터널이 아직 안 열려있으면 열고, 로컬에서 접속할 포트 번호를 반환한다."""
    global _tunnel
    if _tunnel is None:
        from sshtunnel import SSHTunnelForwarder

        settings = get_settings()
        settings.validate_ssh_database()
        _tunnel = SSHTunnelForwarder(
            (settings.ec2_host, 22),
            ssh_username=settings.ec2_ssh_user,
            ssh_pkey=settings.ssh_key_path,
            remote_bind_address=(
                settings.remote_db_host,
                settings.remote_db_port,
            ),
        )
        _tunnel.start()
        print(
            "SSH 터널 연결됨 — "
            f"로컬 포트 {_tunnel.local_bind_port} → "
            f"EC2 {settings.remote_db_host}:{settings.remote_db_port}"
        )
    return _tunnel.local_bind_port


def close_tunnel():
    global _tunnel
    if _tunnel is not None:
        _tunnel.stop()
        _tunnel = None


atexit.register(close_tunnel)  # 프로세스 종료 시 자동으로 터널 정리
