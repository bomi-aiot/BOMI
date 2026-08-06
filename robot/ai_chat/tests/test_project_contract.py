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


def _env_variables_read_by(path: Path) -> set[str]:
    """한 파일이 읽는 환경변수 이름들."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.args[0].value
        for node in ast.walk(tree)
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


def test_env_example_covers_every_runtime_setting():
    """.env.example 과 '실제로 읽는 환경변수'가 정확히 일치해야 한다.

    양방향인 것이 핵심이다.
      - 문서에만 있는 변수 -> 아무 일도 안 하는 설정을 사람들이 채운다
      - 코드만 읽는 변수  -> 배포할 때 아무도 그것을 채워야 하는지 모른다

    ★ 왜 config.py 만 보지 않는가 (S15P11E102-233)
        원래 이 검사는 config.py 만 훑었다. 그런데 audio_io/beam_control.py 가
        os.getenv 를 직접 쓴다(BEAM_FIX_ENABLED 등). 그래서 그 변수들을 .env.example
        에 적는 순간 "문서에만 있는 변수"로 잡혀 실패했다 — 문서가 맞고 검사가
        좁았던 것이다.

        패키지 전체를 훑는 쪽이 이 검사의 원래 의도에 맞다. 덤으로, config.py 밖에서
        환경변수를 읽는 새 코드가 생기면 문서화를 강제한다.

    주의사항
        CLAUDE.md §20 은 "환경변수는 config.py 에만"이라고 적는다. beam_control.py 는
        그 규칙에서 벗어나 있고, 옮기는 것은 별도 작업이다. 이 검사는 규칙 위반을
        눈감아 주는 것이 아니라, 위반이 있는 동안에도 '문서화'만은 강제한다.
    """
    package = PROJECT_ROOT / "src" / "bomi_ai_chat"
    read_variables: set[str] = set()
    for path in sorted(package.rglob("*.py")):
        read_variables |= _env_variables_read_by(path)

    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    documented_variables = set(ENV_NAME_PATTERN.findall(env_example))

    only_documented = documented_variables - read_variables
    only_read = read_variables - documented_variables

    assert not only_documented, (
        f".env.example 에만 있고 아무도 읽지 않는 변수: {sorted(only_documented)}. "
        "채워도 아무 일이 일어나지 않는 설정이다")
    assert not only_read, (
        f"코드가 읽는데 .env.example 에 없는 변수: {sorted(only_read)}. "
        "배포할 때 아무도 이것을 채워야 하는지 모른다")


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
