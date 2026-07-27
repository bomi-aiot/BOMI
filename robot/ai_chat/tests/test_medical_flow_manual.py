# robot/ai_chat/tests/test_medical_flow_manual.py
"""medical_lookup 흐름(라우팅 → Gemini tool 호출 → 응답 생성) 수동 테스트."""
import sys
import os

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.append(os.path.abspath(SRC_DIR))

from llm.router import choose_backend
from llm.medical_flow import handle_medical_query


def test(text: str):
    print(f"\n입력: {text}")
    backend, category, score = choose_backend(text)
    print(f"라우팅 결과: backend={backend}, category={category}, score={score:.2f}")

    if backend == "api" and category == "medical_lookup":
        response = handle_medical_query(text)
        print(f"최종 응답: {response}")
    else:
        print("→ medical_lookup으로 안 빠짐 (라우팅부터 확인 필요)")


if __name__ == "__main__":
    test("타이레놀 노인이 먹어도 되나요?")
    test("근처 병원 좀 알려줘")
    test("이 약이랑 아미트리프틸린 같이 먹어도 돼?")