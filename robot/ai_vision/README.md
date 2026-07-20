# BOMI AI Vision

돌봄 로봇의 사람 탐지·추적과 사용자 상태 분석 결과를 외부 시스템에 제공하기 위한 Python 프로젝트다. AI 비전 모듈은 모터, TTS, 대화를 직접 실행하지 않는다.

## 현재 구현 범위

현재는 AI 기능 구현 전의 프로젝트 초기 구조 단계다. Python 패키지, 개발 도구 설정, 가상환경 및 한국어 docstring 검사, 단위 테스트가 준비되어 있다. YOLO, ByteTrack, OpenCV, ROS2 기능은 아직 구현하지 않았다.

## 디렉터리 구조

```text
src/bomi_vision/   패키지 소스
scripts/           개발 환경 검사 도구
tests/unit/        단위 테스트
tests/integration/ 통합 테스트(후속 작업)
docs/              요구사항, 설계, 작업 계획
artifacts/         로컬 실행 산출물
```

## 빠른 시작

지원 Python 버전은 3.10 이상 3.13 미만이다. 저장소를 복제한 뒤 프로젝트 루트에서 `venv`를 최초 한 번 생성하고 활성화한다. 기존 `venv`가 있다면 삭제하거나 다시 만들지 않고 그대로 활성화한다.

Windows PowerShell:

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Git Bash:

```bash
py -3.12 -m venv venv
source venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Linux 또는 Jetson:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

설치 후 다음 명령으로 실제 패키지 import를 확인할 수 있다.

```bash
python -c "import bomi_vision; print(bomi_vision.__version__)"
```

## 개발 명령

활성화된 프로젝트 `venv`에서 실행한다.

```bash
make help
make check-env
make setup
make format
make format-check
make lint
make type-check
make check-docstrings
make test-unit
make test-integration
make test
make coverage
make check
make clean
```

GNU Make를 사용할 수 없는 Windows 환경에서는 Makefile에 표시된 `python -m ruff`, `python -m mypy`, `python -m pytest` 명령을 직접 실행할 수 있다. pytest는 editable install된 패키지를 검사하므로 테스트 전에 `python -m pip install -e ".[dev]"`가 필요하다.

## 주요 문서

- [아키텍처](ARCHITECTURE.md)
- [코드 작성 규칙](docs/code-style.md)
- [비전 요구사항](docs/vision-requirements.md)
- [상태 머신](docs/state-machine.md)
- [초기 구조 작업 기록](docs/plans/completed/project-scaffold.md)

## 후속 작업

사람 탐지, ByteTrack 추적, 사람 수 상태 머신 등 실제 AI 비전 기능은 별도 이슈와 실행 계획에서 단계적으로 구현한다.
