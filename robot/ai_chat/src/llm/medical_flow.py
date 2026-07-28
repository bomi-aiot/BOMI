# robot/ai_chat/src/llm/medical_flow.py
import os
import requests
from db.medical_repository import find_hospitals, find_pharmacies, find_drug_info

GEMINI_API_KEY = os.getenv("GMS_KEY")
GEMINI_URL = "https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"

TOOLS = [{
    "function_declarations": [
        {
            "name": "find_medical_facility",
            "description": "병원 또는 약국 정보를 검색한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "facility_type": {"type": "string", "enum": ["병원", "약국"]},
                    "region": {"type": "string", "description": "찾고자 하는 지역명 또는 병원/약국 이름"},
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

SYSTEM_PROMPT = """너는 노인 돌봄 로봇 '보미'야.
사용자가 병원/약국을 찾거나 약 정보를 물으면 반드시 제공된 도구를 사용해서 확인한 뒤에만 답변해.
도구 없이 추측으로 답하지 마."""


def execute_tool(name: str, args: dict) -> dict:
    if name == "find_medical_facility":
        region = args.get("region")
        if args.get("facility_type") == "약국":
            rows = find_pharmacies(name=region, region=region)
        else:
            rows = find_hospitals(name=region, region=region)
        return {"results": rows}

    elif name == "check_pill_info":
        rows = find_drug_info(args.get("item_name"))
        return {"results": rows}

    return {"error": f"unknown tool: {name}"}


def _call_gemini(contents: list) -> dict:
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


def handle_medical_query(user_text: str) -> str:
    contents = [{"role": "user", "parts": [{"text": user_text}]}]

    data = _call_gemini(contents)
    part = data["candidates"][0]["content"]["parts"][0]

    if "functionCall" not in part:
        return part.get("text", "")

    fc = part["functionCall"]
    tool_result = execute_tool(fc["name"], fc.get("args", {}))

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

    data2 = _call_gemini(contents)
    return data2["candidates"][0]["content"]["parts"][0].get("text", "")