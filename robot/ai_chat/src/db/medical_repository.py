# robot/ai_chat/src/db/medical_repository.py
"""
DB 조회 전담 모듈.
로컬 테스트: springboot_local DB의 hospitals/pharmacies/drugs 테이블 사용.
EC2 이전 시 DATABASE_URL만 바꾸면 됨 (쿼리/컬럼명은 백엔드와 스키마 확정 필요).
"""
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def _get_conn():
    return psycopg2.connect(DATABASE_URL, client_encoding="utf-8")


def find_hospitals(name=None, region=None, department=None, limit=5):
    query = "SELECT DISTINCT yadm_nm, addr, department FROM hospitals WHERE 1=1"
    params = []
    if name:
        query += " AND yadm_nm ILIKE %s"
        params.append(f"%{name}%")
    if region:
        query += " AND addr ILIKE %s"
        params.append(f"%{region}%")
    if department:
        query += " AND department = %s"
        params.append(department)
    query += " LIMIT %s"
    params.append(limit)

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def find_pharmacies(name=None, region=None, limit=5):
    query = "SELECT yadm_nm, addr, telno FROM pharmacies WHERE 1=1"
    params = []
    if name:
        query += " AND yadm_nm ILIKE %s"
        params.append(f"%{name}%")
    if region:
        query += " AND addr ILIKE %s"
        params.append(f"%{region}%")
    query += " LIMIT %s"
    params.append(limit)

    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def find_drug_info(item_name, limit=3):
    query = """
        SELECT item_name, pill_form, dosage_text, storage_method, etc_otc, entp_name
        FROM drugs
        WHERE item_name ILIKE %s
        LIMIT %s
    """
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (f"%{item_name}%", limit))
            return cur.fetchall()