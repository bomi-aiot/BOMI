"""모델 확장자로 openWakeWord 추론 프레임워크를 고르는 로직 검증.

왜 이 테스트가 있는가 (2026-08-06 실기)
    openWakeWord 의 inference_framework 기본값이 버전에 따라 다르다. 젯슨에
    깔린 버전은 tflite 를 기본으로 잡아 우리 .onnx 모델을 거부하고 기동
    자체가 죽었다. 기본값에 기대지 않고 명시적으로 넘기는 것이 고침이며,
    이 테스트가 그 규칙을 지킨다.
"""

from __future__ import annotations

import pytest

from bomi_ai_chat.audio_io.wakeword import _inference_framework_for


@pytest.mark.parametrize(
    "path",
    [
        "models/bomi.onnx",
        "/abs/path/bomi_ya.onnx",
        "MODELS/BOMI.ONNX",  # 대소문자 무관
    ],
)
def test_onnx_model_selects_onnx(path: str) -> None:
    assert _inference_framework_for(path) == "onnx"


def test_tflite_model_selects_tflite() -> None:
    assert _inference_framework_for("models/bomi.tflite") == "tflite"


def test_unknown_suffix_falls_back_to_onnx() -> None:
    """우리가 실제로 쓰는 모델이 onnx 다 — 모르면 그쪽으로 건다."""
    assert _inference_framework_for("models/bomi.bin") == "onnx"
