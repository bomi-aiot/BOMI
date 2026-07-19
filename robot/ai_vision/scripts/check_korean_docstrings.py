"""프로젝트의 Python 코드에 한국어 docstring이 작성됐는지 검사한다.

src, scripts, tests 디렉터리의 Python 파일을 AST로 분석해 모듈,
클래스, 공개 함수, 공개 메서드 및 테스트 함수의 docstring 존재 여부와
한글 포함 여부를 확인한다.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import re

KOREAN_PATTERN = re.compile(r"[ㄱ-ㅎㅏ-ㅣ가-힣]")

DEFAULT_TARGET_DIRECTORIES = (
    "src",
    "scripts",
    "tests",
)

EXCLUDED_DIRECTORY_NAMES = {
    "__pycache__",
    "venv",
    ".venv",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
}

EXCLUDED_SPECIAL_METHODS = {
    "__init__",
    "__repr__",
    "__str__",
    "__enter__",
    "__exit__",
}

TEST_FUNCTION_PREFIX = "test_"


@dataclass(frozen=True)
class DocstringViolation:
    """docstring 규칙 위반 정보를 표현한다."""

    file_path: Path
    line_number: int
    target_type: str
    target_name: str
    reason: str

    def format_message(self, project_root: Path) -> str:
        """위반 정보를 터미널 출력용 문자열로 변환한다.

        Args:
            project_root: 상대경로 계산에 사용할 프로젝트 루트.

        Returns:
            파일 경로와 위반 이유가 포함된 문자열.
        """
        try:
            relative_path = self.file_path.relative_to(project_root)
        except ValueError:
            relative_path = self.file_path

        target_description = self.target_type

        if self.target_name:
            target_description += f" '{self.target_name}'"

        return f"{relative_path}:{self.line_number} {target_description}의 {self.reason}"


def contains_korean(text: str) -> bool:
    """문자열에 한글 문자가 포함돼 있는지 확인한다.

    Args:
        text: 검사할 문자열.

    Returns:
        한글 음절 또는 한글 자모가 하나 이상 있으면 True.
    """
    return KOREAN_PATTERN.search(text) is not None


def is_private_name(name: str) -> bool:
    """이름이 비공개 함수나 메서드 형식인지 확인한다.

    Args:
        name: 검사할 함수 또는 메서드 이름.

    Returns:
        밑줄 하나로 시작하는 비공개 이름이면 True.
    """
    return name.startswith("_") and not name.startswith("__")


def is_excluded_special_method(name: str) -> bool:
    """Docstring 검사에서 제외할 특수 메서드인지 확인한다.

    Args:
        name: 검사할 메서드 이름.

    Returns:
        검사 제외 대상 특수 메서드이면 True.
    """
    return name in EXCLUDED_SPECIAL_METHODS


def is_test_function(name: str) -> bool:
    """Pytest 테스트 함수 이름인지 확인한다.

    Args:
        name: 검사할 함수 이름.

    Returns:
        이름이 test_로 시작하면 True.
    """
    return name.startswith(TEST_FUNCTION_PREFIX)


def create_violation(
    file_path: Path,
    node: ast.AST,
    target_type: str,
    target_name: str,
    reason: str,
) -> DocstringViolation:
    """AST 노드 정보를 이용해 docstring 위반 객체를 생성한다.

    Args:
        file_path: 위반이 발생한 Python 파일 경로.
        node: 위반 대상 AST 노드.
        target_type: 모듈, 클래스, 함수 등의 대상 종류.
        target_name: 위반 대상의 이름.
        reason: 위반 사유.

    Returns:
        생성된 docstring 위반 객체.
    """
    return DocstringViolation(
        file_path=file_path,
        line_number=getattr(node, "lineno", 1),
        target_type=target_type,
        target_name=target_name,
        reason=reason,
    )


DocstringNode = ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


def validate_docstring(
    file_path: Path,
    node: DocstringNode,
    target_type: str,
    target_name: str,
) -> list[DocstringViolation]:
    """AST 노드의 docstring 존재 여부와 한글 포함 여부를 검사한다.

    Args:
        file_path: 검사 중인 Python 파일 경로.
        node: docstring을 검사할 AST 노드.
        target_type: 모듈, 클래스, 함수 등의 대상 종류.
        target_name: 검사 대상의 이름.

    Returns:
        발견된 docstring 위반 목록.
    """
    docstring = ast.get_docstring(node, clean=False)

    if docstring is None:
        return [
            create_violation(
                file_path=file_path,
                node=node,
                target_type=target_type,
                target_name=target_name,
                reason="docstring이 없습니다.",
            )
        ]

    if not contains_korean(docstring):
        return [
            create_violation(
                file_path=file_path,
                node=node,
                target_type=target_type,
                target_name=target_name,
                reason="docstring에 한글이 없습니다.",
            )
        ]

    return []


def should_check_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    inside_class: bool,
) -> bool:
    """함수 또는 메서드가 docstring 검사 대상인지 판단한다.

    Args:
        node: 검사할 함수 또는 비동기 함수 노드.
        inside_class: 클래스 내부 메서드인지 여부.

    Returns:
        docstring 검사 대상이면 True.
    """
    name = node.name

    if is_test_function(name):
        return True

    if is_private_name(name):
        return False

    return not (inside_class and is_excluded_special_method(name))


class DocstringVisitor(ast.NodeVisitor):
    """Python AST를 순회하며 docstring 규칙 위반을 수집한다."""

    def __init__(self, file_path: Path) -> None:
        """Docstring 검사 방문자를 초기화한다.

        Args:
            file_path: 현재 검사 중인 Python 파일 경로.
        """
        self.file_path = file_path
        self.violations: list[DocstringViolation] = []
        self._class_depth = 0

    def visit_Module(self, node: ast.Module) -> None:
        """모듈 docstring을 검사하고 하위 노드를 순회한다.

        Args:
            node: 검사할 모듈 AST 노드.
        """
        self.violations.extend(
            validate_docstring(
                file_path=self.file_path,
                node=node,
                target_type="모듈",
                target_name="",
            )
        )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """클래스 docstring을 검사하고 클래스 내부를 순회한다.

        Args:
            node: 검사할 클래스 AST 노드.
        """
        self.violations.extend(
            validate_docstring(
                file_path=self.file_path,
                node=node,
                target_type="클래스",
                target_name=node.name,
            )
        )

        self._class_depth += 1
        self.generic_visit(node)
        self._class_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """일반 함수 또는 메서드의 docstring을 검사한다.

        Args:
            node: 검사할 함수 AST 노드.
        """
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """비동기 함수 또는 메서드의 docstring을 검사한다.

        Args:
            node: 검사할 비동기 함수 AST 노드.
        """
        self._visit_function(node)

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        """함수 종류에 공통으로 적용되는 docstring 검사를 수행한다.

        Args:
            node: 검사할 함수 또는 비동기 함수 AST 노드.
        """
        inside_class = self._class_depth > 0

        if should_check_function(node, inside_class):
            if is_test_function(node.name):
                target_type = "테스트 함수"
            elif inside_class:
                target_type = "메서드"
            else:
                target_type = "함수"

            self.violations.extend(
                validate_docstring(
                    file_path=self.file_path,
                    node=node,
                    target_type=target_type,
                    target_name=node.name,
                )
            )

        self.generic_visit(node)


def parse_python_file(file_path: Path) -> ast.Module:
    """Python 파일을 읽어 AST 모듈로 변환한다.

    Args:
        file_path: 파싱할 Python 파일 경로.

    Returns:
        파싱된 Python AST 모듈.

    Raises:
        OSError: 파일을 읽을 수 없는 경우.
        SyntaxError: Python 문법 오류가 있는 경우.
    """
    source_code = file_path.read_text(encoding="utf-8")
    return ast.parse(source_code, filename=str(file_path))


def inspect_python_file(file_path: Path) -> list[DocstringViolation]:
    """하나의 Python 파일에서 docstring 규칙 위반을 찾는다.

    Args:
        file_path: 검사할 Python 파일 경로.

    Returns:
        발견된 docstring 위반 목록.
    """
    try:
        module = parse_python_file(file_path)
    except UnicodeDecodeError as error:
        return [
            DocstringViolation(
                file_path=file_path,
                line_number=1,
                target_type="파일",
                target_name=file_path.name,
                reason=f"UTF-8로 읽을 수 없습니다: {error}",
            )
        ]
    except OSError as error:
        return [
            DocstringViolation(
                file_path=file_path,
                line_number=1,
                target_type="파일",
                target_name=file_path.name,
                reason=f"파일을 읽을 수 없습니다: {error}",
            )
        ]
    except SyntaxError as error:
        return [
            DocstringViolation(
                file_path=file_path,
                line_number=error.lineno or 1,
                target_type="파일",
                target_name=file_path.name,
                reason=f"Python 문법 오류가 있습니다: {error.msg}",
            )
        ]

    visitor = DocstringVisitor(file_path)
    visitor.visit(module)
    return visitor.violations


def is_excluded_path(path: Path) -> bool:
    """검사에서 제외할 디렉터리에 포함된 경로인지 확인한다.

    Args:
        path: 검사 대상 경로.

    Returns:
        제외 대상 디렉터리에 포함돼 있으면 True.
    """
    return any(part in EXCLUDED_DIRECTORY_NAMES for part in path.parts)


def find_python_files(
    project_root: Path,
    target_directories: Iterable[str] = DEFAULT_TARGET_DIRECTORIES,
) -> list[Path]:
    """검사 대상 디렉터리에서 Python 파일을 찾는다.

    Args:
        project_root: 프로젝트 루트 경로.
        target_directories: 검사할 디렉터리 이름 목록.

    Returns:
        정렬된 Python 파일 경로 목록.
    """
    python_files: list[Path] = []

    for directory_name in target_directories:
        target_path = project_root / directory_name

        if not target_path.exists():
            continue

        for file_path in target_path.rglob("*.py"):
            relative_path = file_path.relative_to(project_root)

            if is_excluded_path(relative_path):
                continue

            python_files.append(file_path.resolve(strict=False))

    return sorted(python_files)


def find_project_root() -> Path:
    """현재 스크립트 위치를 기준으로 프로젝트 루트를 찾는다.

    Returns:
        프로젝트 루트의 절대경로.
    """
    script_path = Path(__file__).resolve(strict=False)
    return script_path.parent.parent


def inspect_project(
    project_root: Path,
    target_directories: Iterable[str] = DEFAULT_TARGET_DIRECTORIES,
) -> tuple[list[Path], list[DocstringViolation]]:
    """프로젝트의 Python 파일과 docstring 위반 사항을 검사한다.

    Args:
        project_root: 검사할 프로젝트 루트.
        target_directories: 검사 대상 디렉터리 이름 목록.

    Returns:
        검사한 파일 목록과 발견한 위반 목록.
    """
    python_files = find_python_files(
        project_root=project_root,
        target_directories=target_directories,
    )

    violations: list[DocstringViolation] = []

    for file_path in python_files:
        violations.extend(inspect_python_file(file_path))

    return python_files, violations


def print_violations(
    violations: Iterable[DocstringViolation],
    project_root: Path,
) -> None:
    """발견한 docstring 위반 사항을 터미널에 출력한다.

    Args:
        violations: 출력할 위반 목록.
        project_root: 상대경로 계산에 사용할 프로젝트 루트.
    """
    for violation in violations:
        print(violation.format_message(project_root))


def main() -> int:
    """프로젝트 docstring 검사를 실행하고 종료 코드를 반환한다.

    Returns:
        모든 검사를 통과하면 0, 위반이 있으면 1.
    """
    project_root = find_project_root()
    python_files, violations = inspect_project(project_root)

    if not python_files:
        print("검사할 Python 파일을 찾지 못했습니다.")
        print(f"프로젝트 루트: {project_root}")
        return 1

    print(f"Python 파일 {len(python_files)}개를 검사했습니다.")

    if violations:
        print(f"docstring 규칙 위반 {len(violations)}개를 발견했습니다.")
        print()
        print_violations(violations, project_root)
        return 1

    print("모든 Python 파일이 한국어 docstring 규칙을 통과했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
