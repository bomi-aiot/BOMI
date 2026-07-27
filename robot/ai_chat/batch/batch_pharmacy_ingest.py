# robot/ai_chat/batch/batch_pharmacy_ingest.py
import sys, os, time, argparse
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.append(os.path.abspath(SRC_DIR))

from apis.medical_apis import MedicalDataClient
from db.medical_repository import _get_conn


def is_region_ingested_pharmacy(sido_cd: str) -> bool:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pharmacies WHERE sido_cd = %s LIMIT 1", (sido_cd,))
            return cur.fetchone() is not None


def ingest_pharmacies(client, sido_cd, num_of_rows=500, force=False):
    if not force and is_region_ingested_pharmacy(sido_cd):
        print(f"{sido_cd} 지역 약국 데이터는 이미 있어 스킵합니다.")
        return

    page = 1
    with _get_conn() as conn:
        with conn.cursor() as cur:
            while True:
                result = client.get_pharmacy_info(
                    sido_cd=sido_cd, page_no=page, num_of_rows=num_of_rows,
                )
                if not result:
                    break
                for p in result:
                    cur.execute(
                        """INSERT INTO pharmacies
                           (yadm_nm, addr, sido_cd, sgg_cd, telno)
                           VALUES (%s, %s, %s, %s, %s)
                           ON CONFLICT DO NOTHING""",
                        (p.get("yadmNm"), p.get("addr"),
                         p.get("sidoCd"), p.get("sgguCd"), p.get("telno")),
                    )
                conn.commit()
                print(f"약국 페이지 {page} 완료 — {len(result)}건")
                page += 1
                time.sleep(0.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sido-cd", required=True, help="사용자 거주지 시도코드")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    ingest_pharmacies(MedicalDataClient(), sido_cd=args.sido_cd, force=args.force)