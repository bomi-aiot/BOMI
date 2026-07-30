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
]

_medical_embeddings = _model.encode(MEDICAL_EXAMPLES, convert_to_tensor=True)

THRESHOLD = 0.6


def is_medical_query(text: str) -> bool:
    """의료(병원/약국/의약품) 관련 질문인지 판단한다."""
    text_emb = _model.encode(text, convert_to_tensor=True)
    max_sim = util.cos_sim(text_emb, _medical_embeddings).max().item()
    return max_sim >= THRESHOLD
