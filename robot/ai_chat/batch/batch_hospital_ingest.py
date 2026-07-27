# robot/ai_chat/batch/batch_hospital_ingest.py
import sys, os, time
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.append(os.path.abspath(SRC_DIR))

from apis.medical_apis import MedicalDataClient
from apis.dept_codes import DEPT_CODES, DEPT_GROUP_MAP
from db.medical_repository import _get_conn


def is_region_ingested(sido_cd: str) -> bool:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM hospitals WHERE sido_cd = %s LIMIT 1", (sido_cd,))
            return cur.fetchone() is not None


def ingest_hospitals_by_dept(client, sido_cd, num_of_rows=500, force=False):
    if not force and is_region_ingested(sido_cd):
        print(f"{sido_cd} 지역은 이미 데이터가 있어 스킵합니다.")
        return

    with _get_conn() as conn:
        with conn.cursor() as cur:
            for dept_code in DEPT_CODES:
                group_name = DEPT_GROUP_MAP[dept_code]
                page = 1
                while True:
                    result = client.get_hospital_info(
                        sido_cd=sido_cd, dgsbjt_cd=dept_code,
                        page_no=page, num_of_rows=num_of_rows,
                    )
                    if not result:
                        break
                    for h in result:
                        cur.execute(
                            """INSERT INTO hospitals
                               (yadm_nm, addr, sido_cd, sgg_cd, department)
                               VALUES (%s, %s, %s, %s, %s)
                               ON CONFLICT DO NOTHING""",
                            (h.get("yadmNm"), h.get("addr"),
                             h.get("sidoCd"), h.get("sgguCd"), group_name),
                        )
                    conn.commit()
                    print(f"[{group_name}] 페이지 {page} 완료 — {len(result)}건")
                    page += 1
                    time.sleep(0.2)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sido-cd", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    ingest_hospitals_by_dept(MedicalDataClient(), sido_cd=args.sido_cd, force=args.force)