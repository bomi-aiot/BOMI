"""기본 pytest 실행의 외부 연동 차단 기준선."""

import ast
import runpy
from pathlib import Path

import pytest
import requests

MANUAL_DIR = Path(__file__).parent / "manual"
EXPECTED_MANUAL_SCRIPTS = {
    "audio_smoke.py",
    "db_connection_smoke.py",
    "ec2_query_smoke.py",
    "llm_smoke.py",
    "medical_flow_smoke.py",
    "rtzr_token_smoke.py",
    "stt_smoke.py",
    "tts_smoke.py",
    "weather_smoke.py",
}


def _is_main_guard(node: ast.If) -> bool:
    comparison = node.test
    return (
        isinstance(comparison, ast.Compare)
        and isinstance(comparison.left, ast.Name)
        and comparison.left.id == "__name__"
        and len(comparison.ops) == 1
        and isinstance(comparison.ops[0], ast.Eq)
        and len(comparison.comparators) == 1
        and isinstance(comparison.comparators[0], ast.Constant)
        and comparison.comparators[0].value == "__main__"
    )


def test_external_http_is_blocked_by_default():
    with pytest.raises(AssertionError, match="외부 HTTP 요청"):
        requests.get("https://example.com")


def test_manual_scripts_are_explicit_and_main_guarded():
    scripts = {path.name for path in MANUAL_DIR.glob("*_smoke.py")}
    assert scripts == EXPECTED_MANUAL_SCRIPTS

    for path in sorted(MANUAL_DIR.glob("*_smoke.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        guards = [
            node
            for node in tree.body
            if isinstance(node, ast.If) and _is_main_guard(node)
        ]
        assert len(guards) == 1, f"{path.name}에는 단일 main guard가 필요합니다."

        unguarded_calls = [
            node
            for node in tree.body
            if isinstance(node, ast.Expr)
            and not (
                isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
        ]
        assert not unguarded_calls, f"{path.name}에 최상위 실행문이 있습니다."
        runpy.run_path(str(path), run_name="manual_import_check")
