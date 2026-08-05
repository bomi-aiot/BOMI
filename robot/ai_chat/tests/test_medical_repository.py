"""의료 DB 쿼리의 결정성, 입력 제한, 장애 변환 테스트."""

import pytest

from bomi_ai_chat.db import medical_repository


class RecordingCursor:
    def __init__(self, rows):
        self.rows = rows
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchall(self):
        return self.rows


class RecordingConnection:
    def __init__(self, rows):
        self.cursor_instance = RecordingCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self, **kwargs):
        return self.cursor_instance


def test_hospital_query_escapes_wildcards_and_has_stable_order(
    monkeypatch,
):
    connection = RecordingConnection(
        [{"yadm_nm": "안전병원", "addr": "부산 서면", "cl_cd_nm": "병원"}]
    )
    monkeypatch.setattr(
        medical_repository,
        "_get_conn",
        lambda: connection,
    )

    rows = medical_repository.find_hospitals(
        name="50%_병원",
        region="부산 서면",
        limit=999,
    )

    assert rows[0]["yadm_nm"] == "안전병원"
    assert "ORDER BY LOWER(yadm_nm) ASC" in connection.cursor_instance.query
    assert "ESCAPE E'\\\\'" in connection.cursor_instance.query
    assert connection.cursor_instance.params == [
        "%50\\%\\_병원%",
        "%부산%",
        "%서면%",
        20,
    ]


def test_hospital_name_search_ignores_whitespace(monkeypatch):
    """STT가 공백을 다르게 넣어도 방금 알려준 곳을 계속 찾는다.

    "남경 의원"으로 저장된 곳을 로봇이 말해줬는데, 되물을 때 "남경의원"으로
    (공백 없이) 넘어오면 예전에는 ILIKE 부분 문자열 매칭이 깨져 로봇 스스로
    방금 알려준 곳을 "못 찾겠다"고 답했다. 공백을 지우고 비교해야 한다.
    """
    connection = RecordingConnection(
        [{"yadm_nm": "남경 의원", "addr": "부산", "cl_cd_nm": "의원"}]
    )
    monkeypatch.setattr(medical_repository, "_get_conn", lambda: connection)

    rows = medical_repository.find_hospitals(name="남경의원")

    assert rows[0]["yadm_nm"] == "남경 의원"
    assert "regexp_replace(yadm_nm" in connection.cursor_instance.query
    assert connection.cursor_instance.params[0] == "%남경의원%"


def test_pharmacy_name_search_ignores_whitespace(monkeypatch):
    """find_hospitals 와 같은 이유로 약국 이름도 공백을 지우고 비교한다."""
    connection = RecordingConnection(
        [{"yadm_nm": "행복 약국", "addr": "서울", "telno": "02-000-0000"}]
    )
    monkeypatch.setattr(medical_repository, "_get_conn", lambda: connection)

    rows = medical_repository.find_pharmacies(name="행복약국")

    assert rows[0]["yadm_nm"] == "행복 약국"
    assert "regexp_replace(yadm_nm" in connection.cursor_instance.query
    assert connection.cursor_instance.params[0] == "%행복약국%"


def test_pharmacy_query_uses_deterministic_tie_breakers(monkeypatch):
    connection = RecordingConnection([])
    monkeypatch.setattr(
        medical_repository,
        "_get_conn",
        lambda: connection,
    )

    medical_repository.find_pharmacies(region="서울")

    query = connection.cursor_instance.query
    assert "ORDER BY LOWER(yadm_nm) ASC" in query
    assert "LOWER(addr) ASC" in query
    assert "LOWER(COALESCE(telno, '')) ASC" in query


def test_closest_value_breaks_equal_scores_by_normalized_name(monkeypatch):
    monkeypatch.setattr(
        medical_repository,
        "_fetch_all",
        lambda query, params: [
            {"item_name": "나 약", "score": 0.9},
            {"item_name": "가 약", "score": 0.9},
        ],
    )
    monkeypatch.setattr(
        medical_repository,
        "_jamo_similarity",
        lambda left, right: 0.8,
    )

    assert (
        medical_repository.find_closest_value(
            "drug_permit",
            "item_name",
            "약",
        )
        == "가 약"
    )


def test_closest_value_rejects_unapproved_table():
    with pytest.raises(ValueError, match="허용되지 않은"):
        medical_repository.find_closest_value(
            "hospital",
            "yadm_nm",
            "서울병원",
        )


def test_drug_exact_query_has_stable_order(monkeypatch):
    calls = []

    def fetch_all(query, params):
        calls.append((query, params))
        return [
            {
                "item_name": "타이레놀",
                "entp_name": "제조사",
                "item_permit_date": "20200101",
                "item_ingr_name": "성분",
                "prduct_type": "일반",
            }
        ]

    monkeypatch.setattr(medical_repository, "_fetch_all", fetch_all)

    result = medical_repository.find_drug_info("타이 레놀")

    assert result["match_type"] == "exact"
    assert "item_permit_date DESC NULLS LAST" in calls[0][0]
    assert calls[0][1] == ("타이레놀", 3)


def test_connection_failure_is_not_an_empty_result(monkeypatch):
    def fail_connection():
        raise OSError("database unavailable")

    monkeypatch.setattr(medical_repository, "_get_conn", fail_connection)

    with pytest.raises(medical_repository.MedicalRepositoryError):
        medical_repository.find_hospitals(region="서울")
