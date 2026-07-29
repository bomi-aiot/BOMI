import os
import time
import requests
from db.medical_repository import find_hospitals, find_pharmacies, find_drug_info

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = "https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"

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
            "description": "특정 의약품의 이름, 종류(정제/캡슐/주사제 등), 용법용량, 보관법, 전문/일반 구분, 제조사 정보를 조회한다.",
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
사용자가 병원/약국을 찾거나 약 정보를 물으면 반드시 제공된 도구를 사용해서 확인한 뒤에만 답변하세요.
도구 없이 추측으로 답하지 마세요.
병원/약국을 찾을 때 지역명(region)과 특정 시설 이름(facility_name)은 서로 다른 값이니 절대 섞지 말고 각각 맞는 자리에 채우세요.

말투 규칙(반드시 지킬 것):
- 항상 존댓말을 사용하세요. 반말은 절대 쓰지 마세요.
- 노인 사용자가 알아듣기 쉽도록 짧고 담백한 문장으로 답하세요.
- "삐삐삐" 같은 로봇 효과음, 의성어, 장난스러운 감탄사를 넣지 마세요.
- 감정을 과장하거나 지나치게 발랄한 말투를 쓰지 말고, 차분하고 신뢰감 있게 답하세요.

응답 형식 규칙(반드시 지킬 것) — 이 답변은 화면에 뜨는 게 아니라 음성(TTS)으로 그대로 읽힙니다:
- 조회 결과가 여러 건이면 전체 주소나 전화번호를 나열하지 말고, 이름 위주로 2~3개만 간단히 말하고 "더 자세히 알려드릴까요?"처럼 되물으세요.
- 목록이나 별표(*), 특수기호를 쓰지 마세요. 음성으로 읽었을 때 자연스러운 문장으로만 답하세요.
- 사용자가 특정 한 곳을 더 자세히 물어봤을 때만 상세 정보를 말하세요.

병원/약국을 찾았는데 도구 조회 결과가 비어 있을 때(find_medical_facility 결과 없음):
- 절대로 스스로 알고 있는 지식(정식 명칭, 주소 등)으로 답을 지어내지 마세요. 반드시 도구 조회 결과만 근거로 답해야 합니다.
- 사용자가 말한 이름이 줄임말이거나 애칭일 가능성이 있으면(예: '서울대병원'처럼 정식 명칭이 아닐 수 있는 경우), "찾지 못했습니다"라고 말한 뒤 "정식 명칭으로 다시 한번 말씀해주시겠어요?"처럼 정중하게 다시 물어보세요.
- 절대 사용자가 말한 이름 대신 다른 이름(정식 명칭 등)을 확인 없이 검색 결과인 것처럼 답하지 마세요.

find_medical_facility 결과에 match_type이 "exact"로 표시된 경우에만 사용자가 말한 이름과 정확히 일치하는 것이니, 그 정보를 바탕으로 답하세요."""


def execute_tool(name: str, args: dict) -> dict:
    if name == "find_medical_facility":
        region = args.get("region")
        facility_name = args.get("facility_name")

        if args.get("facility_type") == "약국":
            rows = find_pharmacies(name=facility_name, region=region)
        else:
            rows = find_hospitals(name=facility_name, region=region)

        # facility_name으로 검색했는데 결과의 실제 이름이 사용자가 말한
        # 이름과 정확히 같지 않으면(부분 일치로만 걸린 경우), 이걸 확신
        # 있게 정답으로 취급하지 않도록 match_type을 표시한다.
        # 위치 오안내는 실제 피해로 이어질 수 있어, 이 경우 LLM이 반드시
        # 사용자에게 "맞으신가요?" 확인을 받도록 유도한다.
        # 비교 시 공백 차이(STT 인식 오차 등)는 무시하도록 정규화한다.
        match_type = None
        if facility_name and rows:
            normalized_input = "".join(facility_name.split())
            exact_rows = [
                r for r in rows
                if "".join(r["yadm_nm"].split()) == normalized_input
            ]
            if exact_rows:
                match_type = "exact"
                # 정확히 일치하는 곳만 남기고 나머지(부분 일치로 같이
                # 걸린 계열/지점 등)는 LLM에게 넘기지 않는다. LLM이
                # 알아서 골라 말하도록 맡기면 관계없는 곳까지 섞어
                # 설명하는 경우가 실제로 관측되었기 때문이다.
                rows = exact_rows
            else:
                match_type = "partial"

        return {"results": rows, "match_type": match_type}

    elif name == "check_pill_info":
        return find_drug_info(args.get("item_name"))

    return {"error": f"unknown tool: {name}"}


def _call_gemini(contents: list, max_retries: int = 2) -> dict:
    """
    503(서버 과부하)/429(요청 과다)는 일시적 장애일 가능성이 높아 잠깐 대기 후
    재시도한다. 429는 요청 빈도 제한이라 503보다 좀 더 여유 있게 기다린다.
    그 외 에러(401 인증 실패, 400 잘못된 요청 등)는 재시도해도 소용없으므로
    바로 예외를 올린다.
    """
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                GEMINI_URL,
                params={"key": GEMINI_API_KEY},
                json={
                    "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                    "contents": contents,
                    "tools": TOOLS,
                },
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status == 429 and attempt < max_retries:
                time.sleep(3 * (attempt + 1))
                continue
            if status == 503 and attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise


def _extract_part(data: dict) -> dict | None:
    """
    Gemini 응답에서 첫 번째 part를 안전하게 꺼낸다.
    candidates/content/parts 중 어느 하나라도 없을 수 있으므로
    (예: 안전 필터에 걸리거나 finishReason이 다르게 오는 경우) 방어적으로 처리한다.
    """
    candidates = data.get("candidates") or []
    if not candidates:
        return None
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    if not parts:
        return None
    return parts[0]


FALLBACK_MESSAGE = "죄송해요, 잘 이해하지 못했어요. 다시 한번 말씀해주시겠어요?"


RATE_LIMIT_MESSAGE = "지금 응답이 조금 늦어지고 있어요. 잠시 후 다시 말씀해주시겠어요?"


NOT_FOUND_MESSAGES = {
    "find_medical_facility": "찾으시는 곳을 확인하지 못했습니다. 정식 명칭으로 다시 한번 말씀해주시겠어요?",
    "check_pill_info": "찾으시는 약을 확인하지 못했습니다. 약 이름을 다시 한번 말씀해주시겠어요?",
}


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
    names = list(dict.fromkeys(r["yadm_nm"] for r in rows))  # 순서 유지 + 중복 제거
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
    names = list(dict.fromkeys(r["item_name"] for r in rows))
    guidance = " 아니라면 정확한 약 이름으로 다시 한번 말씀해주세요."
    if len(names) == 1:
        name = names[0]
        return f"{name}{_josa_eul_reul(name)} 찾으신 건가요?{guidance}"
    names_str = ", ".join(names[:3])
    return f"{names_str} 중에 찾으시는 약이 있으신가요?{guidance}"


def _is_empty_result(tool_result: dict) -> bool:
    """도구 조회 결과가 비어 있는지(찾은 게 없는지) 확인한다."""
    if "error" in tool_result:
        return True
    results = tool_result.get("results")
    return not results  # None, [], {} 모두 True


def _is_valid_spoken_text(text: str) -> bool:
    """
    Gemini가 실제 functionCall 대신 도구 호출을 파이썬 코드처럼 흉내 낸
    텍스트(예: '<tool_code>print(default_api.find_...)')를 그대로
    답변으로 내놓는 경우가 있다. 이런 텍스트는 TTS로 그대로 읽히면
    안 되므로, 코드처럼 보이는 패턴이 있으면 유효하지 않은 답변으로 판단한다.
    """
    if not text:
        return False
    suspicious_markers = ["<tool_code", "```", "default_api.", "print(", "```python"]
    return not any(marker in text for marker in suspicious_markers)


def handle_medical_query(user_text: str) -> str:
    contents = [{"role": "user", "parts": [{"text": user_text}]}]

    try:
        data = _call_gemini(contents)
    except requests.exceptions.HTTPError:
        return RATE_LIMIT_MESSAGE

    part = _extract_part(data)
    if part is None:
        return FALLBACK_MESSAGE

    if "functionCall" not in part:
        text = part.get("text", "")
        return text if _is_valid_spoken_text(text) else FALLBACK_MESSAGE

    fc = part["functionCall"]
    print(f"[디버그] 함수 호출: {fc['name']}, 인자: {fc.get('args', {})}")
    tool_result = execute_tool(fc["name"], fc.get("args", {}))

    # 조회 결과가 비어 있으면, LLM에게 답변 생성을 맡기지 않고
    # 코드에서 바로 고정 문구를 반환한다. LLM은 "결과 없음"을 근거로
    # 스스로 아는 지식을 지어내 답하는 경우가 실제로 관측되었기 때문에
    # (예: DB에 없는 병원의 주소를 확신 있게 답변), 이 경로에서는
    # LLM의 프롬프트 준수 여부에 의존하지 않고 원천적으로 차단한다.
    if _is_empty_result(tool_result):
        return NOT_FOUND_MESSAGES.get(fc["name"], FALLBACK_MESSAGE)

    # match_type이 partial(정확히 일치하지 않는 곳)이면, 그 이름으로
    # 확인 질문을 하되 "혹시 아니라면 정식 명칭으로 다시 말해달라"는
    # 안내를 함께 붙인다. LLM에게 맡기지 않고 코드에서 바로 반환하는 이유는,
    # 프롬프트 지시만으로는 LLM이 확인을 물으면서도 동시에 주소를
    # 흘려버리는 경우가 실제로 관측되었기 때문이다.
    if tool_result.get("match_type") == "partial":
        return _build_partial_match_message(tool_result)

    # 의약품도 마찬가지: match_type이 corrected(자모 유사도 보정을 거쳐
    # 찾은 것)면 성분/제형 등 상세 정보를 바로 주지 않고 확인만 한다.
    # STT가 첫 글자부터 잘못 알아들으면 보정이 완전히 다른 약(예:
    # 전문의약품/주사제)으로 튈 수 있는데, 이를 확신 있게 답하면
    # 실제 위해로 이어질 수 있다.
    if fc["name"] == "check_pill_info" and tool_result.get("match_type") == "corrected":
        return _build_drug_confirmation_message(tool_result)

    contents.append({"role": "model", "parts": [part]})
    contents.append({
        "role": "user",
        "parts": [{
            "functionResponse": {
                "name": fc["name"],
                "response": {"result": tool_result},
            }
        }],
    })

    try:
        data2 = _call_gemini(contents)
    except requests.exceptions.HTTPError:
        return RATE_LIMIT_MESSAGE

    part2 = _extract_part(data2)
    if part2 is None:
        return FALLBACK_MESSAGE

    text2 = part2.get("text", "")
    return text2 if _is_valid_spoken_text(text2) else FALLBACK_MESSAGE