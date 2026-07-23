"""STT/TTS 없이 LLM(로컬/API) 응답과 라우팅만 테스트."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.client import LLMClient
from src.llm.local_client import LocalLLMClient
from src.llm.router import choose_backend
from dotenv import load_dotenv
load_dotenv()

TEST_QUERIES = [
    # 가족/개인 맥락 - 새로 보강한 카테고리의 일반화 테스트 (api 기대)
    "손녀딸 요즘 학교생활 잘 하고 있나 모르겠어",
    "우리 며느리가 요즘 힘들어 보이던데",
    "옛날에 우리 애들 키울 때 얘기해줄까",
    "예전 살던 집 마당이 참 좋았는데",
    "우리 강아지 보고 싶네",

    # 정서/건강 - 간접 표현 일반화 테스트 (api 기대)
    "요즘 통 입맛이 없네",
    "밤에 자꾸 깨서 힘들어",
    "요새 눈물이 괜히 나더라고",
    "누구랑 얘기라도 하고 싶은데",
    "속이 더부룩하고 안 좋아",

    # 통제군: 명확히 local이어야 하는 문장 (회귀 확인용)
    "오늘 날씨 어때",
    "지금 몇 시야",
    "점심 뭐 먹을까?",
    "심심해",

    # 여전히 애매할 수 있는 경계 케이스
    "요즘 노래 듣는 게 낙이야",       # 취미 얘기 - local 쪽으로 남아야 자연스러움
    "예전 얘기 하나 해도 될까",       # personal_context와 유사하지만 가족 언급 없음
]

def run_single(label: str, client, text: str):
    start = time.perf_counter()
    response = client.generate(text)
    elapsed = time.perf_counter() - start
    print(f"[{label}] ({elapsed:.2f}s) {text} → {response}")


def main():
    llm_api = LLMClient()
    llm_local = LocalLLMClient()

    for text in TEST_QUERIES:
        backend, sim = choose_backend(text)
        print(f"\n--- 입력: '{text}' | 라우팅 판단: {backend} (sim={sim:.2f}) ---")

        # 라우팅 판단과 무관하게 둘 다 호출해서 답변을 나란히 비교
        run_single("Local", llm_local, text)
        run_single("API", llm_api, text)


if __name__ == "__main__":
    main()