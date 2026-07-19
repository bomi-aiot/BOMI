"""프로젝트 가상환경 검사 로직의 정상 및 실패 상황을 검증한다."""

import os
from pathlib import Path

import pytest
from scripts.check_virtualenv import check_virtualenv, is_path_inside

pytestmark = pytest.mark.unit


def create_project_with_venv(tmp_path: Path) -> tuple[Path, Path]:
    """테스트용 프로젝트 루트와 venv 디렉터리를 생성한다.

    Args:
        tmp_path: pytest가 제공하는 임시 디렉터리.

    Returns:
        프로젝트 루트와 가상환경 경로를 담은 튜플.
    """
    project_root = tmp_path / "bomi-ai-vision"
    virtualenv_path = project_root / "venv"

    virtualenv_path.mkdir(parents=True)

    return project_root, virtualenv_path


def create_python_executable_path(virtualenv_path: Path) -> Path:
    """현재 운영체제 형식에 맞는 가상환경 Python 경로를 생성한다.

    Args:
        virtualenv_path: 테스트용 가상환경 경로.

    Returns:
        운영체제에 맞게 구성한 Python 실행 파일 경로.
    """
    if os.name == "nt":
        return virtualenv_path / "Scripts" / "python.exe"

    return virtualenv_path / "bin" / "python"


def test_valid_project_virtualenv_passes(tmp_path: Path) -> None:
    """현재 Python과 prefix가 프로젝트 venv 내부이면 검사를 통과한다."""
    project_root, virtualenv_path = create_project_with_venv(tmp_path)
    python_executable = create_python_executable_path(virtualenv_path)

    result = check_virtualenv(
        project_root=project_root,
        python_executable=python_executable,
        current_prefix=virtualenv_path,
        base_prefix=tmp_path / "system-python",
    )

    assert result.is_valid is True
    assert result.reason == "프로젝트의 venv 가상환경 사용이 확인됐습니다."
    assert result.expected_virtualenv_path == virtualenv_path.resolve()


def test_system_python_fails(tmp_path: Path) -> None:
    """현재 prefix와 base prefix가 같으면 시스템 Python으로 판단한다."""
    project_root, _ = create_project_with_venv(tmp_path)
    system_prefix = tmp_path / "system-python"
    python_executable = system_prefix / "python.exe"

    result = check_virtualenv(
        project_root=project_root,
        python_executable=python_executable,
        current_prefix=system_prefix,
        base_prefix=system_prefix,
    )

    assert result.is_valid is False
    assert "시스템 환경" in result.reason


def test_other_virtualenv_fails(tmp_path: Path) -> None:
    """다른 프로젝트의 가상환경을 사용하면 검사를 실패한다."""
    project_root, _ = create_project_with_venv(tmp_path)
    other_virtualenv = tmp_path / "other-project" / "venv"
    other_virtualenv.mkdir(parents=True)

    python_executable = create_python_executable_path(other_virtualenv)

    result = check_virtualenv(
        project_root=project_root,
        python_executable=python_executable,
        current_prefix=other_virtualenv,
        base_prefix=tmp_path / "system-python",
    )

    assert result.is_valid is False
    assert "Python 실행 파일" in result.reason


def test_missing_project_virtualenv_fails(tmp_path: Path) -> None:
    """프로젝트 루트에 venv 디렉터리가 없으면 검사를 실패한다."""
    project_root = tmp_path / "bomi-ai-vision"
    project_root.mkdir()

    missing_virtualenv = project_root / "venv"

    result = check_virtualenv(
        project_root=project_root,
        python_executable=create_python_executable_path(missing_virtualenv),
        current_prefix=missing_virtualenv,
        base_prefix=tmp_path / "system-python",
    )

    assert result.is_valid is False
    assert "venv 디렉터리를 찾지 못했습니다" in result.reason


def test_python_inside_venv_but_prefix_outside_fails(tmp_path: Path) -> None:
    """실행 파일만 venv 내부이고 prefix가 외부이면 검사를 실패한다."""
    project_root, virtualenv_path = create_project_with_venv(tmp_path)
    python_executable = create_python_executable_path(virtualenv_path)
    other_prefix = tmp_path / "other-environment"

    result = check_virtualenv(
        project_root=project_root,
        python_executable=python_executable,
        current_prefix=other_prefix,
        base_prefix=tmp_path / "system-python",
    )

    assert result.is_valid is False
    assert "Python prefix" in result.reason


def test_similarly_named_directory_is_not_inside_venv(tmp_path: Path) -> None:
    """venv-old처럼 이름만 비슷한 디렉터리를 venv 내부로 판단하지 않는다."""
    project_root, virtualenv_path = create_project_with_venv(tmp_path)
    similar_path = project_root / "venv-old" / "Scripts" / "python.exe"

    assert is_path_inside(similar_path, virtualenv_path) is False


def test_child_path_is_inside_venv(tmp_path: Path) -> None:
    """가상환경의 하위 경로는 venv 내부 경로로 판단한다."""
    _, virtualenv_path = create_project_with_venv(tmp_path)
    child_path = create_python_executable_path(virtualenv_path)

    assert is_path_inside(child_path, virtualenv_path) is True


def test_venv_root_is_considered_inside_itself(tmp_path: Path) -> None:
    """Venv 루트 경로 자체도 venv 내부 경로로 판단한다."""
    _, virtualenv_path = create_project_with_venv(tmp_path)

    assert is_path_inside(virtualenv_path, virtualenv_path) is True
