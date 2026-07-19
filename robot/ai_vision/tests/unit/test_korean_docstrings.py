"""한국어 docstring 검사 스크립트의 주요 동작을 검증한다."""

from pathlib import Path

import pytest
from scripts.check_korean_docstrings import (
    contains_korean,
    find_python_files,
    inspect_python_file,
)

pytestmark = pytest.mark.unit


def _write_python_file(
    tmp_path: Path,
    source_code: str,
    file_name: str = "sample.py",
) -> Path:
    """테스트용 Python 파일을 생성한다."""
    file_path = tmp_path / file_name
    file_path.write_text(source_code, encoding="utf-8")
    return file_path


def test_contains_korean_returns_true_for_korean_text() -> None:
    """한글이 포함된 문자열을 올바르게 인식하는지 확인한다."""
    assert contains_korean("사용자 상태를 확인한다.") is True


def test_contains_korean_returns_false_for_english_text() -> None:
    """영어만 포함된 문자열은 한글로 판단하지 않는지 확인한다."""
    assert contains_korean("Check the user state.") is False


def test_valid_module_docstring_passes(tmp_path: Path) -> None:
    """한국어 모듈 docstring이 있는 파일은 검사를 통과한다."""
    file_path = _write_python_file(
        tmp_path,
        '''"""테스트용 Python 모듈이다."""\n''',
    )

    violations = inspect_python_file(file_path)

    assert violations == []


def test_missing_module_docstring_fails(tmp_path: Path) -> None:
    """모듈 docstring이 없으면 위반 사항이 생성되는지 확인한다."""
    file_path = _write_python_file(
        tmp_path,
        "VALUE = 1\n",
    )

    violations = inspect_python_file(file_path)

    assert len(violations) == 1
    assert violations[0].target_type == "모듈"
    assert violations[0].reason == "docstring이 없습니다."


def test_english_module_docstring_fails(tmp_path: Path) -> None:
    """영어로만 작성된 모듈 docstring이 실패하는지 확인한다."""
    file_path = _write_python_file(
        tmp_path,
        '''"""This is a sample module."""\n''',
    )

    violations = inspect_python_file(file_path)

    assert len(violations) == 1
    assert violations[0].target_type == "모듈"
    assert violations[0].reason == "docstring에 한글이 없습니다."


def test_valid_class_docstring_passes(tmp_path: Path) -> None:
    """한국어 클래스 docstring이 있으면 검사를 통과한다."""
    file_path = _write_python_file(
        tmp_path,
        '''
"""테스트용 모듈이다."""


class Sample:
    """테스트에 사용하는 예시 클래스다."""
''',
    )

    violations = inspect_python_file(file_path)

    assert violations == []


def test_missing_class_docstring_fails(tmp_path: Path) -> None:
    """클래스 docstring이 없으면 위반 사항이 생성되는지 확인한다."""
    file_path = _write_python_file(
        tmp_path,
        '''
"""테스트용 모듈이다."""


class Sample:
    pass
''',
    )

    violations = inspect_python_file(file_path)

    assert len(violations) == 1
    assert violations[0].target_type == "클래스"
    assert violations[0].target_name == "Sample"
    assert violations[0].reason == "docstring이 없습니다."


def test_english_class_docstring_fails(tmp_path: Path) -> None:
    """영어로만 작성된 클래스 docstring이 실패하는지 확인한다."""
    file_path = _write_python_file(
        tmp_path,
        '''
"""테스트용 모듈이다."""


class Sample:
    """Sample class."""
''',
    )

    violations = inspect_python_file(file_path)

    assert len(violations) == 1
    assert violations[0].target_type == "클래스"
    assert violations[0].target_name == "Sample"
    assert violations[0].reason == "docstring에 한글이 없습니다."


def test_valid_public_function_docstring_passes(tmp_path: Path) -> None:
    """공개 함수에 한국어 docstring이 있으면 검사를 통과한다."""
    file_path = _write_python_file(
        tmp_path,
        '''
"""테스트용 모듈이다."""


def calculate_value() -> int:
    """테스트 값을 계산해 반환한다."""
    return 1
''',
    )

    violations = inspect_python_file(file_path)

    assert violations == []


def test_missing_public_function_docstring_fails(tmp_path: Path) -> None:
    """공개 함수에 docstring이 없으면 실패하는지 확인한다."""
    file_path = _write_python_file(
        tmp_path,
        '''
"""테스트용 모듈이다."""


def calculate_value() -> int:
    return 1
''',
    )

    violations = inspect_python_file(file_path)

    assert len(violations) == 1
    assert violations[0].target_type == "함수"
    assert violations[0].target_name == "calculate_value"
    assert violations[0].reason == "docstring이 없습니다."


def test_private_function_without_docstring_passes(tmp_path: Path) -> None:
    """비공개 함수는 docstring이 없어도 통과하는지 확인한다."""
    file_path = _write_python_file(
        tmp_path,
        '''
"""테스트용 모듈이다."""


def _calculate_internal_value() -> int:
    return 1
''',
    )

    violations = inspect_python_file(file_path)

    assert violations == []


def test_public_method_without_docstring_fails(tmp_path: Path) -> None:
    """공개 메서드에 docstring이 없으면 실패하는지 확인한다."""
    file_path = _write_python_file(
        tmp_path,
        '''
"""테스트용 모듈이다."""


class Sample:
    """테스트용 클래스다."""

    def calculate(self) -> int:
        return 1
''',
    )

    violations = inspect_python_file(file_path)

    assert len(violations) == 1
    assert violations[0].target_type == "메서드"
    assert violations[0].target_name == "calculate"
    assert violations[0].reason == "docstring이 없습니다."


def test_init_method_without_docstring_passes(tmp_path: Path) -> None:
    """검사 예외인 생성자는 docstring이 없어도 통과하는지 확인한다."""
    file_path = _write_python_file(
        tmp_path,
        '''
"""테스트용 모듈이다."""


class Sample:
    """테스트용 클래스다."""

    def __init__(self) -> None:
        self.value = 1
''',
    )

    violations = inspect_python_file(file_path)

    assert violations == []


def test_test_function_without_docstring_fails(tmp_path: Path) -> None:
    """테스트 함수에 docstring이 없으면 실패하는지 확인한다."""
    file_path = _write_python_file(
        tmp_path,
        '''
"""테스트용 모듈이다."""


def test_example() -> None:
    assert True
''',
    )

    violations = inspect_python_file(file_path)

    assert len(violations) == 1
    assert violations[0].target_type == "테스트 함수"
    assert violations[0].target_name == "test_example"
    assert violations[0].reason == "docstring이 없습니다."


def test_valid_async_function_docstring_passes(tmp_path: Path) -> None:
    """비동기 공개 함수의 한국어 docstring을 검사하는지 확인한다."""
    file_path = _write_python_file(
        tmp_path,
        '''
"""테스트용 모듈이다."""


async def load_data() -> None:
    """비동기 방식으로 데이터를 불러온다."""
''',
    )

    violations = inspect_python_file(file_path)

    assert violations == []


def test_syntax_error_is_reported(tmp_path: Path) -> None:
    """Python 문법 오류를 위반 사항으로 반환하는지 확인한다."""
    file_path = _write_python_file(
        tmp_path,
        '''
"""테스트용 모듈이다."""


def broken_function(
''',
    )

    violations = inspect_python_file(file_path)

    assert len(violations) == 1
    assert violations[0].target_type == "파일"
    assert "Python 문법 오류" in violations[0].reason


def test_find_python_files_returns_only_python_files(tmp_path: Path) -> None:
    """검사 대상 디렉터리의 Python 파일만 찾는지 확인한다."""
    source_directory = tmp_path / "src"
    source_directory.mkdir()

    python_file = source_directory / "sample.py"
    python_file.write_text(
        '"""테스트용 모듈이다."""\n',
        encoding="utf-8",
    )

    text_file = source_directory / "sample.txt"
    text_file.write_text(
        "Python 파일이 아니다.",
        encoding="utf-8",
    )

    python_files = find_python_files(
        project_root=tmp_path,
        target_directories=("src",),
    )

    assert python_files == [python_file.resolve()]


def test_find_python_files_excludes_venv_directory(tmp_path: Path) -> None:
    """Venv 내부의 Python 파일을 검사 대상에서 제외하는지 확인한다."""
    source_directory = tmp_path / "src"
    source_directory.mkdir()

    normal_file = source_directory / "normal.py"
    normal_file.write_text(
        '"""검사 대상 모듈이다."""\n',
        encoding="utf-8",
    )

    virtualenv_directory = source_directory / "venv"
    virtualenv_directory.mkdir()

    excluded_file = virtualenv_directory / "excluded.py"
    excluded_file.write_text(
        '"""검사에서 제외할 모듈이다."""\n',
        encoding="utf-8",
    )

    python_files = find_python_files(
        project_root=tmp_path,
        target_directories=("src",),
    )

    assert python_files == [normal_file.resolve()]
