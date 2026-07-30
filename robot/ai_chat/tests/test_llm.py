# robot/ai_chat/tests/test_llm.py
"""STT/TTS 없이 LLM(API) 응답만 테스트."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bomi_ai_chat.llm.client import LLMClient
from bomi_ai_chat.llm.router import is_medical_query
from dotenv import load_dotenv
load_dotenv()

TEST_QUERIES = [
    # 가족/개인 맥락
    "손녀딸 요즘 학교생활 잘 하고 있나 모르겠어",
    "우리 며느리가 요즘 힘들어 보이던데",
    "옛날에 우리 애들 키울 때 얘기해줄까",
    "예전 살던 집 마당이 참 좋았는데",
    "우리 강아지 보고 싶네",

    # 정서/건강 - 간접 표현
    "요즘 통 입맛이 없네",
    "밤에 자꾸 깨서 힘들어",
    "요새 눈물이 괜히 나더라고",
    "누구랑 얘기라도 하고 싶은데",
    "속이 더부룩하고 안 좋아",

    # 정형 정보성 질문 (날씨는 pipeline.py에서 별도 처리되므로 여기선 API로 감)
    "오늘 날씨 어때",
    "지금 몇 시야",
    "점심 뭐 먹을까?",
    "심심해",

    # 의료 관련 - is_medical_query가 True로 잡아야 함
    "타이레놀 먹어도 되나요",
    "근처 병원 좀 알려줘",
]


def run_single(client, text: str):
    start = time.perf_counter()
    response = client.generate(text)
    elapsed = time.perf_counter() - start
    print(f"({elapsed:.2f}s) {text} → {response}")


def main():
    llm_api = LLMClient()

    for text in TEST_QUERIES:
        medical = is_medical_query(text)
        print(f"\n--- 입력: '{text}' | medical_lookup 판단: {medical} ---")

        if medical:
            print("(의료 관련 — medical_flow.handle_medical_query로 처리될 문장, 여기선 스킵)")
            continue

        run_single(llm_api, text)


if __name__ == "__main__":
    main()
