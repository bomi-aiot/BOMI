"""Gemini function calling과 의료 DB 조회 흐름을 직접 확인한다."""

import time

QUESTIONS = [
    "부산에 있는 병원 알려줘",
    "서울대병원 어디야",
    "서울대학교병원 어디야",
    "부산 서면에 약국 좀 찾아줘",
    "타이레놀 있어?",
    "타이레롤 있어?",
    "타이네롤 있어?",
]


def main() -> None:
    from bomi_ai_chat.config import Settings
    from bomi_ai_chat.llm.medical_flow import handle_medical_query

    settings = Settings.from_env()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY가 필요합니다.")
    settings.validate_database()

    for question in QUESTIONS:
        print(f"\n[질문] {question}")
        print(f"[응답] {handle_medical_query(question)}")
        time.sleep(3)


if __name__ == "__main__":
    main()
