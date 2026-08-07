"""Gemini 일반 대화와 의료 분류 모델을 실제 호출해 확인한다."""

import time

TEST_QUERIES = [
    "손녀딸 요즘 학교생활 잘 하고 있나 모르겠어",
    "요즘 통 입맛이 없네",
    "오늘 날씨 어때",
    "점심 뭐 먹을까?",
    "타이레놀 먹어도 되나요",
    "근처 병원 좀 알려줘",
]


def main() -> None:
    from bomi_ai_chat.config import Settings
    from bomi_ai_chat.llm.client import LLMClient
    from bomi_ai_chat.llm.router import is_medical_query

    settings = Settings.from_env()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY가 필요합니다.")
    client = LLMClient(settings)

    for text in TEST_QUERIES:
        medical = is_medical_query(text)
        print(f"\n--- 입력: {text!r} | medical_lookup: {medical} ---")
        if medical:
            print("(의료 조회 경로이므로 일반 LLM 호출은 생략합니다.)")
            continue

        started_at = time.perf_counter()
        response = client.generate(text)
        elapsed = time.perf_counter() - started_at
        print(f"({elapsed:.2f}s) {text} → {response}")


if __name__ == "__main__":
    main()
