# BOMI AI Vision 프로젝트의 개발 환경 구성과 코드 검증 명령을 정의한다.

PYTHON := python
PIP := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest
RUFF := $(PYTHON) -m ruff
MYPY := $(PYTHON) -m mypy

SOURCE_PATHS := src scripts tests
TYPE_CHECK_PATHS := src/bomi_vision scripts
UNIT_TEST_PATH := tests/unit
INTEGRATION_TEST_PATH := tests/integration

.PHONY: help check-env setup format format-check lint type-check check-docstrings test-unit test-integration test coverage check clean

help:
	@echo "BOMI AI Vision commands"
	@echo "  make check-env         Check the project virtual environment"
	@echo "  make setup             Install development packages"
	@echo "  make format            Fix and format code with Ruff"
	@echo "  make format-check      Check code formatting with Ruff"
	@echo "  make lint              Check code with Ruff"
	@echo "  make type-check        Check types with mypy"
	@echo "  make check-docstrings  Check Korean docstrings"
	@echo "  make test-unit         Run unit tests"
	@echo "  make test-integration  Run integration tests"
	@echo "  make test              Run all tests"
	@echo "  make coverage          Run tests with coverage"
	@echo "  make check             Run all code checks"
	@echo "  make clean             Remove local cache and build files"

check-env:
	@$(PYTHON) scripts/check_virtualenv.py
	@$(PYTHON) -c "import sys; print('Python path:', sys.executable)"
	@$(PIP) --version

setup: check-env
	@$(PIP) install --upgrade pip
	@$(PIP) install -e ".[dev]"

format: check-env
	@$(RUFF) check $(SOURCE_PATHS) --fix
	@$(RUFF) format $(SOURCE_PATHS)

format-check: check-env
	@$(RUFF) format $(SOURCE_PATHS) --check

lint: check-env
	@$(RUFF) check $(SOURCE_PATHS)

type-check: check-env
	@$(MYPY) $(TYPE_CHECK_PATHS)

check-docstrings: check-env
	@$(PYTHON) scripts/check_korean_docstrings.py

test-unit: check-env
	@$(PYTEST) $(UNIT_TEST_PATH) -m unit

# 초기 구조에는 통합 테스트가 없으므로 pytest의 수집 대상 없음(exit 5)만 허용한다.
test-integration: check-env
	@$(PYTHON) -c "import subprocess, sys; result = subprocess.run([sys.executable, '-m', 'pytest', '$(INTEGRATION_TEST_PATH)', '-m', 'integration'], check=False); sys.exit(0 if result.returncode in (0, 5) else result.returncode)"

test: check-env
	@$(PYTEST) tests

coverage: check-env
	@$(PYTEST) tests \
		--cov=bomi_vision \
		--cov-branch \
		--cov-report=term-missing \
		--cov-report=html

check: check-env format-check lint type-check check-docstrings test

clean:
	@$(PYTHON) -c "from pathlib import Path; import shutil; targets = ['.pytest_cache', '.mypy_cache', '.ruff_cache', 'htmlcov', 'build', 'dist']; [shutil.rmtree(path, ignore_errors=True) for path in targets]; [shutil.rmtree(path, ignore_errors=True) for path in Path('.').rglob('__pycache__')]; [path.unlink(missing_ok=True) for path in Path('.').glob('.coverage*')]; print('Removed local cache and build files.')"
