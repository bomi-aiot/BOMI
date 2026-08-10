# robot/ai_chat/src/bomi_ai_chat/llm/router.py
"""의료·날씨 조회 의도를 값싼 결정 규칙으로 판정한다."""

from __future__ import annotations


def _load_legacy_model():
    """제거한 임베딩 라우터를 오프라인 비교 평가할 때만 로드한다.

    무엇을 하는가
        먼저 local_files_only=True 로 시도해 디스크 캐시만 읽는다. 캐시가 없을 때
        (기기 첫 설치)만 예외를 받아 평소처럼 내려받는다.

    왜 존재하는가  ★ 233 실기에서 의료 질문 턴이 21~36초씩 걸렸다
        sentence-transformers 는 캐시가 있어도 로드할 때마다 HF Hub 에 갱신 확인
        요청을 보낸다. 젯슨의 느린 회선에서는 그 확인만으로 수 초가 늘어지고,
        오프라인이면 타임아웃을 다 기다린 뒤에야 캐시로 돌아온다 — 로봇이
        오프라인일 때가 바로 이 판정이 로컬이어서 살아남아야 하는 순간이다
        (CLAUDE.md §18). 캐시 우선이면 두 경우 모두 네트워크를 아예 안 탄다.

    운영 런타임은 이 함수를 호출하지 않는다. evals/evaluate_router.py의
    --legacy-model 옵션만 사용하며 sentence-transformers도 선택 의존성이다.
    """
    from sentence_transformers import SentenceTransformer

    try:
        return SentenceTransformer("jhgan/ko-sroberta-multitask", local_files_only=True)
    except Exception:  # noqa: BLE001 - 캐시가 없으면 첫 설치이므로 내려받는다
        return SentenceTransformer("jhgan/ko-sroberta-multitask")


# 제거한 모델을 같은 조건으로 재평가하기 위한 예시 스냅샷이다.
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

THRESHOLD = 0.6

_MEDICAL_TOPICS = (
    "병원", "약국", "응급실", "의원", "진료", "처방", "부작용", "복용",
    "정형외과", "이비인후과", "내과", "치과", "안과", "피부과", "소아과",
    "타이레놀", "게보린", "아스피린", "마데카솔", "겔포스", "혈압약", "감기약",
    "기침약", "당뇨약", "소화제", "보청기",
)
_MEDICAL_REQUESTS = (
    "어디", "찾아", "알려", "어느", "어떤", "전화번호", "먹어도", "같이 먹",
    "어떻게", "가야", "가도", "있을까", "있는 곳", "안전", "확인", "봐줘",
    "문의", "상담", "아픈데", "아파", "통증", "복용법", "문 여", "살 수",
    "얼마나 걸려", "근처", "주말에도", "일까",
)
_BARE_SPECIALTIES = (
    "정형외과", "이비인후과", "내과", "치과", "안과", "피부과", "소아과",
)


def is_medical_query(text: str) -> bool:
    """의료(병원/약국/의약품) 관련 질문인지 판단한다."""
    normalized = (text or "").strip().replace("약속", "")
    if not normalized:
        return False
    if normalized in _BARE_SPECIALTIES:
        return True
    has_topic = any(marker in normalized for marker in _MEDICAL_TOPICS)
    has_request = any(marker in normalized for marker in _MEDICAL_REQUESTS)
    return has_topic and has_request



# ---------------------------------------------------------------------------
# 날씨 의도 판단
# ---------------------------------------------------------------------------
# 아래 예시는 제거한 SentenceTransformer 라우터를 같은 조건으로 재평가하기 위해
# 남긴 스냅샷이다. 운영 판정은 _WEATHER_TOPICS/_WEATHER_REQUESTS만 사용한다.
WEATHER_EXAMPLES = [
    "오늘 날씨 어때", "오늘 날씨 알려줘", "지금 날씨 어때", "내일 날씨 어때",
    "서울 날씨 알려줘", "부산 날씨 어때", "오늘 부산 날씨 어때",
    "밖에 날씨 어때", "지금 밖에 어때",
    "오늘 비 와?", "비 올까?", "우산 챙겨야 해?",
    "밖에 추워?", "오늘 더워?", "기온 몇 도야", "오늘 하늘 어때",
]

WEATHER_THRESHOLD = 0.7

# ★ 주제 표지는 "날씨" 하나뿐이다 (2026-08-10 실사용 피드백)
#
#   원래는 "우산"·"기온"·"추워"·"빨래"·"소풍" 까지 주제로 봤다. 그 넓이가 실기에서
#   되돌아온 결과는 "묻지도 않았는데 기상 예보로 답한다" 였다 — "오늘 좀 춥네"
#   같은 평범한 잡담, "빨래 널었어" 같은 근황 보고가 전부 조회를 태우고, 조회된
#   예보는 참고 자료로 프롬프트에 실려 모델이 그 화제를 이어받는다.
#
#   그래서 판정을 한 단어로 좁힌다. 어르신이 "날씨"라고 말하지 않았으면 날씨로
#   답하지 않는다. 놓치는 쪽("우산 필요해?")은 모델이 참고 자료 없이 평범하게
#   답하면 그만이지만, 넘치는 쪽은 대화 전체의 화제를 뺏는다.
_WEATHER_TOPICS = ("날씨",)
_WEATHER_REQUESTS = (
    "알려", "어때", "올까", "쌓일까", "필요", "챙겨", "괜찮", "봐줘", "궁금",
    "몇 도", "많이 불어", "높아", "내려가", "열어도", "없어", "와", "추워",
    "더워", "더운지", "맑을까", "얼겠", "강하면", "?",
)


def is_weather_query(text: str) -> bool:
    """'날씨' 라는 말과 조회 의도가 함께 있는지 판정한다.

    주제 표지를 "날씨" 하나로 좁힌 이유는 _WEATHER_TOPICS 주석 참고. 조회 의도
    표지는 그대로 둔다 — "어제 날씨 참 좋았지" 같은 회상까지 기상청을 부를
    이유는 없기 때문이다.
    """
    normalized = (text or "").strip()
    if not normalized:
        return False
    has_topic = any(marker in normalized for marker in _WEATHER_TOPICS)
    has_request = any(marker in normalized for marker in _WEATHER_REQUESTS)
    return has_topic and has_request
