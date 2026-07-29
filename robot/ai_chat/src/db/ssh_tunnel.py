# robot/ai_chat/src/db/ssh_tunnel.py
"""EC2에 도커로 떠 있는 Postgres 접근용 SSH 터널.
프로세스 실행 중 한 번만 터널을 열고, 이후 요청은 로컬 포트로 재사용한다."""
import os
import atexit
from sshtunnel import SSHTunnelForwarder
from dotenv import load_dotenv

load_dotenv()

EC2_HOST = os.getenv("EC2_HOST")
SSH_USER = os.getenv("EC2_SSH_USER", "ec2-user")
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH")
REMOTE_DB_HOST = os.getenv("REMOTE_DB_HOST", "localhost")
REMOTE_DB_PORT = int(os.getenv("REMOTE_DB_PORT", 5432))

_tunnel = None


def get_local_port() -> int:
    """터널이 아직 안 열려있으면 열고, 로컬에서 접속할 포트 번호를 반환한다."""
    global _tunnel
    if _tunnel is None:
        _tunnel = SSHTunnelForwarder(
            (EC2_HOST, 22),
            ssh_username=SSH_USER,
            ssh_pkey=SSH_KEY_PATH,
            remote_bind_address=(REMOTE_DB_HOST, REMOTE_DB_PORT),
        )
        _tunnel.start()
        print(f"SSH 터널 연결됨 — 로컬 포트 {_tunnel.local_bind_port} → EC2 {REMOTE_DB_HOST}:{REMOTE_DB_PORT}")
    return _tunnel.local_bind_port


def close_tunnel():
    global _tunnel
    if _tunnel is not None:
        _tunnel.stop()
        _tunnel = None


atexit.register(close_tunnel)  # 프로세스 종료 시 자동으로 터널 정리