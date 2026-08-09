import logging
import time
from collections.abc import Callable, Mapping
from typing import Any

import requests

from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.db.medical_repository import (
    MedicalRepositoryError,
    find_drug_info,
    find_hospitals,
    find_pharmacies,
)
from bomi_ai_chat.http import (
    ExternalServiceError,
    decode_json_object,
    request_with_retry,
)

GEMINI_URL = "https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent"
LOGGER = logging.getLogger(__name__)

TOOLS = [{
    "function_declarations": [
        {
            "name": "find_medical_facility",
            "description": "병원 또는 약국 정보를 검색한다. 지역명과 시설 이름은 서로 다른 개념이므로 반드시 구분해서 채운다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "facility_type": {"type": "string", "enum": ["병원", "약국"]},
                    "region": {
                        "type": "string",
                        "description": "찾고자 하는 지역명 (예: 부산, 강남구, 해운대). 특정 시설 이름이 아니라 위치를 나타낼 때만 채운다.",
                    },
                    "facility_name": {
                        "type": "string",
                        "description": "사용자가 특정 병원/약국 이름을 언급한 경우에만 채운다 (예: 서울대병원, 온누리약국). 지역명이면 여기 넣지 않는다.",
                    },
                },
                "required": ["facility_type"],
            },
        },
        {
            "name": "check_pill_info",
            "description": (
                "의약품 허가 데이터에서 제품명, 업체명, 허가일, "
                "원료성분명, 품목구분을 조회한다. 복용법, 보관법, "
                "효능, 부작용, 병용 가능 여부는 이 도구로 판단할 수 없다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {"type": "string", "description": "사용자가 말한 약 이름 (그대로 전달, 임의 보정 금지)"},
                },
                "required": ["item_name"],
            },
        },
    ]
}]

SYSTEM_PROMPT = """당신은 노인 돌봄 로봇 '보미'입니다.
사용자가 병원/약국을 찾거나 약 정보를 물으면 반드시 제공된 도구 중 하나를 호출하세요.
의료 지식을 직접 답하거나 도구 조회 결과를 추측해서 텍스트로 답하지 마세요.
병원/약국을 찾을 때 지역명(region)과 특정 시설 이름(facility_name)은 서로 다른 값이니 절대 섞지 말고 각각 맞는 자리에 채우세요.
지역과 시설 이름을 모두 알 수 없다면 임의 값을 만들지 말고 facility_type만 전달하세요. 애플리케이션이 사용자에게 위치를 다시 묻습니다.
의약품 이름을 알 수 없다면 임의로 보정하거나 다른 제품명을 만들지 마세요.

말투 규칙(반드시 지킬 것):
- 항상 존댓말을 사용하세요. 반말은 절대 쓰지 마세요.
- 노인 사용자가 알아듣기 쉽도록 짧고 담백한 문장으로 답하세요.
- "삐삐삐" 같은 로봇 효과음, 의성어, 장난스러운 감탄사를 넣지 마세요.
- 감정을 과장하거나 지나치게 발랄한 말투를 쓰지 말고, 차분하고 신뢰감 있게 답하세요.

도구 호출 뒤의 사용자 안내는 애플리케이션 코드가 DB 결과만으로 생성합니다.
따라서 도구 호출 이후의 자연어 답변을 미리 작성하지 마세요."""


MAX_TOOL_ARGUMENT_LENGTH = 100
VALID_FACILITY_TYPES = frozenset({"병원", "약국"})
RELATIVE_LOCATION_TERMS = frozenset(
    {
        "근처",
        "내근처",
        "이근처",
        "주변",
        "내주변",
        "여기",
        "현재위치",
        "가까운곳",
        "근방",
        "우리동네",
    }
)
GENERIC_FACILITY_NAMES = frozenset(
    {
        "병원",
        "약국",
        "의원",
        "의료기관",
        "근처병원",
        "근처약국",
        "가까운병원",
        "가까운약국",
    }
)
GENERIC_DRUG_NAMES = frozenset({"약", "약품", "의약품", "알약", "이약", "그약"})


class ToolArgumentError(ValueError):
    """Gemini functionCall의 이름이나 인자가 계약과 다를 때 발생한다."""


def _text_argument(
    args: Mapping[str, Any],
    name: str,
    *,
    required: bool = False,
) -> str | None:
    if name not in args or args[name] is None:
        if required:
            raise ToolArgumentError(f"{name} 값이 필요합니다.")
        return None

    value = args[name]
    if not isinstance(value, str):
        raise ToolArgumentError(f"{name}은 문자열이어야 합니다.")
    value = " ".join(value.split())
    if not value:
        if required:
            raise ToolArgumentError(f"{name}은 비어 있을 수 없습니다.")
        return None
    if len(value) > MAX_TOOL_ARGUMENT_LENGTH:
        raise ToolArgumentError(f"{name}이 너무 깁니다.")
    return value


def _invalid_tool_result(reason: str) -> dict:
    return {
        "status": "invalid",
        "reason": reason,
        "results": [],
    }


def _normalized_term(value: str) -> str:
    return "".join(value.split()).casefold()


def _database_error_result() -> dict:
    return {
        "status": "database_error",
        "results": [],
    }


def _valid_rows(rows: Any, *, name_field: str) -> list[Mapping[str, Any]]:
    if not isinstance(rows, list):
        raise MedicalRepositoryError("의료 DB 결과가 목록이 아닙니다.")
    valid_rows = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise MedicalRepositoryError("의료 DB 행이 객체가 아닙니다.")
        value = row.get(name_field)
        if not isinstance(value, str) or not value.strip():
            raise MedicalRepositoryError(
                f"의료 DB 행에 {name_field} 값이 없습니다."
            )
        valid_rows.append(row)
    return valid_rows


def _deduplicate_rows(
    rows: list[Mapping[str, Any]],
    *,
    fields: tuple[str, ...],
) -> list[Mapping[str, Any]]:
    unique_rows = []
    seen = set()
    for row in rows:
        signature = tuple(_spoken_value(row.get(field)) for field in fields)
        if signature not in seen:
            seen.add(signature)
            unique_rows.append(row)
    return unique_rows


def _execute_facility_tool(args: Mapping[str, Any]) -> dict:
    unexpected = set(args) - {"facility_type", "region", "facility_name"}
    if unexpected:
        raise ToolArgumentError("지원하지 않는 시설 검색 인자가 있습니다.")

    facility_type = _text_argument(args, "facility_type", required=True)
    if facility_type not in VALID_FACILITY_TYPES:
        raise ToolArgumentError("facility_type은 병원 또는 약국이어야 합니다.")
    region = _text_argument(args, "region")
    facility_name = _text_argument(args, "facility_name")
    if region and _normalized_term(region) in RELATIVE_LOCATION_TERMS:
        region = None
    if (
        facility_name
        and _normalized_term(facility_name) in GENERIC_FACILITY_NAMES
    ):
        facility_name = None
    if not region and not facility_name:
        return {
            "status": "needs_location",
            "facility_type": facility_type,
            "results": [],
        }

    if facility_type == "약국":
        rows = find_pharmacies(name=facility_name, region=region)
    else:
        rows = find_hospitals(name=facility_name, region=region)
    rows = _valid_rows(rows, name_field="yadm_nm")

    if not rows:
        return {
            "status": "not_found",
            "facility_type": facility_type,
            "region": region,
            "facility_name": facility_name,
            "results": [],
        }

    match_type = "regional"
    status = "ok"
    if facility_name:
        normalized_input = "".join(facility_name.split()).casefold()
        exact_rows = [
            row
            for row in rows
            if "".join(row["yadm_nm"].split()).casefold()
            == normalized_input
        ]
        if exact_rows:
            rows = _deduplicate_rows(
                exact_rows,
                fields=("yadm_nm", "addr", "cl_cd_nm", "telno"),
            )
            match_type = "exact"
            if len(rows) > 1:
                status = "needs_facility_selection"
        else:
            match_type = "partial"
            status = "needs_confirmation"

    return {
        "status": status,
        "facility_type": facility_type,
        "region": region,
        "facility_name": facility_name,
        "match_type": match_type,
        "results": rows,
    }


def _execute_drug_tool(args: Mapping[str, Any]) -> dict:
    unexpected = set(args) - {"item_name"}
    if unexpected:
        raise ToolArgumentError("지원하지 않는 의약품 검색 인자가 있습니다.")

    item_name = _text_argument(args, "item_name")
    if not item_name or _normalized_term(item_name) in GENERIC_DRUG_NAMES:
        return {
            "status": "needs_drug_name",
            "results": [],
        }
    result = find_drug_info(item_name)
    if not isinstance(result, Mapping):
        raise MedicalRepositoryError("의약품 DB 결과가 객체가 아닙니다.")
    rows = _valid_rows(result.get("results"), name_field="item_name")
    match_type = result.get("match_type")

    if not rows:
        return {
            "status": "not_found",
            "item_name": item_name,
            "match_type": None,
            "results": [],
        }
    if match_type == "exact":
        rows = _deduplicate_rows(
            rows,
            fields=(
                "item_name",
                "entp_name",
                "item_permit_date",
                "item_ingr_name",
                "prduct_type",
            ),
        )
        status = "ok" if len(rows) == 1 else "needs_drug_selection"
    elif match_type == "corrected":
        status = "needs_confirmation"
    else:
        raise MedicalRepositoryError("알 수 없는 의약품 일치 상태입니다.")

    return {
        "status": status,
        "item_name": item_name,
        "match_type": match_type,
        "results": rows,
    }


def execute_tool(name: str, args: Any) -> dict:
    """Gemini 도구 호출을 검증하고 DB 상태를 명시적으로 구분한다."""

    if not isinstance(name, str):
        return _invalid_tool_result("도구 이름은 문자열이어야 합니다.")
    if not isinstance(args, Mapping):
        return _invalid_tool_result("도구 인자는 객체여야 합니다.")

    try:
        if name == "find_medical_facility":
            return _execute_facility_tool(args)
        if name == "check_pill_info":
            return _execute_drug_tool(args)
        return _invalid_tool_result("지원하지 않는 의료 도구입니다.")
    except ToolArgumentError as exc:
        return _invalid_tool_result(str(exc))
    except MedicalRepositoryError:
        LOGGER.exception("의료 DB 조회 실패: tool=%s", name)
        return _database_error_result()


def _call_gemini(
    contents: list,
    *,
    settings: Settings | None = None,
    session: Any = requests,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """공통 외부 HTTP 정책으로 의료 Gemini를 호출한다."""

    settings = settings or get_settings()
    response = request_with_retry(
        "POST",
        GEMINI_URL,
        service="Gemini 의료",
        timeout_seconds=settings.http_timeout_seconds,
        max_attempts=settings.http_max_attempts,
        backoff_seconds=settings.http_backoff_seconds,
        max_backoff_seconds=settings.http_max_backoff_seconds,
        session=session,
        sleep=sleep,
        params={"key": settings.gemini_api_key},
        json={
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": contents,
            "tools": TOOLS,
            # 여기엔 maxOutputTokens 가 없어 잘릴 위험은 없지만, thinking 을
            # 켜두면 도구 호출 한 번이 1.6~2.0초로 늘고 사고 토큰 157~228 개가
            # 매번 과금된다. 끄면 1.0초이고 functionCall 결과는 동일하다
            # (2026-08-10 실측).
            "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
        },
    )
    return decode_json_object(response, service="Gemini 의료")


def _extract_part(data: dict) -> dict | None:
    """
    Gemini 응답에서 첫 번째 part를 안전하게 꺼낸다.
    candidates/content/parts 중 어느 하나라도 없을 수 있으므로
    (예: 안전 필터에 걸리거나 finishReason이 다르게 오는 경우) 방어적으로 처리한다.
    """
    candidates = data.get("candidates") or []
    if not isinstance(candidates, list) or not candidates:
        return None
    candidate = candidates[0]
    if not isinstance(candidate, Mapping):
        return None
    content = candidate.get("content") or {}
    if not isinstance(content, Mapping):
        return None
    parts = content.get("parts") or []
    if not isinstance(parts, list) or not parts:
        return None
    part = parts[0]
    if not isinstance(part, Mapping):
        return None
    return dict(part)


FALLBACK_MESSAGE = "죄송해요, 잘 이해하지 못했어요. 다시 한번 말씀해주시겠어요?"


SERVICE_UNAVAILABLE_MESSAGE = (
    "지금 의료 정보를 확인하기 어렵습니다. 잠시 후 다시 말씀해주시겠어요?"
)


INVALID_TOOL_MESSAGE = (
    "의료 요청을 정확히 확인하지 못했습니다. 다시 한번 말씀해주시겠어요?"
)
LOCATION_REQUIRED_MESSAGE = (
    "병원이나 약국을 찾으려면 지역명이나 정확한 기관 이름을 말씀해주세요."
)
DRUG_NAME_REQUIRED_MESSAGE = "확인할 약의 정확한 이름을 말씀해주세요."
FACILITY_SELECTION_REQUIRED_MESSAGE = (
    "같은 이름의 기관이 여러 곳 확인됐습니다. 찾는 지역을 함께 말씀해주세요."
)
DRUG_SELECTION_REQUIRED_MESSAGE = (
    "같은 이름의 의약품이 여러 건 확인됐습니다. "
    "포장에 적힌 제조사를 확인해주시거나 약사에게 문의해주세요."
)
DATABASE_ERROR_MESSAGE = (
    "지금 의료 정보 데이터베이스를 확인하기 어렵습니다. "
    "잠시 후 다시 말씀해주시겠어요?"
)
FACILITY_NOT_FOUND_MESSAGE = (
    "찾으시는 곳을 확인하지 못했습니다. "
    "지역이나 정식 기관 이름을 다시 말씀해주시겠어요?"
)
DRUG_NOT_FOUND_MESSAGE = (
    "찾으시는 약을 확인하지 못했습니다. "
    "약 이름을 다시 한번 말씀해주시겠어요?"
)


def _josa_eul_reul(word: str) -> str:
    """
    단어의 마지막 글자에 받침이 있으면 '을', 없으면 '를'을 반환한다.
    한글 유니코드는 (코드 - 0xAC00)을 28로 나눈 나머지가 종성(받침) 인덱스이며,
    0이면 받침이 없다는 뜻이다.
    """
    if not word:
        return "를"
    last_char = word[-1]
    code = ord(last_char) - 0xAC00
    if 0 <= code < 11172:  # 완성형 한글 음절 범위
        jongseong = code % 28
        return "을" if jongseong != 0 else "를"
    return "를"  # 한글 음절이 아니면(숫자/영문 등) 기본값


def _build_partial_match_message(tool_result: dict) -> str:
    """
    facility_name 검색이 정확히 일치하지 않고(match_type == 'partial')
    이름 일부만 겹치는 곳이 나왔을 때, 그 이름으로 확인 질문을 하되
    "혹시 아니라면 줄임말 말고 정식 명칭으로 다시 말해달라"는 안내를
    함께 붙인다. 주소/전화번호 등 상세 정보는 절대 포함하지 않는다 —
    확인도 받기 전에 상세 정보를 흘리면 되묻기 자체가 무의미해지기 때문이다.
    """
    rows = tool_result.get("results", [])
    names = list(dict.fromkeys(row["yadm_nm"] for row in rows))
    guidance = " 만약 아니라면 줄임말이 아닌 정식 명칭으로 다시 말씀해주세요."
    if len(names) == 1:
        name = names[0]
        return f"{name}{_josa_eul_reul(name)} 찾으신 건가요?{guidance}"
    names_str = ", ".join(names[:3])
    return f"{names_str} 중에 찾으시는 곳이 있으신가요?{guidance}"


def _build_drug_confirmation_message(tool_result: dict) -> str:
    """
    item_name 검색이 정확히 일치하지 않아(match_type == 'corrected')
    자모 유사도 보정을 거쳐 찾은 약일 때, 그 이름으로 확인 질문만 하고
    성분/제형/전문-일반 구분 등 상세 정보는 절대 포함하지 않는다.
    STT가 첫 글자부터 잘못 알아듣는 경우(예: '타이레놀'->'하이레놀') 보정이
    완전히 다른 약(예: 전문의약품/주사제)으로 튈 수 있는데, 이때 상세
    정보를 확신 있게 전달하면 실제 위해로 이어질 수 있어 반드시 확인부터
    받는다.
    """
    rows = tool_result.get("results", [])
    names = list(dict.fromkeys(row["item_name"] for row in rows))
    guidance = " 아니라면 정확한 약 이름으로 다시 한번 말씀해주세요."
    if len(names) == 1:
        name = names[0]
        return f"{name}{_josa_eul_reul(name)} 찾으신 건가요?{guidance}"
    names_str = ", ".join(names[:3])
    return f"{names_str} 중에 찾으시는 약이 있으신가요?{guidance}"


def _spoken_value(value: Any) -> str | None:
    if value is None or isinstance(value, (Mapping, list, tuple, set)):
        return None
    text = " ".join(str(value).split())
    return text or None


def _build_facility_result_message(tool_result: dict) -> str:
    rows = tool_result["results"]
    if tool_result.get("match_type") == "regional":
        names = list(dict.fromkeys(row["yadm_nm"] for row in rows))[:3]
        return (
            f"검색된 {tool_result['facility_type']}은 "
            f"{', '.join(names)}입니다. 어느 곳을 자세히 알려드릴까요?"
        )

    row = rows[0]
    name = row["yadm_nm"]
    address = _spoken_value(row.get("addr"))
    if tool_result["facility_type"] == "약국":
        telephone = _spoken_value(row.get("telno"))
        message = f"{name}"
        if address:
            message += f"은 {address}에 있습니다"
        else:
            message += "을 확인했습니다"
        if telephone:
            message += f". 전화번호는 {telephone}입니다"
        return message + "."

    category = _spoken_value(row.get("cl_cd_nm"))
    message = f"{name}"
    if address:
        message += f"은 {address}에 있습니다"
    else:
        message += "을 확인했습니다"
    if category:
        message += f". 기관 구분은 {category}입니다"
    return message + "."


def _build_exact_drug_message(tool_result: dict) -> str:
    row = tool_result["results"][0]
    name = row["item_name"]
    company = _spoken_value(row.get("entp_name"))
    product_type = _spoken_value(row.get("prduct_type"))

    details = []
    if company:
        details.append(f"업체는 {company}")
    if product_type:
        details.append(f"품목 구분은 {product_type}")

    if details:
        verified = f"{name} 제품은 DB에서 확인됐고, {', '.join(details)}입니다."
    else:
        verified = f"{name} 제품은 DB에서 확인됐습니다."
    return (
        f"{verified} 이 자료만으로 복용 가능 여부나 용법을 판단할 수 없으니 "
        "의사나 약사에게 확인해주세요."
    )


def _tool_result_message(name: str, tool_result: dict) -> str:
    status = tool_result.get("status")
    if status == "invalid":
        LOGGER.warning(
            "의료 도구 호출 거부: tool=%s reason=%s",
            name,
            tool_result.get("reason"),
        )
        return INVALID_TOOL_MESSAGE
    if status == "needs_location":
        return LOCATION_REQUIRED_MESSAGE
    if status == "needs_drug_name":
        return DRUG_NAME_REQUIRED_MESSAGE
    if status == "needs_facility_selection":
        return FACILITY_SELECTION_REQUIRED_MESSAGE
    if status == "needs_drug_selection":
        return DRUG_SELECTION_REQUIRED_MESSAGE
    if status == "database_error":
        return DATABASE_ERROR_MESSAGE
    if status == "not_found":
        if name == "check_pill_info":
            return DRUG_NOT_FOUND_MESSAGE
        return FACILITY_NOT_FOUND_MESSAGE
    if status == "needs_confirmation":
        if name == "check_pill_info":
            return _build_drug_confirmation_message(tool_result)
        return _build_partial_match_message(tool_result)
    if status == "ok":
        if name == "check_pill_info":
            return _build_exact_drug_message(tool_result)
        if name == "find_medical_facility":
            return _build_facility_result_message(tool_result)
    return FALLBACK_MESSAGE


def handle_medical_query(user_text: str) -> str:
    contents = [{"role": "user", "parts": [{"text": user_text}]}]

    try:
        data = _call_gemini(contents)
    except ExternalServiceError:
        LOGGER.exception("의료 Gemini 첫 번째 호출 실패")
        return SERVICE_UNAVAILABLE_MESSAGE

    part = _extract_part(data)
    if part is None:
        return FALLBACK_MESSAGE

    function_call = part.get("functionCall")
    if not isinstance(function_call, Mapping):
        LOGGER.warning("의료 Gemini가 functionCall 없이 응답했습니다.")
        return FALLBACK_MESSAGE

    name = function_call.get("name")
    args = function_call.get("args", {})
    LOGGER.info("의료 도구 호출: %s", name)
    tool_result = execute_tool(name, args)
    return _tool_result_message(name if isinstance(name, str) else "", tool_result)
