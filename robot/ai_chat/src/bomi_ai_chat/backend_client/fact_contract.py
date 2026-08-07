"""추출 프롬프트의 factType 을 백엔드 계약의 필드들로 옮긴다 (S15P11E102-255).

왜 이 모듈이 따로 있는가
    추출 프롬프트(prompts/templates/memory_extract.md)는 어르신의 말을 여섯
    가지로만 분류한다 — FAMILY, HOBBY, DAILY_LIFE, HEALTH, APPOINTMENT, OTHER.
    사람이 읽고 쓰기 쉬운 어휘이고, 모델에게 스무 개짜리 목록을 외우게 하는
    것보다 훨씬 안정적으로 지켜진다.

    반면 백엔드의 POST /api/v1/robot/fact-candidates 는 그것보다 훨씬 구체적인
    값을 요구한다 — targetDomain(MEMORY/CARE_RECORD), memory_type/record_type
    어휘와 같은 factType, operation, riskLevel. 서버가 이 값들로 "자동 반영해도
    되는가"를 판정하기 때문이다(FactRiskPolicy).

    이 둘을 잇는 표를 클라이언트(fact_client)나 틱(jobs/ticks) 안에 흩어 놓으면
    "모델이 뱉는 말"과 "서버가 요구하는 계약" 중 어느 쪽이 바뀌었을 때 어디를
    고쳐야 하는지 알 수 없게 된다. 그래서 변환만 하는 순수 함수 한 곳에 모은다.

주의 — 이 표가 곧 안전 판정의 입력이다
    HEALTH 를 MEMORY 로 잘못 보내면 서버는 그것을 "안전한 사실"로 보고 확인
    없이 저장한다. 복약·건강 관련 발화는 반드시 CARE_RECORD 로 가야 서버가
    보호자 확인 대기로 남긴다(CLAUDE.md §8 쓰기 경로 안전 규칙).

    APPOINTMENT 는 그 반대 방향의 위험을 진다. 서버가 일정류만 자동 반영하므로,
    이 표를 통과한 약속은 사람 확인 없이 보호자 화면의 일정이 된다. 그래서 이
    모듈에는 매핑 말고 검증이 하나 더 산다(_appointment_starts_at) — 시각을
    확정하지 못한 약속을 MEMORY/OTHER 로 강등하는 유일한 초크포인트다.

참고
    CLAUDE.md §8, §12 / 서버 측: FactRiskPolicy, ConversationFactIntakeService
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# 자바 DateTimeFormatter.ISO_OFFSET_DATE_TIME 이 받는 모양, 그것만.
#
# 왜 파서가 아니라 정규식이 먼저인가
#   파이썬 datetime.fromisoformat 의 허용 집합이 이것보다 넓다. 넓은 쪽으로 통과시키면
#   "로봇은 검증했다는데 서버는 못 읽는" 값이 생기고, 서버는 그때 예외를 던지는 대신
#   occurred_at 을 '지금'으로 채운다(CareRecordTime.parseIso 가 경고 한 줄만 남긴다).
#   APPOINTMENT 는 사람 확인 없이 자동 반영되므로 그 사이에 아무도 못 본다.
#
# 받는 것: 대문자 T 구분자, 초와 소수점은 선택, 오프셋은 'Z' 또는 '+HH:MM'(초 포함 가능).
# 안 받는 것: 공백 구분자, '+0900', '+09', 기본형식(20260811T140000).
_ISO_OFFSET_DATE_TIME = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,9})?)?(Z|[+-]\d{2}:\d{2}(:\d{2})?)"
)

# 약속으로 인정하는 미래의 상한.
#
# 이 제품이 다루는 약속은 진료·미용실·가족 방문이고 1년을 넘는 경우가 실질적으로 없다.
# 넘는 값은 맞는 약속이기보다 모델의 연도 계산 오류일 가능성이 압도적이다
# (예: '2126-08-11'). 자동 반영되는 유일한 종류라 중간에 사람이 보지 않으므로,
# 놓치는 쪽(기억으로 강등)이 지어내는 쪽보다 싸다.
_MAX_APPOINTMENT_HORIZON = timedelta(days=365)

# 추출 프롬프트의 factType -> (targetDomain, 서버 factType, riskLevel)
#
# 서버 factType 은 MEMORY 면 MemoryType enum, CARE_RECORD 면 care_record.record_type
# 어휘를 그대로 쓴다 — 서버의 FactMaterializer 가 이 문자열을 그대로 그 두 곳에
# 넣기 때문에, 알 수 없는 값을 보내면 조용히 OTHER 로 떨어진다.
#
# CARE_RECORD 안에서도 HEALTH 와 APPOINTMENT 의 운명이 갈린다
#   서버의 FactRiskPolicy 는 CARE_RECORD 중 일정류(APPOINTMENT/PERSONAL_SCHEDULE)만
#   자동 반영하고 나머지는 전부 확인 대기로 남긴다. HEALTH_CONDITION 은 그 "나머지"에
#   속하므로 "이제 아침 약 안 먹어" 류가 확인 없이 반영되는 일이 구조적으로 막힌다.
#   반대로 APPOINTMENT 는 그 문을 통과하므로, 로봇 쪽 검증이 마지막 방어선이다.
_FACT_TYPE_MAP: dict[str, tuple[str, str, str]] = {
    "FAMILY": ("MEMORY", "PERSONAL_RELATIONSHIP", "NORMAL"),
    "HOBBY": ("MEMORY", "HOBBY", "NORMAL"),
    "DAILY_LIFE": ("MEMORY", "DAILY_ROUTINE", "NORMAL"),
    "HEALTH": ("CARE_RECORD", "HEALTH_CONDITION", "SENSITIVE"),
    # 앞으로의 약속 (G4). ★ 이 한 줄이 다른 네 줄과 성격이 다르다.
    #
    #   서버의 FactRiskPolicy 는 일정류(APPOINTMENT/PERSONAL_SCHEDULE)만 "확인
    #   없이 반영해도 되돌리기 쉽다"고 보아 **자동 반영**한다. 즉 이 표를 통과하는
    #   순간 보호자 확인 대기를 거치지 않고 곧장 care_record 가 되고 보호자 화면의
    #   일정 목록에 뜬다. 아래 _appointment_starts_at 이 그 문을 지키는 유일한
    #   장치다.
    #
    #   riskLevel 을 SENSITIVE 로 올려서 막을 수는 없다 — 서버는 이 필드를 판정에
    #   쓰지 않는다고 명시한다(FactCandidateIntakeRequest javadoc: 참고값일 뿐).
    #   그런데도 SENSITIVE 라고 적으면 "확인이 필요한 사실"이라고 기록해 놓고 실제로는
    #   자동 반영되는, 감사 기록과 처리가 어긋난 행만 남는다. 그래서 NORMAL 이다.
    #
    #   실질적 킬스위치: 이 한 줄을 지우면 약속은 _FALLBACK(MEMORY/OTHER)으로
    #   떨어진다 — 내용은 기억으로 남고 일정 등록만 멈춘다. 별도 환경변수를 만들지
    #   않은 이유이며, 경로 전체를 끄려면 EXTRACTION_ENABLED 를 내리면 된다.
    "APPOINTMENT": ("CARE_RECORD", "APPOINTMENT", "NORMAL"),
    "OTHER": ("MEMORY", "OTHER", "NORMAL"),
}

# 모델이 목록에 없는 값을 뱉었을 때. 버리지 않고 OTHER 기억으로 남긴다 —
# 분류를 놓치는 것과 내용을 잃는 것은 다른 손해이고, 후자가 더 크다.
# (서버의 FactMaterializer.memoryType 이 알 수 없는 값을 OTHER 로 떨구는 것과
#  같은 방향의 판단이다.)
_FALLBACK = ("MEMORY", "OTHER", "NORMAL")


def _appointment_starts_at(
    fact: dict[str, Any], *, now_local: datetime | None = None
) -> str | None:
    """약속의 startsAt 을 검증해서 돌려준다. 못 믿을 값이면 None.

    now_local
        "지금"의 기준점. tz-aware 여야 한다. 과거·먼 미래 판정에만 쓴다.
        None 이면 그 두 검사를 건너뛴다 — 기준 시각을 모르는 채로 "이건 과거다"라고
        단정하면, 시간대를 모르는 어르신의 정상적인 약속을 조용히 버리게 된다.
        (모양·파싱 검증은 기준 시각과 무관하므로 항상 돈다.)

    ★ 이 함수가 없으면 무엇이 조용히 깨지는가
        서버의 FactMaterializer 는 proposedValue 를 통째로 care_record.details 로
        옮기고, occurred_at 을 CareRecordTime.fromDetailsOrNow(details, now) 로
        정한다. startsAt 이 없거나 자바 OffsetDateTime.parse 가 못 읽는 모양이면
        그쪽은 경고 한 줄만 남기고 null 을 돌려주며, occurred_at 은 '사실을 확인한
        지금'으로 채워진다. 그러면 어르신이 언제인지 말한 적도 없는 일정이 보호자
        화면에 '지금 일정'으로 뜬다. 모르는 것을 0(=지금)으로 채우는 전형이다.

        오프셋이 빠진 "2026-08-11T14:00" 이 정확히 그 경로다 — 사람 눈에는 멀쩡해
        보이고 파이썬 fromisoformat 도 읽어내지만, 그 값이 가리키는 절대 시각은
        어디에도 없다. 그래서 tzinfo 를 필수로 본다.

    왜 버리지 않고 None 인가
        호출부가 이 None 을 보고 사실 자체를 버리는 게 아니라 _FALLBACK(MEMORY/
        OTHER)으로 강등한다. "다음 주에 병원 가야 하는데"는 시각이 없어도 다음
        대화에서 꺼낼 가치가 있는 기억이다 — 분류를 놓치는 것과 내용을 잃는 것은
        다른 손해이고, 후자가 더 크다(위 _FALLBACK 주석과 같은 판단).

    반환값
        검증을 통과한 **모델이 준 원문 그대로**. 재포맷하지 않는다 — 파싱은 검증에만
        쓰고, 서버에는 검증된 원문을 보내야 파이썬과 자바의 해석이 갈리지 않는다.
    """
    raw = fact.get("startsAt")
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()

    # ★ 모양부터 자바 기준으로 고정한다 (리뷰 지적).
    #
    #   원래는 datetime.fromisoformat 만 썼는데, 그 함수의 허용 집합이 서버의
    #   OffsetDateTime.parse(= DateTimeFormatter.ISO_OFFSET_DATE_TIME)보다 **넓다.**
    #   넓은 쪽으로 통과시키면 "여기서는 검증됐는데 서버가 못 읽는" 값이 생기고,
    #   그 값의 종착지가 바로 이 함수가 막으려던 실패다 — occurred_at = 지금.
    #
    #   파이썬은 읽고 자바는 못 읽는 실제 형태들:
    #     '2026-08-11 14:00:00+09:00'  T 대신 공백    (파이썬 3.7+ 전부 통과)
    #     '2026-08-11T14:00:00+0900'   콜론 없는 오프셋
    #     '20260811T140000+0900'       기본형식
    #     '2026-08-11T14:00:00+09'     시만 있는 오프셋 (파이썬 3.11+ 통과)
    #
    #   마지막 것은 파이썬 버전에 따라 통과/거절이 갈려서, 젯슨 이미지를 바꾸면
    #   증상이 달라지는 최악의 형태다. 그래서 파서에 맡기지 않고 모양을 먼저 박는다.
    #
    #   ISO_OFFSET_DATE_TIME 이 받는 것: 대문자 T, 초·소수점 선택, 오프셋은 'Z' 또는
    #   '+HH:MM'('+HH:MM:SS' 포함). 그 밖은 전부 거절이다.
    if not _ISO_OFFSET_DATE_TIME.fullmatch(text):
        logger.warning(
            "appointment startsAt is not in the exact shape the server parses "
            "(ISO_OFFSET_DATE_TIME); demoting the fact to a memory"
        )
        return None

    # 모양이 맞아도 값이 틀릴 수 있다(2026-02-30, 25시). 그건 파서가 잡는다.
    # 파이썬 3.10 의 fromisoformat 은 "...Z" 를 못 읽으므로(3.11 부터 읽는다) 여기서
    # 바꿔 둔다 — 위 정규식이 이미 Z 를 합법으로 통과시켰기 때문에 필요하다.
    candidate = f"{text[:-1]}+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        logger.warning(
            "appointment startsAt has a valid shape but an impossible value; "
            "demoting the fact to a memory"
        )
        return None
    if parsed.tzinfo is None:
        # 정규식이 이미 오프셋을 요구하므로 여기 오지 않는다. 그래도 남겨 둔다 —
        # 정규식이 나중에 느슨해지면 이 검사가 마지막 방어선이 된다.
        logger.warning(
            "appointment startsAt has no UTC offset; demoting the fact to a memory "
            "(the server would silently record it as 'now')"
        )
        return None

    # ★ 시간축 위의 위치가 말이 되는가 (리뷰 지적).
    #
    #   여기까지는 "읽히는가"만 봤다. 읽히는 값 중에도 등록하면 안 되는 것이 있다.
    #   APPOINTMENT 는 서버가 **사람 확인 없이 자동 반영**하는 유일한 CARE_RECORD 라,
    #   중간에 아무도 보지 않는다.
    #
    #   과거를 막는 이유 — "지난 화요일에 병원 갔다 왔어"를 모델이 APPOINTMENT 로
    #   잘못 분류하면 지난 날짜의 일정이 생긴다. 앞으로의 일정을 보는 조회 경로에는
    #   뜨지 않으므로 어르신은 아무 알림도 못 받고, 예외도 경고도 남지 않는다.
    #   지나간 일은 일정이 아니라 기억이다.
    #
    #   먼 미래를 막는 이유 — 모델이 연도를 잘못 계산한 '2126-08-11' 같은 값이 그대로
    #   통과한다. 상한을 1년으로 두는 것은 이 제품이 다루는 약속(진료·미용실·가족 방문)이
    #   그보다 먼 경우가 실질적으로 없고, 넘는 값은 맞는 약속이기보다 계산 오류일
    #   가능성이 압도적으로 높기 때문이다. 놓치는 쪽이 지어내는 쪽보다 싸다.
    if now_local is not None:
        if parsed <= now_local:
            logger.warning(
                "appointment startsAt is not in the future; demoting the fact to a memory"
            )
            return None
        if parsed - now_local > _MAX_APPOINTMENT_HORIZON:
            logger.warning(
                "appointment startsAt is further out than %s; demoting the fact to a memory "
                "(a year-level miscalculation is likelier than a real appointment)",
                _MAX_APPOINTMENT_HORIZON,
            )
            return None

    return text


def to_intake_payload(
    fact: dict[str, Any],
    *,
    senior_id: str,
    conversation_id: str | None,
    source_message_id: str | None,
    now_local: datetime | None = None,
) -> dict[str, Any]:
    """추출된 사실 하나를 백엔드 요청 본문 하나로 바꾼다.

    무엇을 하는가
        {"factType": "FAMILY", "content": "..."} 를 서버의
        FactCandidateIntakeRequest 형태로 옮긴다.

    반환값
        seniorId/conversationId/sourceMessageId/targetDomain/factType/
        operation/proposedValue/riskLevel 을 담은 dict. 서버의 필수 필드를
        모두 채운다 — 하나라도 빠지면 bean validation 이 400 으로 거절한다.

    주의사항
        operation 은 항상 CREATE 다. 자유 대화에서 "기존 값을 고쳐라"를 판단할
        근거가 로봇에게 없다 — UPDATE/CANCEL 은 계약 대화(온보딩·재질의)나
        보호자 화면처럼 대상 행이 특정된 경로의 몫이다.

        약속(APPOINTMENT)만 proposedValue 에 키가 더 붙고, startsAt 을 믿을 수
        없으면 여기서 MEMORY/OTHER 로 강등된다. 즉 이 함수가 돌려주는 factType 은
        입력 factType 과 다를 수 있다 — 강등이 일어나는 유일한 지점이다.
    """
    target_domain, server_fact_type, risk_level = _FACT_TYPE_MAP.get(
        str(fact.get("factType", "")).upper(), _FALLBACK
    )

    content = str(fact.get("content", ""))
    proposed: dict[str, Any] = {"content": content}

    # 왜 여기서만 분기하는가 (G4)
    #   나머지 네 분류는 proposedValue 가 {"content": ...} 하나로 끝난다. 약속만
    #   다른 이유는 서버가 이것만 자동 반영하고, 그 반영에 '시각'이라는 추가 입력이
    #   필요하기 때문이다. 매핑표는 (targetDomain, factType, riskLevel) 튜플 구조를
    #   그대로 유지하고, 값이 아니라 '값의 검증'만 이 분기에 둔다 — 표에 네 번째
    #   칸을 만들면 나머지 네 줄에 영원히 빈칸이 남는다.
    if server_fact_type == "APPOINTMENT":
        starts_at = _appointment_starts_at(fact, now_local=now_local)
        if starts_at is None:
            # 시각을 확정하지 못한 약속은 일정이 아니라 기억으로 남긴다.
            # 여기가 강등이 일어나는 유일한 지점이다.
            target_domain, server_fact_type, risk_level = _FALLBACK
        else:
            # ★ content 는 약속에서도 그대로 남긴다 (위에서 이미 넣었고, 빼지 않는다).
            #   서버의 회피 대상 인물 필터(ConversationFactIntakeService.
            #   mentionsAvoidedPerson)가 proposedValue["content"] 하나만 읽는다.
            #   "약속은 title 이면 충분하지"라며 빼는 순간 그 필터가 통째로 꺼지고,
            #   돌아가신 배우자 이름이 들어간 일정이 아무 검사 없이 보호자 화면에 걸린다.
            #
            # 보호자 화면(ScheduleDto.title, ConfirmationTextFactory)이 이 키를
            # 읽는다. 없으면 "알 수 없음"이 뜨므로, 모델이 제목을 안 주면 content
            # 문장을 그대로 쓴다 — 제목치고 길지만, 지어내지도 비워두지도 않는다.
            title = str(fact.get("title") or "").strip() or content
            proposed["title"] = title
            proposed["startsAt"] = starts_at

            # ★ title 에만 있는 말이 회피 필터를 통과하지 못하게 한다 (리뷰 지적).
            #
            #   위 주석은 "content 를 빼지 마라"까지만 막았는데, 반대 방향이 남아 있었다.
            #   서버 필터(mentionsAvoidedPerson)는 proposedValue["content"] **하나만**
            #   읽는다. 모델이 회피 대상 이름을 title 에만 넣으면
            #   (content="다음 주 화요일 오후 세 시에 간다.", title="OOO 기일")
            #   필터는 이름을 보지 못하고 통과시킨다. APPOINTMENT 는 자동 반영이라
            #   사람 확인도 없어서, 돌아가신 분의 이름이 그대로 보호자 화면 일정 목록에
            #   걸린다.
            #
            #   서버를 고치는 편이 옳지만 그건 백엔드 라인이다. 여기서는 필터가 봐야 할
            #   글자가 반드시 content 안에 있도록 클라이언트가 보장한다.
            if title not in content:
                proposed["content"] = f"{content} ({title})"

    return {
        "seniorId": senior_id,
        "conversationId": conversation_id,
        "sourceMessageId": source_message_id,
        "targetDomain": target_domain,
        "factType": server_fact_type,
        "operation": "CREATE",
        "proposedValue": proposed,
        "riskLevel": risk_level,
    }
