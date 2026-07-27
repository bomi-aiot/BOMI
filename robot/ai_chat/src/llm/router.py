"""임베딩 유사도 기반 로컬/API 라우팅 판단."""

from sentence_transformers import SentenceTransformer, util

_model = SentenceTransformer("jhgan/ko-sroberta-multitask")

# 정형 정보 조회 — 판단 없이 바로 로컬로 보내는 패턴
DETERMINISTIC_KEYWORDS = ["날씨", "몇 시", "몇시", "오늘 날짜", "무슨 요일", "몇 월", "며칠"]

# 카테고리별 예시 문장 — API로 보낼 패턴들
API_EXAMPLES = {
    "personal_context": [
        "아까 내가 말했잖아", "저번에 이야기했던 거", "그때 그 얘기 있잖아",
        "우리 딸 얘기 좀 더 해줘", "손주가 보고 싶어",
        "손주 유치원 잘 다니고 있는지 모르겠네",
        "아들이 요즘 바쁜가봐", "며느리는 요즘 어떻게 지내나",
        "손녀가 이번에 학교 들어갔어", "사위가 요즘 회사 일이 힘든가봐",
        "우리 애들 어릴 때 얘기 좀 해줘", "작년에 갔던 여행 얘기 기억나?",
        "예전에 살던 동네 얘기했었잖아", "우리 강아지 이름이 뭐였더라",
    ],
    "emotional_health": [
        "몸이 아파요", "기운이 하나도 없어", "너무 외로워", "요즘 기분이 우울해",
        "여기저기 쑤셔", "잠을 잘 못 잤어", "입맛이 없어",
        "요즘 자꾸 눈물이 나", "마음이 답답해", "누구랑 얘기할 사람이 없네",
        "요즘 통 기운을 못 차리겠어", "속이 계속 안 좋아", "머리가 지끈거려",
        "밤에 잠이 안 와서 힘들어", "혼자 있으니 쓸쓸하네",
        "누구랑 얘기라도 하고 싶은데", "얘기할 사람이 없네", "말동무가 없어서 심심해",
    ],
    "medical_lookup": [
        "타이레놀 먹어도 되나요", "이 약 노인이 먹어도 되나",
        "이 약이랑 저 약 같이 먹어도 되나요", "약 같이 먹어도 괜찮은지 봐줘",
        "혈압약이랑 이거 같이 먹어도 돼?", "이 약 먹고 저것도 먹어도 되나",
        "근처 병원 좀 알려줘", "여기서 가까운 병원 어디야",
        "약국 어디 있어", "제일 가까운 약국 알려줘",
        "동네 병원 좀 찾아줘", "병원 위치 좀 알려줄래",
        "이 약 부작용 있어?", "이 약 먹어도 안전한가",
        "약 처방받은 거 확인 좀 해줘",
    ],
}

_category_embeddings = {
    cat: _model.encode(examples, convert_to_tensor=True)
    for cat, examples in API_EXAMPLES.items()
}

THRESHOLD = 0.6  # 테스트하면서 조정


def choose_backend(text: str) -> tuple[str, str | None, float]:
    """텍스트를 보고 (backend, category, score)를 반환한다."""
    if any(kw in text for kw in DETERMINISTIC_KEYWORDS):
        return "local", None, 0.0

    text_emb = _model.encode(text, convert_to_tensor=True)
    best_sim = 0.0
    for cat, cat_embs in _category_embeddings.items():
        max_sim = util.cos_sim(text_emb, cat_embs).max().item()
        if max_sim >= THRESHOLD:
            return "api", cat, max_sim
        best_sim = max(best_sim, max_sim)
    return "local", None, best_sim