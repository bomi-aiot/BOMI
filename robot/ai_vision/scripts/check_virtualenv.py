"""현재 Python이 프로젝트의 venv 가상환경에서 실행되는지 검사하는 스크립트다.

프로젝트 루트의 venv 디렉터리와 현재 Python 실행 경로를 비교해
시스템 Python이나 다른 프로젝트의 가상환경 사용을 방지한다.

검사에 성공하면 종료 코드 0을 반환하고, 실패하면 활성화 방법을 안내한 뒤
종료 코드 1을 반환한다.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys

VIRTUALENV_DIRECTORY_NAME = "venv"


@dataclass(frozen=True)
class VirtualenvCheckResult:
    """가상환경 검사 결과를 표현한다."""

    is_valid: bool
    project_root: Path
    expected_virtualenv_path: Path
    python_executable: Path
    current_prefix: Path
    base_prefix: Path
    reason: str


def normalize_path(path: Path) -> str:
    """운영체제 차이를 고려한 경로 비교용 문자열을 생성한다.

    Args:
        path: 정규화할 경로.

    Returns:
        절대경로와 운영체제별 대소문자 규칙을 적용한 문자열.
    """
    resolved_path = path.expanduser().resolve(strict=False)
    return os.path.normcase(str(resolved_path))


def is_path_inside(child_path: Path, parent_path: Path) -> bool:
    """대상 경로가 기준 경로 내부에 있는지 확인한다.

    Args:
        child_path: 내부 경로인지 확인할 대상.
        parent_path: 기준이 되는 상위 경로.

    Returns:
        대상 경로가 기준 경로와 같거나 내부에 있으면 True.
    """
    normalized_child = Path(normalize_path(child_path))
    normalized_parent = Path(normalize_path(parent_path))

    try:
        normalized_child.relative_to(normalized_parent)
    except ValueError:
        return False

    return True


def find_project_root() -> Path:
    """현재 스크립트의 위치를 기준으로 프로젝트 루트를 찾는다.

    Returns:
        프로젝트 루트의 절대경로.
    """
    script_path = Path(__file__).resolve(strict=False)
    return script_path.parent.parent


def check_virtualenv(
    project_root: Path,
    python_executable: Path,
    current_prefix: Path,
    base_prefix: Path,
) -> VirtualenvCheckResult:
    """현재 Python이 프로젝트의 venv를 사용하는지 검사한다.

    Args:
        project_root: 프로젝트 루트 경로.
        python_executable: 현재 Python 실행 파일 경로.
        current_prefix: 현재 Python 환경의 prefix.
        base_prefix: 기반 Python 환경의 prefix.

    Returns:
        성공 여부와 실패 이유를 포함한 검사 결과.
    """
    resolved_project_root = project_root.resolve(strict=False)
    expected_virtualenv_path = (resolved_project_root / VIRTUALENV_DIRECTORY_NAME).resolve(
        strict=False
    )

    resolved_python_executable = python_executable.resolve(strict=False)
    resolved_current_prefix = current_prefix.resolve(strict=False)
    resolved_base_prefix = base_prefix.resolve(strict=False)

    if not expected_virtualenv_path.is_dir():
        return VirtualenvCheckResult(
            is_valid=False,
            project_root=resolved_project_root,
            expected_virtualenv_path=expected_virtualenv_path,
            python_executable=resolved_python_executable,
            current_prefix=resolved_current_prefix,
            base_prefix=resolved_base_prefix,
            reason="프로젝트 루트에서 venv 디렉터리를 찾지 못했습니다.",
        )

    if normalize_path(resolved_current_prefix) == normalize_path(resolved_base_prefix):
        return VirtualenvCheckResult(
            is_valid=False,
            project_root=resolved_project_root,
            expected_virtualenv_path=expected_virtualenv_path,
            python_executable=resolved_python_executable,
            current_prefix=resolved_current_prefix,
            base_prefix=resolved_base_prefix,
            reason="현재 Python은 가상환경이 아닌 시스템 환경입니다.",
        )

    if not is_path_inside(
        resolved_python_executable,
        expected_virtualenv_path,
    ):
        return VirtualenvCheckResult(
            is_valid=False,
            project_root=resolved_project_root,
            expected_virtualenv_path=expected_virtualenv_path,
            python_executable=resolved_python_executable,
            current_prefix=resolved_current_prefix,
            base_prefix=resolved_base_prefix,
            reason=("현재 Python 실행 파일이 프로젝트의 venv 내부에 있지 않습니다."),
        )

    if not is_path_inside(
        resolved_current_prefix,
        expected_virtualenv_path,
    ):
        return VirtualenvCheckResult(
            is_valid=False,
            project_root=resolved_project_root,
            expected_virtualenv_path=expected_virtualenv_path,
            python_executable=resolved_python_executable,
            current_prefix=resolved_current_prefix,
            base_prefix=resolved_base_prefix,
            reason="현재 Python prefix가 프로젝트의 venv를 가리키지 않습니다.",
        )

    return VirtualenvCheckResult(
        is_valid=True,
        project_root=resolved_project_root,
        expected_virtualenv_path=expected_virtualenv_path,
        python_executable=resolved_python_executable,
        current_prefix=resolved_current_prefix,
        base_prefix=resolved_base_prefix,
        reason="프로젝트의 venv 가상환경 사용이 확인됐습니다.",
    )


def print_activation_guide() -> None:
    """운영체제별 가상환경 활성화 명령을 출력한다."""
    print()
    print("프로젝트 가상환경을 활성화한 뒤 다시 실행하세요.")
    print()
    print("Windows PowerShell:")
    print(r"  .\venv\Scripts\Activate.ps1")
    print()
    print("Windows Command Prompt:")
    print(r"  venv\Scripts\activate.bat")
    print()
    print("Linux 또는 Jetson:")
    print("  source venv/bin/activate")
    print()
    print("시스템 Python에는 프로젝트 패키지를 설치하지 마세요.")


def print_check_result(result: VirtualenvCheckResult) -> None:
    """가상환경 검사 결과를 출력한다.

    Args:
        result: 출력할 가상환경 검사 결과.
    """
    if result.is_valid:
        print("가상환경 확인이 완료되었습니다.")
    else:
        print("가상환경 확인에 실패했습니다.")

    print(f"판단 결과: {result.reason}")
    print(f"프로젝트 루트: {result.project_root}")
    print(f"예상 가상환경 경로: {result.expected_virtualenv_path}")
    print(f"Python 실행 경로: {result.python_executable}")
    print(f"현재 Python prefix: {result.current_prefix}")
    print(f"기반 Python prefix: {result.base_prefix}")


def main() -> int:
    """현재 Python 환경을 검사한다.

    Returns:
        프로젝트의 venv를 사용하면 0, 그렇지 않으면 1.
    """
    project_root = find_project_root()

    result = check_virtualenv(
        project_root=project_root,
        python_executable=Path(sys.executable),
        current_prefix=Path(sys.prefix),
        base_prefix=Path(sys.base_prefix),
    )

    print_check_result(result)

    if result.is_valid:
        return 0

    print_activation_guide()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
