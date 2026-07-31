# robot/ai_chat/src/bomi_ai_chat/llm/router.py
"""임베딩 유사도 기반 medical_lookup 판단 (단일 API 체제)."""

from sentence_transformers import SentenceTransformer, util

_model = SentenceTransformer("jhgan/ko-sroberta-multitask")

MEDICAL_EXAMPLES = [
    "타이레놀 먹어도 되나요", "이 약 노인이 먹어도 되나",
    "이 약이랑 저 약 같이 먹어도 되나요", "약 같이 먹어도 괜찮은지 봐줘",
    "혈압약이랑 이거 같이 먹어도 돼?", "이 약 먹고 저것도 먹어도 되나",
    "근처 병원 좀 알려줘", "여기서 가까운 병원 어디야",
    "약국 어디 있어", "제일 가까운 약국 알려줘",
    "동네 병원 좀 찾아줘", "병원 위치 좀 알려줄래",
    "이 약 부작용 있어?", "이 약 먹어도 안전한가",
    "약 처방받은 거 확인 좀 해줘",
    # 증상 + 병원 문의 패턴 (간접적으로 병원을 묻는 경우)
    "허리가 아픈데 병원 가봐야 할까", "다리가 아파서 병원 가야하나",
    "배가 아픈데 병원 가야할까", "머리가 아픈데 병원 가봐야 하나",
    "무릎이 아픈데 병원 가야 하나", "속이 안 좋은데 병원 가야 할까",
    # 흔한 상비약 브랜드명
    "게보린 있어?", "판피린 있어?", "정로환 있어?", "베아제 있어?",
    "활명수 있어?", "후시딘 있어?", "마데카솔 있어?", "우루사 있어?", "인사돌 있어?",
    # 파스류
    "파스 붙여야 하는데 뭐가 좋을까", "파스 있어?",
    # 동사 없이 시설명/진료과만 언급하는 명사형 패턴
    "정형외과", "이비인후과", "안과", "소아과", "치과", "내과",
    "대현동 정형외과", "서면 이비인후과",
]

_medical_embeddings = _model.encode(MEDICAL_EXAMPLES, convert_to_tensor=True)

THRESHOLD = 0.6


def is_medical_query(text: str) -> bool:
    """의료(병원/약국/의약품) 관련 질문인지 판단한다."""
    text_emb = _model.encode(text, convert_to_tensor=True)
    max_sim = util.cos_sim(text_emb, _medical_embeddings).max().item()
    return max_sim >= THRESHOLD



# ---------------------------------------------------------------------------
# 날씨 의도 판단
# ---------------------------------------------------------------------------
# 사용자가 '날씨'를 물었는지 판단한다. 정확한 단어("날씨")를 찾는 대신,
# 문장의 '의미'가 아래 예시들과 비슷한지로 판단한다.
WEATHER_EXAMPLES = [
    "오늘 날씨 어때", "오늘 날씨 알려줘", "지금 날씨 어때", "내일 날씨 어때",
    "서울 날씨 알려줘", "부산 날씨 어때", "오늘 부산 날씨 어때",
    "밖에 날씨 어때", "지금 밖에 어때",
    "오늘 비 와?", "비 올까?", "우산 챙겨야 해?",
    "밖에 추워?", "오늘 더워?", "기온 몇 도야", "오늘 하늘 어때",
]

_weather_embeddings = _model.encode(WEATHER_EXAMPLES, convert_to_tensor=True)

WEATHER_THRESHOLD = 0.7


def is_weather_query(text: str) -> bool:
    """날씨 관련 질문인지 (문장 의미 기준으로) 판단한다."""
    text_emb = _model.encode(text, convert_to_tensor=True)
    max_sim = util.cos_sim(text_emb, _weather_embeddings).max().item()
    return max_sim >= WEATHER_THRESHOLD
