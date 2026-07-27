# robot/ai_chat/batch/batch_medication_ingest.py
"""의약품 제품허가정보 전체를 배치로 가져와 파싱하는 일회성/주기적 스크립트."""
import sys
import os
import time

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.append(os.path.abspath(SRC_DIR))

from apis.medical_apis import MedicalDataClient
from apis.drug_parser import parse_drug_item


def fetch_all_drug_data(client, num_of_rows=500):
    all_items = []
    page = 1
    while True:
        result = client.get_drug_permission_list(page_no=page, num_of_rows=num_of_rows)
        if not result:
            break
        parsed = [parse_drug_item(item) for item in result]
        all_items.extend(parsed)
        print(f"페이지 {page} 완료 — 누적 {len(all_items)}건")
        page += 1
        time.sleep(0.2)
    return all_items


if __name__ == "__main__":
    client = MedicalDataClient()
    data = fetch_all_drug_data(client)
    print(f"총 {len(data)}건 수집 완료")
    # TODO: 백엔드 저장 API로 전송 또는 DB 직접 저장