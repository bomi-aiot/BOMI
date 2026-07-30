"""패키지 소유권과 운영 문서가 현재 런타임에서 벗어나지 않게 한다."""

import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_NAME_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*)=", flags=re.MULTILINE)


def test_unused_medical_ingestion_code_is_not_packaged():
    api_directory = PROJECT_ROOT / "src" / "bomi_ai_chat" / "apis"
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert not api_directory.exists()
    assert "xmltodict" not in pyproject
    assert "HIRA_HOSPITAL_API_KEY" not in env_example
    assert "HIRA_PHARMACY_API_KEY" not in env_example
    assert "DUR_PRDLST_API_KEY" not in env_example


def test_env_example_covers_every_runtime_setting():
    config_path = PROJECT_ROOT / "src" / "bomi_ai_chat" / "config.py"
    config_tree = ast.parse(
        config_path.read_text(encoding="utf-8"),
        filename=str(config_path),
    )
    config_variables = {
        node.args[0].value
        for node in ast.walk(config_tree)
        if isinstance(node, ast.Call)
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and (
            (
                isinstance(node.func, ast.Name)
                and node.func.id.endswith("_env")
            )
            or (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "getenv"
            )
        )
    }
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    documented_variables = set(ENV_NAME_PATTERN.findall(env_example))

    assert documented_variables == config_variables


def test_readme_describes_current_runtime_and_entrypoints():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "현재 런타임은 Gemini 단일 API 체제" in readme
    assert "ollama pull" not in readme
    assert "localhost:11434" not in readme
    assert "python -m bomi_ai_chat --once" in readme
    assert "python -m bomi_ai_chat" in readme
    assert "AUDIO_MODE" in readme
    assert "### MVP" in readme
    assert "### FUTURE" in readme


def test_manual_guide_only_lists_existing_smoke_scripts():
    manual_directory = PROJECT_ROOT / "tests" / "manual"
    manual_readme = (manual_directory / "README.md").read_text(
        encoding="utf-8"
    )

    documented_scripts = {
        line.removeprefix("python tests/manual/").strip()
        for line in manual_readme.splitlines()
        if line.startswith("python tests/manual/") and line.endswith(".py")
    }
    existing_scripts = {
        path.name
        for path in manual_directory.glob("*_smoke.py")
    }

    assert documented_scripts == existing_scripts
