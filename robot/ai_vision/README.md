# BOMI AI Vision

돌봄 로봇의 사람 탐지·추적과 사용자 상태 분석 결과를 외부 시스템에 제공하기 위한 Python 프로젝트다. AI 비전 모듈은 모터, TTS, 대화를 직접 실행하지 않는다.

## 현재 구현 범위

현재 노트북 카메라 영상에서 YOLO11과 ByteTrack으로 사람을 탐지·추적하고 Track ID, 바운딩 박스, 신뢰도와 화면 기준 위치를 표시할 수 있다. 사용자 상태 분석과 ROS2 연동은 아직 구현하지 않았다.

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

## 실시간 사람 추적

가상환경을 활성화한 뒤 개발 의존성을 포함해 설치한다.

```bash
python -m pip install -e ".[dev]"
```

프로젝트 표준 명령을 사용할 수도 있다.

```bash
make setup
```

기본 카메라와 설정으로 실행한다.

```bash
python -m bomi_vision.main
```

Windows Git Bash에서도 같은 명령을 사용하며 옵션은 한 줄로 지정할 수 있다.

```bash
python -m bomi_vision.main --model yolo11n.pt --camera 0 --confidence 0.5
```

처음 실행하면 Ultralytics가 모델 가중치를 내려받을 수 있으며 인터넷 연결이 필요하다. 운영체제에서 노트북 카메라 접근 권한도 허용해야 한다. 화면에 추적된 모든 사람의 Track ID, 박스와 신뢰도가 표시되며 `q` 키를 누르면 종료한다. 기본 카메라가 열리지 않으면 `--camera 1`처럼 다른 인덱스를 지정한다.

한 명의 사람이 탐지되면 바운딩 박스 중심을 기준으로 화면 내 위치를 계산한다. `offset_x`는 화면 왼쪽 -1.0, 중앙 0.0, 오른쪽 1.0을 의미하고 `offset_y`는 화면 위쪽 -1.0, 중앙 0.0, 아래쪽 1.0을 의미한다. `height_ratio`는 박스 높이가 화면 높이에서 차지하는 비율이며 실제 거리나 미터 단위 값이 아니다.

ByteTrack은 연속 프레임의 같은 객체에 Track ID를 유지한다. 이 ID는 현재 영상 흐름에서 객체를 구분하는 임시 값이며 실제 사용자 ID나 신원을 의미하지 않는다. 추적기나 모델을 다시 시작하거나 사람이 화면을 벗어났다가 돌아오면 달라질 수 있다.

한 명일 때만 대표 Track ID와 위치를 생성한다. 두 명 이상이면 `multiple_people` 상태를 표시하고 특정 사용자를 선택하지 않으며, 대표 Track ID와 위치도 제공하지 않는다. 추적 중인 사람이 잠시 누락되면 `temporarily_lost`를 표시하고 기본 3프레임을 초과해 계속 보이지 않으면 `not_found`로 전환한다. 허용 범위는 `--lost-tolerance-frames`로 조정할 수 있으며 오래된 사용자를 무기한 유지하지 않기 위한 값이다.

좌우 좌표는 미러 화면이 아닌 카메라에서 읽은 원본 프레임을 기준으로 한다. 원본 프레임의 왼쪽은 `offset_x < 0`, 중앙은 `offset_x ≈ 0`, 오른쪽은 `offset_x > 0`이다. 탐지, 위치 계산과 디버그 화면은 모두 좌우 반전하지 않은 같은 프레임을 사용한다.

### 문제 해결

- `Failed to open camera index 0.`이 표시되면 카메라 권한과 다른 프로그램의 카메라 사용 여부를 확인하고 `--camera 1`을 시도한다.
- 모델 다운로드가 실패하면 인터넷 연결과 방화벽을 확인한 뒤 다시 실행하거나 내려받은 모델 파일을 `--model`로 지정한다.
- 화면이 나타나지 않으면 데스크톱 GUI 환경에서 실행 중인지, `opencv-python`이 정상 설치됐는지 확인한다.
- 다른 카메라를 사용하려면 `--camera 1`, `--camera 2`처럼 운영체제에 등록된 인덱스를 지정한다.

## 주요 문서

- [아키텍처](ARCHITECTURE.md)
- [코드 작성 규칙](docs/code-style.md)
- [비전 요구사항](docs/vision-requirements.md)
- [상태 머신](docs/state-machine.md)
- [초기 구조 작업 기록](docs/plans/completed/project-scaffold.md)

## 후속 작업

다중 인물 확인·한 명 복귀 안정화 상태 머신, Re-ID와 사용자 상태 분석은 별도 이슈와 실행 계획에서 단계적으로 구현한다.
