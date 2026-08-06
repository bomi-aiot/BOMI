"""의료 도구 검증과 오안내 차단 정책 회귀 테스트."""

from bomi_ai_chat.db.medical_repository import MedicalRepositoryError
from bomi_ai_chat.llm import medical_flow


def function_call(name, args):
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": name,
                                "args": args,
                            }
                        }
                    ]
                }
            }
        ]
    }


def test_locationless_facility_request_never_queries_database(monkeypatch):
    monkeypatch.setattr(
        medical_flow,
        "_call_gemini",
        lambda contents: function_call(
            "find_medical_facility",
            {"facility_type": "병원"},
        ),
    )

    def unexpected_query(**kwargs):
        raise AssertionError("위치 없는 시설 요청에서 DB를 호출했습니다.")

    monkeypatch.setattr(medical_flow, "find_hospitals", unexpected_query)

    assert (
        medical_flow.handle_medical_query("근처 병원 알려줘")
        == medical_flow.LOCATION_REQUIRED_MESSAGE
    )


def test_relative_location_and_generic_name_are_not_treated_as_location(
    monkeypatch,
):
    def unexpected_query(**kwargs):
        raise AssertionError("상대 위치 표현으로 DB를 호출했습니다.")

    monkeypatch.setattr(medical_flow, "find_hospitals", unexpected_query)

    result = medical_flow.execute_tool(
        "find_medical_facility",
        {
            "facility_type": "병원",
            "region": "내 근처",
            "facility_name": "가까운 병원",
        },
    )

    assert result["status"] == "needs_location"


def test_generic_drug_name_never_queries_database(monkeypatch):
    def unexpected_query(item_name):
        raise AssertionError("일반 명사로 의약품 DB를 호출했습니다.")

    monkeypatch.setattr(medical_flow, "find_drug_info", unexpected_query)

    result = medical_flow.execute_tool(
        "check_pill_info",
        {"item_name": "이 약"},
    )

    assert result["status"] == "needs_drug_name"
    assert (
        medical_flow._tool_result_message("check_pill_info", result)
        == medical_flow.DRUG_NAME_REQUIRED_MESSAGE
    )


def test_invalid_function_arguments_are_rejected_before_database(monkeypatch):
    called = False

    def track_query(**kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(medical_flow, "find_hospitals", track_query)

    result = medical_flow.execute_tool(
        "find_medical_facility",
        {
            "facility_type": "의원",
            "region": ["서울"],
            "unexpected": "value",
        },
    )

    assert result["status"] == "invalid"
    assert called is False


def test_unknown_tool_and_non_object_args_are_rejected():
    assert medical_flow.execute_tool("unknown", {})["status"] == "invalid"
    assert medical_flow.execute_tool("check_pill_info", [])["status"] == "invalid"


def test_regional_results_speak_only_deterministic_names(monkeypatch):
    calls = 0

    def call_gemini(contents):
        nonlocal calls
        calls += 1
        return function_call(
            "find_medical_facility",
            {"facility_type": "약국", "region": "서울"},
        )

    monkeypatch.setattr(medical_flow, "_call_gemini", call_gemini)
    monkeypatch.setattr(
        medical_flow,
        "find_pharmacies",
        lambda **kwargs: [
            {
                "yadm_nm": "가약국",
                "addr": "비공개 주소 1",
                "telno": "02-111-1111",
            },
            {
                "yadm_nm": "나약국",
                "addr": "비공개 주소 2",
                "telno": "02-222-2222",
            },
        ],
    )

    response = medical_flow.handle_medical_query("서울 약국 알려줘")

    assert "가약국, 나약국" in response
    assert "비공개 주소" not in response
    assert "02-" not in response
    assert calls == 1


def test_exact_facility_uses_only_exact_row_details(monkeypatch):
    monkeypatch.setattr(
        medical_flow,
        "_call_gemini",
        lambda contents: function_call(
            "find_medical_facility",
            {"facility_type": "병원", "facility_name": "서울대학교병원"},
        ),
    )
    monkeypatch.setattr(
        medical_flow,
        "find_hospitals",
        lambda **kwargs: [
            {
                "yadm_nm": "서울대효병원",
                "addr": "잘못된 주소",
                "cl_cd_nm": "병원",
            },
            {
                "yadm_nm": "서울대학교병원",
                "addr": "정확한 주소",
                "cl_cd_nm": "상급종합병원",
            },
        ],
    )

    response = medical_flow.handle_medical_query("서울대학교병원 어디야")

    assert "서울대학교병원" in response
    assert "정확한 주소" in response
    assert "상급종합병원" in response
    assert "서울대효병원" not in response
    assert "잘못된 주소" not in response


def test_partial_facility_requires_confirmation_without_details(monkeypatch):
    monkeypatch.setattr(
        medical_flow,
        "_call_gemini",
        lambda contents: function_call(
            "find_medical_facility",
            {"facility_type": "병원", "facility_name": "서울대병원"},
        ),
    )
    monkeypatch.setattr(
        medical_flow,
        "find_hospitals",
        lambda **kwargs: [
            {
                "yadm_nm": "서울대효병원",
                "addr": "노출하면 안 되는 주소",
                "cl_cd_nm": "병원",
            }
        ],
    )

    response = medical_flow.handle_medical_query("서울대병원 어디야")

    assert "서울대효병원을 찾으신 건가요?" in response
    assert "노출하면 안 되는 주소" not in response
    assert "정식 명칭" in response


def test_duplicate_exact_facilities_require_region_without_details(
    monkeypatch,
):
    monkeypatch.setattr(
        medical_flow,
        "_call_gemini",
        lambda contents: function_call(
            "find_medical_facility",
            {"facility_type": "약국", "facility_name": "행복약국"},
        ),
    )
    monkeypatch.setattr(
        medical_flow,
        "find_pharmacies",
        lambda **kwargs: [
            {
                "yadm_nm": "행복약국",
                "addr": "서울 비공개 주소",
                "telno": "02-111-1111",
            },
            {
                "yadm_nm": "행복약국",
                "addr": "부산 비공개 주소",
                "telno": "051-222-2222",
            },
        ],
    )

    response = medical_flow.handle_medical_query("행복약국 어디야")

    assert response == medical_flow.FACILITY_SELECTION_REQUIRED_MESSAGE
    assert "비공개 주소" not in response
    assert "02-" not in response


def test_corrected_drug_requires_confirmation_without_details(monkeypatch):
    monkeypatch.setattr(
        medical_flow,
        "_call_gemini",
        lambda contents: function_call(
            "check_pill_info",
            {"item_name": "타이네롤"},
        ),
    )
    monkeypatch.setattr(
        medical_flow,
        "find_drug_info",
        lambda item_name: {
            "match_type": "corrected",
            "results": [
                {
                    "item_name": "타이레놀",
                    "entp_name": "노출하면 안 되는 제조사",
                    "item_ingr_name": "노출하면 안 되는 성분",
                    "prduct_type": "노출하면 안 되는 구분",
                }
            ],
        },
    )

    response = medical_flow.handle_medical_query("타이네롤 먹어도 돼?")

    assert "타이레놀을 찾으신 건가요?" in response
    assert "노출하면 안 되는" not in response


def test_exact_drug_never_claims_dosage_or_safety(monkeypatch):
    monkeypatch.setattr(
        medical_flow,
        "_call_gemini",
        lambda contents: function_call(
            "check_pill_info",
            {"item_name": "타이레놀"},
        ),
    )
    monkeypatch.setattr(
        medical_flow,
        "find_drug_info",
        lambda item_name: {
            "match_type": "exact",
            "results": [
                {
                    "item_name": "타이레놀",
                    "entp_name": "제조사",
                    "item_ingr_name": "등록 성분",
                    "prduct_type": "일반의약품",
                }
            ],
        },
    )

    response = medical_flow.handle_medical_query("타이레놀 먹어도 돼?")

    assert "제조사" in response
    assert "일반의약품" in response
    assert "복용 가능 여부나 용법을 판단할 수 없" in response
    assert "먹어도 됩니다" not in response


def test_duplicate_exact_drugs_require_manufacturer_confirmation(
    monkeypatch,
):
    monkeypatch.setattr(
        medical_flow,
        "_call_gemini",
        lambda contents: function_call(
            "check_pill_info",
            {"item_name": "동일약"},
        ),
    )
    monkeypatch.setattr(
        medical_flow,
        "find_drug_info",
        lambda item_name: {
            "match_type": "exact",
            "results": [
                {
                    "item_name": "동일약",
                    "entp_name": "가제약",
                    "item_permit_date": "20200101",
                    "item_ingr_name": "성분 가",
                    "prduct_type": "일반",
                },
                {
                    "item_name": "동일약",
                    "entp_name": "나제약",
                    "item_permit_date": "20210101",
                    "item_ingr_name": "성분 나",
                    "prduct_type": "전문",
                },
            ],
        },
    )

    response = medical_flow.handle_medical_query("동일약 알려줘")

    assert response == medical_flow.DRUG_SELECTION_REQUIRED_MESSAGE
    assert "성분 가" not in response
    assert "전문" not in response


def test_unknown_drug_returns_fixed_not_found_message(monkeypatch):
    monkeypatch.setattr(
        medical_flow,
        "_call_gemini",
        lambda contents: function_call(
            "check_pill_info",
            {"item_name": "존재하지않는약"},
        ),
    )
    monkeypatch.setattr(
        medical_flow,
        "find_drug_info",
        lambda item_name: {
            "match_type": None,
            "results": [],
        },
    )

    assert (
        medical_flow.handle_medical_query("존재하지않는약 알려줘")
        == medical_flow.DRUG_NOT_FOUND_MESSAGE
    )


def test_not_found_and_database_failure_have_different_messages(monkeypatch):
    monkeypatch.setattr(
        medical_flow,
        "_call_gemini",
        lambda contents: function_call(
            "find_medical_facility",
            {"facility_type": "병원", "region": "서울"},
        ),
    )
    monkeypatch.setattr(
        medical_flow,
        "find_hospitals",
        lambda **kwargs: [],
    )
    assert (
        medical_flow.handle_medical_query("서울 병원 알려줘")
        == medical_flow.FACILITY_NOT_FOUND_MESSAGE
    )

    def database_failure(**kwargs):
        raise MedicalRepositoryError("DB failure")

    monkeypatch.setattr(medical_flow, "find_hospitals", database_failure)
    assert (
        medical_flow.handle_medical_query("서울 병원 알려줘")
        == medical_flow.DATABASE_ERROR_MESSAGE
    )


def test_direct_model_text_is_never_spoken_as_medical_fact(monkeypatch):
    monkeypatch.setattr(
        medical_flow,
        "_call_gemini",
        lambda contents: {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    "서울대학교병원 주소는 모델이 기억한 주소입니다."
                                )
                            }
                        ]
                    }
                }
            ]
        },
    )

    response = medical_flow.handle_medical_query("서울대학교병원 주소 알려줘")

    assert response == medical_flow.FALLBACK_MESSAGE
    assert "모델이 기억한 주소" not in response


def test_malformed_function_call_returns_fixed_message(monkeypatch):
    monkeypatch.setattr(
        medical_flow,
        "_call_gemini",
        lambda contents: {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "check_pill_info",
                                    "args": ["타이레놀"],
                                }
                            }
                        ]
                    }
                }
            ]
        },
    )

    assert (
        medical_flow.handle_medical_query("타이레놀 알려줘")
        == medical_flow.INVALID_TOOL_MESSAGE
    )


def test_tool_schema_mentions_only_available_drug_fields():
    declarations = medical_flow.TOOLS[0]["function_declarations"]
    pill_tool = next(
        declaration
        for declaration in declarations
        if declaration["name"] == "check_pill_info"
    )

    assert "제품명" in pill_tool["description"]
    assert "업체명" in pill_tool["description"]
    assert "원료성분명" in pill_tool["description"]
    assert "복용법" in pill_tool["description"]
    assert "판단할 수 없다" in pill_tool["description"]
