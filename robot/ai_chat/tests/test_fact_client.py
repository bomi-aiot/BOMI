"""사실 후보 제출 클라이언트(backend_client/fact_client.py) 검증 (S15P11E102-255).

이 파일이 검증하는 것
    1. 성공하면 예외 없이 끝나고, 페이로드가 서버 계약(FactCandidateIntakeRequest)
       대로 실린다 — 사실 하나당 요청 하나.
    2. 실패하면(네트워크, HTTP 오류 둘 다) FactSubmissionError 를 올린다 —
       conversation_client 와 반대 방향(예외를 삼키지 않는다).
    3. 빈 facts 는 아예 호출하지 않는다.
    4. 401 은 다른 실패와 구분되는 AUTH FAILURE 경고를 남긴다.
    5. 건강 관련 발화는 CARE_RECORD 로 간다 — MEMORY 로 새면 서버가 확인 없이
       저장해버린다(S15P11E102-255 계약 정합).
    6. 약속(APPOINTMENT)은 startsAt 을 믿을 수 있을 때만 care_record 로 간다 (G4).
       못 믿을 startsAt 은 사실을 버리지 않고 MEMORY/OTHER 로 강등한다.

왜 6번이 필요한가
    서버의 FactRiskPolicy 는 일정류만 **사람 확인 없이 자동 반영**한다. 그리고
    FactMaterializer 는 startsAt 을 못 읽으면 occurred_at 을 조용히 '지금'으로
    채운다. 그래서 오프셋 빠진 시각 하나가, 어르신이 언제인지 말한 적도 없는
    일정을 보호자 화면에 '지금 일정'으로 띄운다. 그 문을 지키는 것이 여기다.

참고
    CLAUDE.md §8, §12 / backend_client/fact_client.py, fact_contract.py 모듈 docstring
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from bomi_ai_chat.backend_client.fact_client import (
    BackendFactClient,
    FactSubmissionError,
)
from tests.http_fakes import StubResponse, StubSession

SENIOR = "senior-1"


def test_successful_submission_sends_the_expected_payload(settings_factory):
    settings = settings_factory(BACKEND_BASE_URL="https://backend.example")
    session = StubSession(StubResponse(200, json_data={}))
    client = BackendFactClient(settings=settings, session=session)

    client.submit_fact_candidates(
        SENIOR,
        conversation_id="conv-1",
        source_message_id="msg-1",
        facts=[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}],
    )

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://backend.example/api/v1/robot/fact-candidates"
    # 서버의 FactCandidateIntakeRequest 는 필수 필드가 여덟 개다. 하나라도 빠지면
    # bean validation 이 400 으로 거절하고, 그 400 은 재시도해도 낫지 않는다.
    assert call["json"] == {
        "seniorId": SENIOR,
        "conversationId": "conv-1",
        "sourceMessageId": "msg-1",
        "targetDomain": "MEMORY",
        "factType": "PERSONAL_RELATIONSHIP",
        "operation": "CREATE",
        "proposedValue": {"content": "손자가 자주 놀러 온다."},
        "riskLevel": "NORMAL",
    }


def test_each_fact_becomes_its_own_request(settings_factory):
    """서버는 요청 하나당 후보 하나를 만든다 — 묶음으로 보내면 나머지를 잃는다."""
    settings = settings_factory(BACKEND_BASE_URL="https://backend.example")
    session = StubSession(StubResponse(200, json_data={}), StubResponse(200, json_data={}))
    client = BackendFactClient(settings=settings, session=session)

    client.submit_fact_candidates(
        SENIOR,
        conversation_id="conv-1",
        source_message_id="msg-1",
        facts=[
            {"factType": "FAMILY", "content": "손자가 자주 놀러 온다."},
            {"factType": "HOBBY", "content": "화분 가꾸기를 좋아한다."},
        ],
    )

    assert len(session.calls) == 2
    assert session.calls[0]["json"]["factType"] == "PERSONAL_RELATIONSHIP"
    assert session.calls[1]["json"]["factType"] == "HOBBY"


def test_health_facts_go_to_care_record_not_memory(settings_factory):
    """건강 발화가 MEMORY 로 새면 서버가 안전한 사실로 보고 확인 없이 저장한다."""
    settings = settings_factory(BACKEND_BASE_URL="https://backend.example")
    session = StubSession(StubResponse(200, json_data={}))
    client = BackendFactClient(settings=settings, session=session)

    client.submit_fact_candidates(
        SENIOR,
        conversation_id="conv-1",
        source_message_id="msg-1",
        facts=[{"factType": "HEALTH", "content": "이제 아침 약을 안 먹는다."}],
    )

    payload = session.calls[0]["json"]
    assert payload["targetDomain"] == "CARE_RECORD"
    assert payload["factType"] == "HEALTH_CONDITION"
    assert payload["riskLevel"] == "SENSITIVE"


def test_unknown_fact_type_falls_back_to_an_other_memory(settings_factory):
    """모델이 목록 밖 값을 뱉어도 내용을 잃지 않는다 — 분류만 OTHER 로 떨어진다."""
    settings = settings_factory(BACKEND_BASE_URL="https://backend.example")
    session = StubSession(StubResponse(200, json_data={}))
    client = BackendFactClient(settings=settings, session=session)

    client.submit_fact_candidates(
        SENIOR,
        conversation_id="conv-1",
        source_message_id="msg-1",
        facts=[{"factType": "WEATHER_CHAT", "content": "비 오는 날을 싫어한다."}],
    )

    payload = session.calls[0]["json"]
    assert payload["targetDomain"] == "MEMORY"
    assert payload["factType"] == "OTHER"
    assert payload["proposedValue"] == {"content": "비 오는 날을 싫어한다."}


# ── 6. 약속(APPOINTMENT) ─────────────────────────────────────────────────────


def _submit_one(settings_factory, fact: dict, *, now_local=None, utterance=None) -> dict:
    """사실 하나를 제출하고 서버로 나간 JSON 본문을 돌려준다.

    now_local
        발화가 말해진 시각(tz-aware). 과거·먼 미래 판정에만 쓰인다. 기본 None 은
        "기준 시각을 모른다"이고, 그때는 그 두 검사를 건너뛴다 — 모르는 채로
        "이건 과거다"라고 단정하면 정상적인 약속을 조용히 버리게 된다.

    utterance
        어르신 발화 원문. 요일 검산에만 쓰인다. 기본 None 은 "원문을 모른다"이고,
        그때는 모델이 준 날짜를 그대로 둔다.
    """
    settings = settings_factory(BACKEND_BASE_URL="https://backend.example")
    session = StubSession(StubResponse(200, json_data={}))
    client = BackendFactClient(settings=settings, session=session)

    client.submit_fact_candidates(
        SENIOR, conversation_id="conv-1", source_message_id="msg-1", facts=[fact],
        now_local=now_local, utterance=utterance)

    return session.calls[0]["json"]


def test_an_appointment_with_a_trustworthy_time_becomes_a_care_record(settings_factory):
    """"다음 주 화요일 세 시에 병원 가" 가 절대 시각을 단 일정으로 나간다."""
    payload = _submit_one(settings_factory, {
        "factType": "APPOINTMENT",
        "content": "다음 주 화요일 오후 세 시에 병원에 간다.",
        "title": "병원 진료",
        "startsAt": "2026-08-11T15:00:00+09:00",
    })

    assert payload["targetDomain"] == "CARE_RECORD"
    assert payload["factType"] == "APPOINTMENT"
    # riskLevel 을 SENSITIVE 로 올려도 서버는 판정에 쓰지 않는다. 그러면서 감사
    # 기록에는 "확인이 필요한 사실"로 남아 처리와 어긋난다 — 그래서 NORMAL 이다.
    assert payload["riskLevel"] == "NORMAL"
    assert payload["proposedValue"] == {
        # content 에 title 이 덧붙는다 — 아래 test_an_appointment_content_absorbs_the_title
        # 참고. 서버의 회피 필터가 content 하나만 읽기 때문이다.
        "content": "다음 주 화요일 오후 세 시에 병원에 간다. (병원 진료)",
        "title": "병원 진료",
        "startsAt": "2026-08-11T15:00:00+09:00",
    }


def test_an_appointment_always_keeps_content(settings_factory):
    """★ content 를 빼면 서버의 회피 대상 인물 필터가 통째로 꺼진다.

    ConversationFactIntakeService.mentionsAvoidedPerson 은 proposedValue 에서
    "content" 하나만 읽는다. 약속이라고 title/startsAt 만 보내면, 돌아가신 배우자
    이름이 들어간 일정이 아무 검사 없이 보호자 화면에 걸린다.
    """
    payload = _submit_one(settings_factory, {
        "factType": "APPOINTMENT",
        "content": "다음 주에 남편 산소에 간다.",
        "title": "성묘",
        "startsAt": "2026-08-11T10:00:00+09:00",
    })

    assert "다음 주에 남편 산소에 간다." in payload["proposedValue"]["content"]


def test_an_appointment_content_absorbs_the_title(settings_factory):
    """★ title 에만 있는 이름도 회피 필터가 볼 수 있어야 한다.

    위 테스트는 "content 를 빼지 마라"를 잠그지만 반대 방향이 남아 있었다. 서버
    필터는 content 하나만 읽는데, 모델이 회피 대상 이름을 title 에만 넣으면
    (content 에는 "간다"만, title 에 "OOO 기일") 필터가 이름을 보지 못한다.
    APPOINTMENT 는 사람 확인 없이 자동 반영되므로 중간에 아무도 못 본다.

    서버를 고치는 편이 옳지만 그건 백엔드 라인이다. 클라이언트가 필터에 필요한
    글자를 반드시 content 안에 넣어 보낸다.
    """
    payload = _submit_one(settings_factory, {
        "factType": "APPOINTMENT",
        "content": "다음 주 화요일 오후 세 시에 간다.",
        "title": "김철수 기일",
        "startsAt": "2026-08-11T15:00:00+09:00",
    })

    assert "김철수" in payload["proposedValue"]["content"]


def test_an_appointment_does_not_duplicate_a_title_already_in_the_content(settings_factory):
    """제목이 이미 문장 안에 있으면 덧붙이지 않는다 — 같은 말을 두 번 읽히지 않는다."""
    payload = _submit_one(settings_factory, {
        "factType": "APPOINTMENT",
        "content": "다음 주 화요일에 병원 진료가 있다.",
        "title": "병원 진료",
        "startsAt": "2026-08-11T15:00:00+09:00",
    })

    assert payload["proposedValue"]["content"] == "다음 주 화요일에 병원 진료가 있다."


def test_an_appointment_without_a_title_falls_back_to_the_content(settings_factory):
    """제목이 없으면 보호자 화면에 "알 수 없음"이 뜬다 — 비워두느니 문장을 그대로 쓴다."""
    payload = _submit_one(settings_factory, {
        "factType": "APPOINTMENT",
        "content": "내일 오후 두 시에 병원에 간다.",
        "startsAt": "2026-08-08T14:00:00+09:00",
    })

    assert payload["proposedValue"]["title"] == "내일 오후 두 시에 병원에 간다."


def test_a_z_suffixed_starts_at_is_accepted(settings_factory):
    """파이썬 3.10 의 fromisoformat 은 "Z" 를 못 읽는다 — 젯슨 파이썬 버전에 따라
    같은 값이 통과했다 거절됐다 하면 안 된다."""
    payload = _submit_one(settings_factory, {
        "factType": "APPOINTMENT",
        "content": "내일 병원에 간다.",
        "startsAt": "2026-08-11T05:00:00Z",
    })

    assert payload["factType"] == "APPOINTMENT"
    # 원문 그대로 보낸다 — 재포맷하면 파이썬과 자바의 해석이 갈릴 여지가 생긴다.
    assert payload["proposedValue"]["startsAt"] == "2026-08-11T05:00:00Z"


@pytest.mark.parametrize(
    ("case", "starts_at"),
    [
        ("startsAt 자체가 없다", None),
        # ★ 가장 중요한 한 줄. 사람 눈에는 멀쩡하고 파이썬도 읽어내지만, 자바
        #   OffsetDateTime.parse 가 던져서 occurred_at 이 '지금'으로 채워진다.
        ("UTC 오프셋이 없다", "2026-08-11T14:00"),
        ("아예 시각이 아니다", "다음 주 화요일"),
        ("빈 문자열이다", "   "),
        ("숫자로 왔다", 1786082640),
        # ─────────────────────────────────────────────────────────────────
        # ★ 파이썬은 읽고 자바는 못 읽는 네 형태 (리뷰 지적).
        #
        #   datetime.fromisoformat 의 허용 집합이 서버의 ISO_OFFSET_DATE_TIME 보다
        #   넓다. 검증만 통과시키고 서버가 파싱에 실패하면, 서버는 예외 대신
        #   occurred_at 을 '지금'으로 채운다 — 이 함수가 막으려던 바로 그 실패다.
        #   APPOINTMENT 는 자동 반영이라 중간에 사람이 보지 않는다.
        ("T 대신 공백이다 (파이썬 3.7+ 전부 통과)", "2026-08-11 14:00:00+09:00"),
        ("오프셋에 콜론이 없다", "2026-08-11T14:00:00+0900"),
        ("기본형식이다", "20260811T140000+0900"),
        # 파이썬 버전에 따라 통과/거절이 갈리는 최악의 형태 — 젯슨 이미지를 바꾸면
        # 증상이 달라진다. 그래서 파서가 아니라 모양으로 먼저 막는다.
        ("오프셋에 시만 있다 (파이썬 3.11+ 통과)", "2026-08-11T14:00:00+09"),
    ],
)
def test_an_appointment_without_a_trustworthy_time_is_demoted(settings_factory, case, starts_at):
    """시각을 확정하지 못한 약속은 care_record 로 가지 않는다 — 그렇다고 버리지도 않는다."""
    fact = {"factType": "APPOINTMENT", "content": "다음 주에 병원에 가야 한다.", "title": "병원"}
    if starts_at is not None:
        fact["startsAt"] = starts_at

    payload = _submit_one(settings_factory, fact)

    assert payload["targetDomain"] == "MEMORY", case
    assert payload["factType"] == "OTHER", case
    assert payload["riskLevel"] == "NORMAL", case
    # 강등된 약속의 proposedValue 는 다른 기억과 똑같은 모양이어야 한다. title 이나
    # startsAt 이 남으면 서버가 그것을 memory 값으로 들고 가고, 화면에서 시각 없는
    # 일정처럼 보이는 절반짜리 행이 생긴다.
    assert payload["proposedValue"] == {"content": "다음 주에 병원에 가야 한다."}, case


@pytest.mark.parametrize(
    ("case", "starts_at"),
    [
        # "지난 화요일에 병원 갔다 왔어" 를 모델이 APPOINTMENT 로 잘못 분류하는 경우.
        # 지나간 일은 일정이 아니라 기억이다. 과거 일정을 만들면 앞으로의 일정을 보는
        # 조회 경로에는 뜨지 않으므로 어르신은 아무 알림도 못 받고, 경고도 안 남는다.
        ("지나간 시각이다", "2026-08-04T15:00:00+09:00"),
        ("바로 직전이다", "2026-08-07T15:03:00+09:00"),
        # 모델이 연도를 잘못 계산한 경우. 상한이 없으면 그대로 통과한다.
        ("100년 뒤다", "2126-08-11T15:00:00+09:00"),
        ("1년을 넘겼다", "2027-09-01T15:00:00+09:00"),
    ],
)
def test_an_appointment_outside_a_sane_horizon_is_demoted(settings_factory, case, starts_at):
    """★ 읽히는 값 중에도 등록하면 안 되는 것이 있다 (리뷰 지적).

    APPOINTMENT 는 서버가 사람 확인 없이 자동 반영하는 유일한 CARE_RECORD 다.
    모양과 파싱만 보면 과거 일정도, 100년 뒤 일정도 그대로 통과한다.

    기준 시각은 발화가 말해진 시각이다 — 이 테스트는 2026-08-07 15:04(서울)로 고정한다.
    """
    fact = {
        "factType": "APPOINTMENT",
        "content": "병원에 간다.",
        "title": "병원",
        "startsAt": starts_at,
    }

    payload = _submit_one(
        settings_factory, fact,
        now_local=datetime(2026, 8, 7, 15, 4, tzinfo=timezone(timedelta(hours=9))))

    assert payload["targetDomain"] == "MEMORY", case
    assert payload["factType"] == "OTHER", case
    assert payload["proposedValue"] == {"content": "병원에 간다."}, case


def test_an_appointment_inside_the_horizon_survives(settings_factory):
    """기준 시각 이후이고 1년 안이면 그대로 일정으로 나간다 — 위 검사가 과잉이 아니다."""
    payload = _submit_one(settings_factory, {
        "factType": "APPOINTMENT",
        "content": "병원에 간다.",
        "title": "병원",
        "startsAt": "2026-08-11T15:00:00+09:00",
    }, now_local=datetime(2026, 8, 7, 15, 4, tzinfo=timezone(timedelta(hours=9))))

    assert payload["targetDomain"] == "CARE_RECORD"
    assert payload["factType"] == "APPOINTMENT"


SEOUL = timezone(timedelta(hours=9))
# 2026-08-10 은 월요일이다. 아래 요일 검산 테스트가 전부 이 날을 기준으로 읽힌다.
MONDAY_2026_08_10 = datetime(2026, 8, 10, 9, 0, tzinfo=SEOUL)


def test_an_appointment_moves_to_the_weekday_the_senior_named(settings_factory):
    """★ 실측 회귀 (S15P11E102-392).

    2026-08-10(월) 대화에서 어르신은 "다음 주 화요일"이라고 말했는데, 모델이
    계산한 startsAt 은 8/19 **수요일**이었다. 같은 대화의 같은 표현이 8/18(화)로
    나온 행도 있었다 — 즉 모델의 산수가 비결정적이다.

    APPOINTMENT 는 사람 확인 없이 자동 반영되고 care_record 에는 created_at 도
    없어서, 하루 밀린 이 값을 나중에 대조할 방법이 없다. 그래서 여기서 고친다.
    """
    payload = _submit_one(settings_factory, {
        "factType": "APPOINTMENT",
        "content": "다음 주 화요일에 병원에 간다.",
        "title": "병원 진료",
        "startsAt": "2026-08-19T14:00:00+09:00",   # 수요일 — 하루 밀렸다
    }, now_local=MONDAY_2026_08_10, utterance="다음 주 화요일 오후 두 시에 병원 가요")

    assert payload["targetDomain"] == "CARE_RECORD"
    assert payload["factType"] == "APPOINTMENT"
    # 날짜만 옮기고 시각은 건드리지 않는다.
    assert payload["proposedValue"]["startsAt"] == "2026-08-18T14:00:00+09:00"


def test_an_appointment_already_on_the_named_weekday_is_left_alone(settings_factory):
    """맞은 값은 손대지 않는다 — 모델의 원문을 그대로 실어 보낸다.

    이 파일의 다른 검사들과 같은 이유다. 재포맷조차 하지 않아야 파이썬과 자바의
    해석이 갈릴 여지가 없다.
    """
    payload = _submit_one(settings_factory, {
        "factType": "APPOINTMENT",
        "content": "다음 주 화요일에 병원에 간다.",
        "startsAt": "2026-08-18T00:00:00+09:00",   # 화요일 — 맞다
    }, now_local=MONDAY_2026_08_10, utterance="다음 주 화요일에 병원 가요")

    assert payload["proposedValue"]["startsAt"] == "2026-08-18T00:00:00+09:00"


@pytest.mark.parametrize(
    "case,utterance",
    [
        ("요일을 말하지 않았다", "8월 19일 오후 두 시에 병원 가요"),
        ("요일이 둘이라 어느 쪽인지 모른다", "지난 화요일에 갔는데 다음 주 수요일에 또 가요"),
        ("원문을 모른다", None),
    ],
)
def test_the_weekday_check_stays_out_when_it_cannot_judge(settings_factory, case, utterance):
    """검산할 근거가 없으면 개입하지 않는다.

    모르는 채로 날짜를 옮기면, 맞았을 수도 있는 값을 틀리게 만든다. 이 파일의
    다른 검사들이 "의심스러우면 버린다"인 것과 같은 보수성이다.
    """
    payload = _submit_one(settings_factory, {
        "factType": "APPOINTMENT",
        "content": "병원에 간다.",
        "startsAt": "2026-08-19T14:00:00+09:00",
    }, now_local=MONDAY_2026_08_10, utterance=utterance)

    assert payload["proposedValue"]["startsAt"] == "2026-08-19T14:00:00+09:00", case


def test_the_weekday_snap_never_jumps_a_week(settings_factory):
    """주(週)는 모델이 정하고 요일만 코드가 고친다 — 가장 가까운 발생일로만 옮긴다.

    토요일(8/22)에서 "화요일"은 뒤로 4일(8/18)보다 앞으로 3일(8/25)이 가깝다.
    어떤 요일이든 가장 가까운 발생일은 ±3일 안에 있어서, 이 규칙은 구조적으로
    주를 건너뛸 수 없다. 모델이 고른 주를 코드가 덮어쓰면 그건 더 큰 오류다.
    """
    payload = _submit_one(settings_factory, {
        "factType": "APPOINTMENT",
        "content": "화요일에 병원에 간다.",
        "startsAt": "2026-08-22T10:00:00+09:00",   # 토요일
    }, now_local=MONDAY_2026_08_10, utterance="화요일에 병원 가요")

    assert payload["proposedValue"]["startsAt"] == "2026-08-25T10:00:00+09:00"


def test_a_correction_that_lands_in_the_past_is_demoted(settings_factory):
    """당긴 결과가 과거면 버린다 — 과거 판정과 같은 이유다.

    스냅은 최대 3일까지 앞으로 당긴다. 그 결과가 기준 시각보다 앞서면 '지나간
    일'이 되고, 지나간 일은 일정이 아니라 기억이다. 조회 경로에 뜨지 않아
    어르신이 알림도 못 받는 행을 만드는 것보다, 기억으로 남기는 편이 낫다.
    """
    payload = _submit_one(settings_factory, {
        "factType": "APPOINTMENT",
        "content": "월요일에 병원에 간다.",
        "startsAt": "2026-08-11T08:00:00+09:00",   # 화요일 → 월요일로 당기면 8/10 08:00
    }, now_local=MONDAY_2026_08_10, utterance="월요일에 병원 가요")

    assert payload["targetDomain"] == "MEMORY"
    assert payload["factType"] == "OTHER"
    assert payload["proposedValue"] == {"content": "월요일에 병원에 간다."}


def test_the_short_weekday_form_is_understood(settings_factory):
    """'화욜' 같은 줄임말도 요일이다. 실제로 그렇게 말한다."""
    payload = _submit_one(settings_factory, {
        "factType": "APPOINTMENT",
        "content": "병원에 간다.",
        "startsAt": "2026-08-19T14:00:00+09:00",
    }, now_local=MONDAY_2026_08_10, utterance="담주 화욜에 병원 가요")

    assert payload["proposedValue"]["startsAt"] == "2026-08-18T14:00:00+09:00"


def test_a_non_appointment_fact_never_carries_schedule_keys(settings_factory):
    """약속이 아닌 사실에 모델이 startsAt 을 붙여도 서버로 나가지 않는다.

    서버는 proposedValue 를 통째로 care_record.details / memory 값으로 옮긴다.
    기억 하나에 시각이 붙으면 보호자 화면에서 일정처럼 읽히는 행이 생긴다.
    """
    payload = _submit_one(settings_factory, {
        "factType": "FAMILY",
        "content": "손자가 자주 놀러 온다.",
        "title": "손자 방문",
        "startsAt": "2026-08-11T15:00:00+09:00",
    })

    assert payload["proposedValue"] == {"content": "손자가 자주 놀러 온다."}


def test_empty_facts_does_not_call_the_backend(settings_factory):
    settings = settings_factory()
    session = StubSession()
    client = BackendFactClient(settings=settings, session=session)

    client.submit_fact_candidates(
        SENIOR, conversation_id="conv-1", source_message_id="msg-1", facts=[])

    assert session.calls == []


def test_network_failure_raises_fact_submission_error(settings_factory):
    settings = settings_factory(
        HTTP_MAX_ATTEMPTS="1", BACKEND_BASE_URL="https://backend.example")
    session = StubSession(ConnectionError("no route to host"))
    client = BackendFactClient(settings=settings, session=session)

    with pytest.raises(FactSubmissionError):
        client.submit_fact_candidates(
            SENIOR,
            conversation_id="conv-1",
            source_message_id="msg-1",
            facts=[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}],
        )


def test_http_error_raises_fact_submission_error(settings_factory):
    settings = settings_factory(
        HTTP_MAX_ATTEMPTS="1", BACKEND_BASE_URL="https://backend.example")
    session = StubSession(StubResponse(500, json_data={}))
    client = BackendFactClient(settings=settings, session=session)

    with pytest.raises(FactSubmissionError):
        client.submit_fact_candidates(
            SENIOR,
            conversation_id="conv-1",
            source_message_id="msg-1",
            facts=[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}],
        )


def test_auth_failure_logs_a_distinct_warning_then_raises(settings_factory, caplog):
    """(완료 조건과 같은 원칙, S15P11E102-307) 401 은 구분되는 경고를 남긴다."""
    settings = settings_factory(
        HTTP_MAX_ATTEMPTS="1", BACKEND_BASE_URL="https://backend.example")
    session = StubSession(StubResponse(401, json_data={}))
    client = BackendFactClient(settings=settings, session=session)

    raised = False
    with caplog.at_level("WARNING"):
        try:
            client.submit_fact_candidates(
                SENIOR,
                conversation_id="conv-1",
                source_message_id="msg-1",
                facts=[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}],
            )
        except FactSubmissionError:
            raised = True

    assert raised is True
    assert "AUTH FAILURE" in caplog.text


# ── 7. 되돌릴 수 없는 실패의 구분 (S15P11E102-393) ───────────────────────────


def _submission_error(settings_factory, status: int) -> FactSubmissionError:
    """주어진 상태 코드로 실패시키고 올라온 예외를 돌려준다."""
    settings = settings_factory(
        HTTP_MAX_ATTEMPTS="1", BACKEND_BASE_URL="https://backend.example")
    client = BackendFactClient(
        settings=settings, session=StubSession(StubResponse(status, json_data={})))

    with pytest.raises(FactSubmissionError) as caught:
        client.submit_fact_candidates(
            SENIOR,
            conversation_id="conv-1",
            source_message_id="msg-1",
            facts=[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}],
        )
    return caught.value


def test_a_bad_request_is_flagged_as_permanent(settings_factory):
    """★ 400 은 재시도해도 같은 답이 온다 — 호출부가 그 큐 행을 닫아야 한다.

    실측 경로: 리허설 사이에 서버 DB 만 초기화하면 로컬 큐에 남은 행의
    conversationId 가 서버에 없어 영원히 400 을 받는다. 그 행이 큐 맨 앞에
    남으면 뒤의 새 발화가 영영 제출되지 않는다.
    """
    assert _submission_error(settings_factory, 400).permanent is True


@pytest.mark.parametrize("status", [401, 403])
def test_an_auth_failure_is_not_permanent(settings_factory, status):
    """시크릿 설정 오류는 사람이 고치면 낫는다 — 그 사이의 기억을 버리지 않는다."""
    assert _submission_error(settings_factory, status).permanent is False


@pytest.mark.parametrize("status", [429, 500, 503])
def test_a_transient_failure_is_not_permanent(settings_factory, status):
    """서버가 돌아오면 그대로 성공할 요청이다. 포기할 이유가 없다."""
    assert _submission_error(settings_factory, status).permanent is False


def test_a_network_failure_is_not_permanent(settings_factory):
    """상태 코드가 아예 없는 실패(연결 끊김)도 재시도 대상이다."""
    import requests

    settings = settings_factory(
        HTTP_MAX_ATTEMPTS="1", BACKEND_BASE_URL="https://backend.example")
    client = BackendFactClient(
        settings=settings, session=StubSession(requests.ConnectionError("no route")))

    with pytest.raises(FactSubmissionError) as caught:
        client.submit_fact_candidates(
            SENIOR,
            conversation_id="conv-1",
            source_message_id="msg-1",
            facts=[{"factType": "FAMILY", "content": "손자가 자주 놀러 온다."}],
        )

    assert caught.value.permanent is False
