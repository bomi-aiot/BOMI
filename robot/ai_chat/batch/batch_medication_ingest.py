# robot/ai_chat/batch/batch_medication_ingest.py
"""의약품 제품허가정보 전체를 배치로 가져와 파싱한 뒤 DB에 저장하는 스크립트."""
import sys, os, time, argparse
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.append(os.path.abspath(SRC_DIR))

from apis.medical_apis import MedicalDataClient
from apis.drug_parser import parse_drug_item
from db.medical_repository import _get_conn


def is_medication_ingested() -> bool:
    """의약품 데이터가 이미 채워져 있는지 확인 (지역 무관, 전체 1회성)."""
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM drugs LIMIT 1")
            return cur.fetchone() is not None


def ingest_medications(client, num_of_rows=500, force=False):
    if not force and is_medication_ingested():
        print("의약품 데이터가 이미 있어 스킵합니다.")
        return

    page = 1
    with _get_conn() as conn:
        with conn.cursor() as cur:
            while True:
                result = client.get_drug_permission_list(page_no=page, num_of_rows=num_of_rows)
                if not result:
                    break
                parsed = [parse_drug_item(item) for item in result]
                for d in parsed:
                    cur.execute(
                        """INSERT INTO drugs
                           (item_seq, item_name, pill_form, dosage_text,
                            storage_method, etc_otc, entp_name)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (item_seq) DO NOTHING""",
                        (d["item_seq"], d["item_name"], d["pill_form"],
                         d["dosage_text"], d["storage_method"],
                         d["etc_otc"], d["entp_name"]),
                    )
                conn.commit()
                print(f"의약품 페이지 {page} 완료 — 누적 {(page) * num_of_rows}건 처리")
                page += 1
                time.sleep(0.2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    ingest_medications(MedicalDataClient(), force=args.force)