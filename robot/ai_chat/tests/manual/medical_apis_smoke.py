"""공공 의료 API 키와 현재 지원 메서드의 실제 응답을 확인한다."""


def main() -> None:
    from bomi_ai_chat.apis.medical_apis import MedicalDataClient
    from bomi_ai_chat.config import Settings

    settings = Settings.from_env()
    missing = [
        name
        for name, value in (
            ("HIRA_HOSPITAL_API_KEY", settings.hira_hospital_api_key),
            ("HIRA_PHARMACY_API_KEY", settings.hira_pharmacy_api_key),
            ("DUR_PRDLST_API_KEY", settings.dur_prdlst_api_key),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"필수 환경변수가 없습니다: {', '.join(missing)}")

    client = MedicalDataClient(settings)
    print("=== 병원정보서비스 테스트 ===")
    print(client.get_hospital_info(yadm_nm="서울대학교병원"))
    print("\n=== 약국정보서비스 테스트 ===")
    print(client.get_pharmacy_info(sido_cd="110000"))
    print("\n=== 의약품 제품허가정보 테스트 ===")
    print(client.get_drug_permission_list(item_name="타이레놀"))


if __name__ == "__main__":
    main()
