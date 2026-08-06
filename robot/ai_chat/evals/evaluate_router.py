"""로컬 SentenceTransformer 라우터와 단순 키워드 기준선을 재현 가능하게 비교한다."""

from __future__ import annotations

import argparse
import ctypes
import importlib
import json
import math
import os
import statistics
import time
from ctypes import wintypes
from pathlib import Path

LABELS = ("medical", "weather", "other")
MEDICAL_MARKERS = (
    "병원", "약국", "진료", "처방", "부작용", "복용", "응급실", "정형외과",
    "이비인후과", "내과", "치과", "안과", "타이레놀", "마데카솔", "겔포스",
)
WEATHER_MARKERS = (
    "날씨", "비", "우산", "기온", "추워", "더워", "눈", "바람", "습도",
    "하늘", "햇볕", "구름", "선선", "얼겠",
)


def _working_set_mb() -> float | None:
    """Windows 프로세스 working set. 다른 OS에서는 측정을 생략한다."""
    if os.name != "nt":
        return None

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    get_memory = psapi.GetProcessMemoryInfo
    get_memory.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    get_memory.restype = wintypes.BOOL
    ok = get_memory(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize / 1024 / 1024 if ok else None


def _keyword_label(text: str) -> str:
    if any(marker in text for marker in MEDICAL_MARKERS):
        return "medical"
    if any(marker in text for marker in WEATHER_MARKERS):
        return "weather"
    return "other"


def _metrics(cases: list[dict], predictions: list[str]) -> dict:
    correct = sum(case["label"] == prediction for case, prediction in zip(cases, predictions))
    by_class: dict[str, dict] = {}
    for label in LABELS:
        true_positive = sum(
            case["label"] == label and prediction == label
            for case, prediction in zip(cases, predictions)
        )
        false_positive = sum(
            case["label"] != label and prediction == label
            for case, prediction in zip(cases, predictions)
        )
        false_negative = sum(
            case["label"] == label and prediction != label
            for case, prediction in zip(cases, predictions)
        )
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        by_class[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
    errors = [
        {"text": case["text"], "expected": case["label"], "predicted": prediction}
        for case, prediction in zip(cases, predictions)
        if case["label"] != prediction
    ]
    return {
        "accuracy": round(correct / len(cases), 4),
        "macro_f1": round(statistics.mean(item["f1"] for item in by_class.values()), 4),
        "by_class": by_class,
        "errors": errors,
    }


def _latency(milliseconds: list[float]) -> dict:
    ordered = sorted(milliseconds)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "median_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[p95_index], 3),
        "max_ms": round(ordered[-1], 3),
    }


def _evaluate_classifier(cases: list[dict], medical_fn, weather_fn) -> tuple[list[str], dict]:
    medical_predictions: list[bool] = []
    medical_latencies: list[float] = []
    weather_predictions: list[bool] = []
    weather_latencies: list[float] = []
    for case in cases:
        started = time.perf_counter()
        medical_predictions.append(medical_fn(case["text"]))
        medical_latencies.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        weather_predictions.append(weather_fn(case["text"]))
        weather_latencies.append((time.perf_counter() - started) * 1000)

    predictions = [
        "medical" if medical else "weather" if weather else "other"
        for medical, weather in zip(medical_predictions, weather_predictions)
    ]
    return predictions, {
        "medical": _latency(medical_latencies),
        "weather": _latency(weather_latencies),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).with_name("router_cases.json"),
    )
    parser.add_argument(
        "--legacy-model",
        action="store_true",
        help="선택 의존성 sentence-transformers로 제거 전 라우터도 함께 평가한다.",
    )
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))

    # 평가가 모델 다운로드를 유발하면 cold-start 수치와 운영 절차가 모두 거짓이 된다.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    rss_before = _working_set_mb()
    load_started = time.perf_counter()
    router = importlib.import_module("bomi_ai_chat.llm.router")
    import_seconds = time.perf_counter() - load_started
    rss_after = _working_set_mb()

    runtime_predictions, runtime_latencies = _evaluate_classifier(
        cases, router.is_medical_query, router.is_weather_query,
    )
    keyword_predictions = [_keyword_label(case["text"]) for case in cases]
    report = {
        "dataset": {"cases": len(cases), "labels": LABELS},
        "runtime_router": {
            "offline": True,
            "import_seconds": round(import_seconds, 6),
            "working_set_before_mb": round(rss_before, 1) if rss_before is not None else None,
            "working_set_after_mb": round(rss_after, 1) if rss_after is not None else None,
            "working_set_delta_mb": (
                round(rss_after - rss_before, 1)
                if rss_before is not None and rss_after is not None else None
            ),
            "latency": runtime_latencies,
            "metrics": _metrics(cases, runtime_predictions),
        },
        "keyword_baseline": _metrics(cases, keyword_predictions),
    }

    if args.legacy_model:
        legacy_rss_before = _working_set_mb()
        legacy_started = time.perf_counter()
        model = router._load_legacy_model()
        from sentence_transformers import util

        medical_embeddings = model.encode(router.MEDICAL_EXAMPLES, convert_to_tensor=True)
        weather_embeddings = model.encode(router.WEATHER_EXAMPLES, convert_to_tensor=True)
        legacy_initialization_seconds = time.perf_counter() - legacy_started
        legacy_rss_after = _working_set_mb()

        def legacy_medical(text: str) -> bool:
            embedding = model.encode(text, convert_to_tensor=True)
            return util.cos_sim(embedding, medical_embeddings).max().item() >= router.THRESHOLD

        def legacy_weather(text: str) -> bool:
            embedding = model.encode(text, convert_to_tensor=True)
            return (
                util.cos_sim(embedding, weather_embeddings).max().item()
                >= router.WEATHER_THRESHOLD
            )

        legacy_predictions, legacy_latencies = _evaluate_classifier(
            cases, legacy_medical, legacy_weather,
        )
        report["legacy_sentence_transformer"] = {
            "initialization_seconds": round(legacy_initialization_seconds, 3),
            "working_set_delta_mb": (
                round(legacy_rss_after - legacy_rss_before, 1)
                if legacy_rss_before is not None and legacy_rss_after is not None else None
            ),
            "latency": legacy_latencies,
            "metrics": _metrics(cases, legacy_predictions),
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
