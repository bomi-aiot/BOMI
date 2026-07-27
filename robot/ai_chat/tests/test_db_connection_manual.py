# robot/ai_chat/tests/test_db_connection_manual.py
"""DB 연결 자체가 되는지만 확인하는 테스트 (테이블 존재 여부와 무관)."""
import sys, os
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.append(os.path.abspath(SRC_DIR))

from db.medical_repository import _get_conn

try:
    conn = _get_conn()
    print("DB 연결 성공!")
    conn.close()
except Exception as e:
    print(f"DB 연결 실패: {e}")