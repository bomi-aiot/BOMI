"""의료·날씨 결정 규칙과 제거한 모델의 회귀 평가 경계를 고정한다."""

import json
import sys
from pathlib import Path

from bomi_ai_chat.llm import router


def _cases() -> list[dict]:
    path = Path(__file__).parents[1] / "evals" / "router_cases.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_runtime_router_passes_the_fixed_korean_evaluation_set():
    """운영 규칙의 기대값은 label 이 아니라 runtime_label 이다 (있을 때만).

    label 은 "사람이 보기에 무슨 주제인가"이고, 제거한 임베딩 라우터를 같은
    조건으로 재평가할 때 쓰는 값이라 그대로 둔다. runtime_label 은 "지금 규칙이
    조회를 열어야 하는가"이며, 2026-08-10 에 날씨 판정을 '날씨'라는 말이 있을
    때로 좁히면서 갈라졌다(router.py _WEATHER_TOPICS 주석). 즉 아래 18건은
    주제로는 날씨가 맞지만 일부러 조회하지 않는 발화다.
    """
    predictions = []
    for case in _cases():
        if router.is_medical_query(case["text"]):
            predictions.append("medical")
        elif router.is_weather_query(case["text"]):
            predictions.append("weather")
        else:
            predictions.append("other")

    expected = [case.get("runtime_label", case["label"]) for case in _cases()]
    assert predictions == expected


def test_importing_runtime_router_does_not_load_sentence_transformers():
    assert "sentence_transformers" not in sys.modules


def test_topic_words_without_lookup_intent_do_not_trigger_external_search():
    assert router.is_medical_query("병원에서 돌아왔어") is False
    assert router.is_weather_query("어제 날씨 참 좋았지") is False
    assert router.is_medical_query("근처 정형외과 찾아줘") is True
    assert router.is_weather_query("오늘 날씨 어때") is True


def test_weather_lookup_needs_the_word_weather():
    """'날씨'가 없으면 조회하지 않는다 (2026-08-10 실사용 피드백).

    날씨성 화제이긴 해도 어르신이 묻지 않은 발화들이다. 여기서 조회를 열면
    예보가 참고 자료로 프롬프트에 실리고, 모델이 그 화제를 이어받는다.
    """
    for text in ("우산을 현관에 놓았어", "산책 전에 겉옷을 챙겨야 할까",
                 "지금 밖에 많이 추워", "오늘 낮 기온이 몇 도야"):
        assert router.is_weather_query(text) is False, text
