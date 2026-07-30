# robot/ai_chat/tests/test_medical_apis_manual.py
"""
API 키 발급 후 응답이 제대로 오는지 확인하는 수동 테스트 스크립트.
python tests/test_medical_apis_manual.py 로 직접 실행.
"""
import sys
import os

# tests/ -> ai_chat/ -> ai_chat/src 로 경로 계산
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.append(os.path.abspath(SRC_DIR))

from bomi_ai_chat.apis.medical_apis import MedicalDataClient


def main():
    client = MedicalDataClient()

    print("=== 병원정보서비스 테스트 ===")
    hospitals = client.get_hospital_info(yadm_nm="서울대학교병원")
    print(hospitals)

    print("\n=== 약국정보서비스 테스트 ===")
    pharmacies = client.get_pharmacy_info(sido_cd="110000")
    print(pharmacies)

    print("=== DUR 노인주의 테스트 ===")
    elderly_info = client.get_dur_elderly_caution()
    print(elderly_info)

    print("\n=== DUR 병용금기 테스트 ===")
    taboo_info = client.get_dur_combination_taboo()
    print(taboo_info)


if __name__ == "__main__":
    main()
