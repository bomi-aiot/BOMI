"""BOMI AI Vision 패키지의 기본 import와 버전 정보를 검증한다."""

from pathlib import Path
import subprocess
import sys

import bomi_vision


def test_package_can_be_imported() -> None:
    """bomi_vision 패키지를 정상적으로 import할 수 있는지 확인한다."""
    assert bomi_vision is not None


def test_package_version() -> None:
    """패키지 버전이 pyproject.toml의 초기 버전과 일치하는지 확인한다."""
    assert bomi_vision.__version__ == "0.1.0"


def test_package_public_exports() -> None:
    """패키지가 현재 단계에서 버전 정보만 공개하는지 확인한다."""
    assert bomi_vision.__all__ == ["__version__"]


def test_installed_package_imports_outside_project_directory(tmp_path: Path) -> None:
    """프로젝트 외부 작업 디렉터리에서도 설치된 패키지를 import할 수 있어야 한다."""
    result = subprocess.run(
        [sys.executable, "-c", "import bomi_vision; print(bomi_vision.__version__)"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.1.0"
