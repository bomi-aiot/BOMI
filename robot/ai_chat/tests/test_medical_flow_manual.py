# robot/ai_chat/tests/test_medical_flow_manual.py
import sys, os, time
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
sys.path.append(os.path.abspath(SRC_DIR))

from bomi_ai_chat.llm.medical_flow import handle_medical_query

questions = [
    "부산에 있는 병원 알려줘",       # region만 있는 케이스
    "서울대병원 어디야",             # facility_name만 있는 케이스
    '서울대학교병원 어디야',
    "부산 서면에 약국 좀 찾아줘",     # region(약국) 케이스
    "타이레놀 있어?",                # 의약품 정확한 이름
    "타이레롤 있어?",                # 의약품 오타
    "타이네롤 있어?",                # 의약품 심한 오타 -> 되묻기 확인
]

for q in questions:
    print(f"\n[질문] {q}")
    print(f"[응답] {handle_medical_query(q)}")
    time.sleep(3)  # 연속 요청으로 인한 rate limit(429) 방지
