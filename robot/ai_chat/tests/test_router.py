"""의료·날씨 결정 규칙과 제거한 모델의 회귀 평가 경계를 고정한다."""

import json
import sys
from pathlib import Path

from bomi_ai_chat.llm import router


def _cases() -> list[dict]:
    path = Path(__file__).parents[1] / "evals" / "router_cases.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_runtime_router_passes_the_fixed_korean_evaluation_set():
    predictions = []
    for case in _cases():
        if router.is_medical_query(case["text"]):
            predictions.append("medical")
        elif router.is_weather_query(case["text"]):
            predictions.append("weather")
        else:
            predictions.append("other")

    assert predictions == [case["label"] for case in _cases()]


def test_importing_runtime_router_does_not_load_sentence_transformers():
    assert "sentence_transformers" not in sys.modules


def test_topic_words_without_lookup_intent_do_not_trigger_external_search():
    assert router.is_medical_query("병원에서 돌아왔어") is False
    assert router.is_weather_query("우산을 현관에 놓았어") is False
    assert router.is_medical_query("근처 정형외과 찾아줘") is True
    assert router.is_weather_query("산책 전에 겉옷을 챙겨야 할까") is True
