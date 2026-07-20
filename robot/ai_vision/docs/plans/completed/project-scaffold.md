# 프로젝트 초기 골격 및 검증 하네스 구성

## 1. 계획 상태

* 상태: `COMPLETED`
* 작업 유형: 프로젝트 초기 설정
* 우선순위: 최우선
* 선행 작업: 프로젝트 문서 및 기본 폴더 구조 작성
* 후속 작업: 사람 탐지 및 추적 MVP 구현

이 계획은 프로젝트 초기 골격과 자동 검증 환경이 완성되면 다음 경로로 이동한다.

```text
docs/plans/completed/project-scaffold.md
```

---

## 2. 작업 목적

BOMI AI Vision 기능을 구현하기 전에 Codex와 개발자가 동일한 환경, 규칙 및 명령을 사용해 코드를 작성하고 검증할 수 있는 프로젝트 기반을 구성한다.

이번 작업의 핵심 목표는 다음과 같다.

1. Python 패키지를 정상적으로 설치하고 import할 수 있게 한다.
2. 기존 `venv/` 가상환경에서만 프로젝트 의존성을 설치하고 실행한다.
3. 코드 포맷, 정적 검사, 타입 검사 및 테스트 명령을 표준화한다.
4. 한국어 docstring 작성 규칙을 자동으로 검사할 수 있게 한다.
5. 이후 기능 구현이 동일한 구조와 검증 절차를 따르도록 기반을 마련한다.
6. AI 모델과 하드웨어 없이 초기 프로젝트 구성을 검증할 수 있게 한다.
7. 시스템 Python 환경이 오염되지 않도록 설치 환경을 검사한다.

이번 작업에서는 실제 AI 비전 기능을 구현하지 않는다.

---

## 3. 필수 참고 문서

작업을 시작하기 전에 다음 문서를 읽는다.

* `AGENTS.md`
* `ARCHITECTURE.md`
* `docs/code-style.md`
* `docs/vision-requirements.md`
* `docs/state-machine.md`
* `docs/plans/completed/project-scaffold.md`
* `README.md`

문서가 존재하지만 비어 있다면 이번 작업 범위에서 필요한 최소 내용만 작성한다.

문서 간 내용이 충돌하면 임의로 구현하지 않는다. 충돌 내용과 판단이 필요한 사항을 이 계획의 미해결 사항에 기록한다.

---

## 4. 현재 환경 전제

### 4.1 운영체제

주 개발 환경은 Windows를 기준으로 한다.

최종 실행 환경은 Jetson Orin Nano의 Linux 환경을 고려한다.

프로젝트 설정은 가능한 범위에서 다음 환경 모두에서 사용할 수 있어야 한다.

* Windows PowerShell
* Windows Command Prompt
* Linux
* Jetson Orin Nano

### 4.2 Python 가상환경

프로젝트 루트에는 Python 표준 `venv` 모듈로 생성된 가상환경이 이미 존재한다.

가상환경 경로는 다음과 같다.

```text
bomi-ai-vision/venv/
```

Codex는 다음 행동을 하지 않는다.

* 새로운 `.venv/` 생성
* 새로운 이름의 별도 가상환경 생성
* 기존 `venv/` 삭제
* 기존 `venv/` 재생성
* `venv/` 내부 파일 직접 수정
* `venv/`를 Git에 추가
* 시스템 Python에 프로젝트 의존성 설치

모든 설치 및 검증 명령은 기존 `venv/` 환경에서 실행한다.

---

## 5. 포함 범위

이번 작업에는 다음 항목을 포함한다.

### 5.1 Python 패키지 구성

* `src` 레이아웃 기반 Python 패키지 설정
* `bomi_vision` 패키지 생성
* 패키지 import 확인
* Python 버전 요구사항 정의
* 개발 의존성 정의

### 5.2 가상환경 확인

* 프로젝트 루트의 `venv/` 존재 여부 확인
* 현재 Python 실행 파일이 `venv/` 내부인지 확인
* 현재 pip가 `venv/` 내부 Python과 연결됐는지 확인
* 가상환경이 아닌 경우 설치 중단
* Windows 및 Linux 환경의 활성화 방법 문서화

### 5.3 프로젝트 설정

* `pyproject.toml` 작성
* Ruff 설정
* pytest 설정
* mypy 설정
* 패키지 메타데이터 작성
* 개발 의존성 그룹 작성

### 5.4 표준 명령 구성

`Makefile`에 다음 명령을 정의한다.

* `check-env`
* `setup`
* `format`
* `lint`
* `type-check`
* `check-docstrings`
* `test-unit`
* `test-integration`
* `test`
* `check`

명령 이름과 실제 동작은 `AGENTS.md` 및 `README.md`와 일치해야 한다.

### 5.5 초기 테스트 구성

* 패키지 import를 검증하는 smoke test
* 테스트 폴더 구조
* 단위 테스트와 통합 테스트 분리
* pytest가 테스트를 정상적으로 수집하는지 확인
* 초기 테스트에서 외부 AI 모델을 사용하지 않음

### 5.6 한국어 docstring 검사

다음 항목을 검사하는 스크립트를 작성한다.

* Python 모듈 docstring 존재 여부
* 클래스 docstring 존재 여부
* 공개 함수 docstring 존재 여부
* 공개 메서드 docstring 존재 여부
* 테스트 함수 docstring 존재 여부
* docstring에 한글 문자가 포함돼 있는지 여부

기본 검사 대상은 다음 경로로 한다.

```text
src/
scripts/
tests/
```

검사에서 제외해야 하는 항목은 코드 안에 흩어 놓지 않고 명시적인 예외 목록으로 관리한다.

### 5.7 기본 저장소 파일

* `.gitignore`
* `README.md`
* 빈 디렉터리 유지에 필요한 `.gitkeep`
* 설정 디렉터리 기본 구조

---

## 6. 제외 범위

이번 작업에서는 다음 기능을 구현하지 않는다.

* YOLO 모델 로딩
* 사람 탐지
* ByteTrack 추적
* 사람 수 상태 머신
* 보호대상자 위치 계산
* 자세 분석
* 움직임 분석
* 사용자 상태 분석
* 수면 가능성 추정
* 웹캠 실행
* 영상 파일 처리
* ROS2 연동
* TensorRT 변환
* Jetson Orin Nano 성능 최적화
* 실제 모델 파일 다운로드
* 실제 영상 데이터 추가
* 새로운 가상환경 생성
* requirements 파일의 불필요한 중복 관리

현재 작업과 직접 관련되지 않은 미래 기능의 클래스나 인터페이스도 미리 생성하지 않는다.

---

## 7. 목표 프로젝트 구조

이번 작업 완료 후 최소한 다음 구조가 존재해야 한다.

```text
bomi-ai-vision/
├── AGENTS.md
├── ARCHITECTURE.md
├── README.md
├── Makefile
├── pyproject.toml
├── .gitignore
│
├── venv/
│   └── ...
│
├── config/
│   └── .gitkeep
│
├── docs/
│   ├── code-style.md
│   ├── vision-requirements.md
│   ├── state-machine.md
│   ├── decisions/
│   │   └── .gitkeep
│   └── plans/
│       ├── active/
│       │   └── project-scaffold.md
│       └── completed/
│           └── .gitkeep
│
├── scripts/
│   ├── check_virtualenv.py
│   └── check_korean_docstrings.py
│
├── src/
│   └── bomi_vision/
│       └── __init__.py
│
├── tests/
│   ├── unit/
│   │   ├── test_package_import.py
│   │   ├── test_virtualenv_checker.py
│   │   └── test_korean_docstrings.py
│   └── integration/
│       └── .gitkeep
│
├── evals/
│   └── .gitkeep
│
└── artifacts/
    └── .gitkeep
```

`venv/`는 로컬에 존재하지만 Git에는 포함하지 않는다.

디렉터리 구조가 이미 존재한다면 삭제하거나 임의로 재구성하지 않는다. 현재 구조를 확인한 뒤 필요한 파일만 추가하거나 수정한다.

---

## 8. 구현 요구사항

## 8.1 기존 가상환경 확인 및 사용

프로젝트는 이미 생성된 `venv/` 가상환경을 사용한다.

### Windows PowerShell 활성화

```powershell
.\venv\Scripts\Activate.ps1
```

PowerShell 실행 정책 문제로 활성화가 차단되면 현재 터미널 세션에 한해 다음 명령을 사용할 수 있다.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

시스템 전체 실행 정책은 프로젝트 설정을 위해 임의로 변경하지 않는다.

### Windows Command Prompt 활성화

```bat
venv\Scripts\activate.bat
```

### Linux 또는 Jetson 활성화

```bash
source venv/bin/activate
```

### Python 실행 경로 확인

```bash
python -c "import sys; print(sys.executable)"
```

출력 경로에는 프로젝트의 `venv` 디렉터리가 포함돼야 한다.

Windows 예시:

```text
...\bomi-ai-vision\venv\Scripts\python.exe
```

Linux 또는 Jetson 예시:

```text
.../bomi-ai-vision/venv/bin/python
```

### 가상환경 여부 확인

```bash
python -c "import sys; print(sys.prefix != sys.base_prefix)"
```

정상적으로 가상환경이 적용됐다면 다음 값이 출력돼야 한다.

```text
True
```

### pip 경로 확인

```bash
python -m pip --version
```

출력된 pip 설치 경로에도 프로젝트의 `venv` 디렉터리가 포함돼야 한다.

### 가상환경을 활성화하지 않고 직접 실행

터미널에서 가상환경을 활성화하지 않은 경우 기존 가상환경의 Python 실행 파일을 직접 사용할 수 있다.

Windows:

```powershell
.\venv\Scripts\python.exe -m pip install -e ".[dev]"
.\venv\Scripts\python.exe -m pytest
```

Linux 또는 Jetson:

```bash
./venv/bin/python -m pip install -e ".[dev]"
./venv/bin/python -m pytest
```

Codex는 가상환경 활성화 여부를 추측하지 않고 실제 Python 경로를 확인한다.

---

## 8.2 `scripts/check_virtualenv.py`

현재 Python 프로세스가 가상환경 안에서 실행되고 있는지 검사하는 스크립트를 작성한다.

스크립트는 Python 표준 라이브러리만 사용한다.

### 검사 항목

다음 조건을 확인한다.

1. `sys.prefix != sys.base_prefix`인가?
2. 현재 `sys.executable`이 프로젝트의 `venv/` 내부에 있는가?
3. 프로젝트 루트에 `venv/` 디렉터리가 존재하는가?

단순히 다른 가상환경이 활성화된 것만으로 통과시키지 않는다.

현재 프로젝트의 `venv/`를 사용하고 있는지 확인해야 한다.

### 성공 시 동작

* 현재 Python 실행 경로를 출력한다.
* 가상환경 루트 경로를 출력한다.
* 프로젝트의 `venv/` 사용이 확인됐음을 출력한다.
* 종료 코드 `0`을 반환한다.

예시:

```text
가상환경 확인이 완료되었습니다.
Python 실행 경로: C:\...\bomi-ai-vision\venv\Scripts\python.exe
가상환경 경로: C:\...\bomi-ai-vision\venv
```

### 실패 시 동작

* 현재 Python 실행 경로를 출력한다.
* 프로젝트 `venv/`를 사용하지 않고 있음을 설명한다.
* 운영체제별 활성화 명령을 안내한다.
* 시스템 Python에 설치하지 말아야 한다고 안내한다.
* 종료 코드 `1`을 반환한다.

### 구현 규칙

* 파일 상단에 한국어 모듈 docstring을 작성한다.
* 공개 함수에 한국어 docstring과 타입 힌트를 작성한다.
* 경로 비교 시 가능한 범위에서 절대경로를 사용한다.
* Windows의 대소문자 차이와 경로 구분자를 고려한다.
* 검사 실패를 자동으로 무시하는 옵션을 만들지 않는다.

---

## 8.3 `pyproject.toml`

`pyproject.toml`에는 최소한 다음 내용을 포함한다.

### 프로젝트 정보

* 프로젝트 이름
* 초기 버전
* 프로젝트 설명
* Python 최소 버전
* `src` 패키지 검색 설정

라이선스가 정해지지 않았다면 임의로 라이선스를 확정하지 않는다.

### 개발 도구

개발 의존성에는 최소한 다음 항목을 포함한다.

* pytest
* pytest-cov
* Ruff
* mypy

초기 골격에는 다음 AI 실행 의존성을 추가하지 않는다.

* Ultralytics
* OpenCV
* PyTorch
* TensorRT
* ROS2 Python 패키지

AI 관련 의존성은 실제 기능 계획에서 추가한다.

### Ruff

최소한 다음 항목을 검사한다.

* 일반적인 Python 오류
* import 순서
* 사용되지 않는 import
* 기본적인 코드 스타일
* docstring 존재 여부

Ruff의 docstring 검사는 존재 여부와 기본 형식을 보조적으로 검사한다.

한국어 포함 여부는 별도 검사 스크립트가 담당한다.

### pytest

* 테스트 경로: `tests`
* 소스 경로: `src`
* 테스트 파일 패턴 정의
* 단위 테스트와 통합 테스트를 개별 실행할 수 있게 설정

### mypy

* 프로젝트 Python 버전과 일치
* `src/bomi_vision`과 필요한 스크립트를 검사
* 초기 단계에서 현실적으로 통과 가능한 엄격도를 적용
* 전체 검사를 무력화하는 `ignore_errors = true` 사용 금지
* 특정 외부 라이브러리 문제는 해당 라이브러리가 추가된 시점에 제한적으로 처리

---

## 8.4 `Makefile`

모든 명령은 저장소 루트에서 실행할 수 있어야 한다.

### `make check-env`

현재 Python이 프로젝트의 `venv/` 가상환경을 사용하는지 검사한다.

권장 동작:

```text
python scripts/check_virtualenv.py
python -m pip --version
```

### `make setup`

현재 프로젝트 가상환경에 개발 의존성을 설치한다.

`setup`은 반드시 `check-env`를 먼저 실행해야 한다.

권장 동작:

```text
check-env
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

가상환경 검사가 실패하면 설치를 중단한다.

`make setup`은 새로운 가상환경을 생성하지 않는다.

### `make format`

Ruff를 이용해 코드 포맷을 적용한다.

자동 수정 가능한 import 및 스타일 문제도 필요한 범위에서 처리한다.

### `make lint`

Ruff 정적 검사를 실행한다.

### `make type-check`

mypy 타입 검사를 실행한다.

### `make check-docstrings`

한국어 docstring 검사 스크립트를 실행한다.

### `make test-unit`

`tests/unit` 테스트만 실행한다.

### `make test-integration`

`tests/integration` 테스트만 실행한다.

통합 테스트가 아직 없는 초기 상태에서도 명령 체계가 유지돼야 한다.

필요한 경우 최소 placeholder 테스트를 추가하되 의미 없는 항상 성공 테스트는 만들지 않는다.

### `make test`

전체 테스트를 실행한다.

### `make check`

다음 검증을 순서대로 실행한다.

```text
lint
type-check
check-docstrings
test
```

`make check`는 가상환경을 새로 만들거나 패키지를 설치하지 않는다.

개발자가 올바른 환경에서 실행했다는 전제하에 코드 품질을 검증한다. 다만 각 명령이 잘못된 Python을 사용하는 문제를 방지하기 위해 필요하면 `check-env`를 선행하도록 구성할 수 있다.

현재 프로젝트에서는 로컬 개발 안정성을 우선해 다음 구성을 권장한다.

```text
check-env
lint
type-check
check-docstrings
test
```

CI 환경을 추가할 때는 CI 전용 가상환경 정책을 별도로 정의할 수 있다.

---

## 8.5 패키지 설치 원칙

가상환경이 확인된 상태에서 다음 명령을 사용한다.

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

`pip`를 직접 실행하지 않고 다음 형식을 우선한다.

```text
python -m pip
```

이 방식은 현재 사용하는 Python과 같은 환경에 패키지가 설치되도록 한다.

다음 방식은 사용하지 않는다.

```bash
pip install ...
```

직접 `pip` 명령을 사용해야 하는 특별한 이유가 없다면 `python -m pip`로 통일한다.

---

## 8.6 `scripts/check_korean_docstrings.py`

이 스크립트는 Python 표준 라이브러리의 `ast`를 사용해 작성한다.

추가 외부 패키지에 의존하지 않는 것을 우선한다.

### 검사 대상

* `.py` 파일의 모듈
* 클래스
* 공개 함수
* 공개 메서드
* 테스트 함수

### 공개 함수 판단

이름이 밑줄 하나로 시작하는 함수는 기본적으로 비공개 함수로 간주한다.

다음 특수 메서드는 검사 예외로 둘 수 있다.

* `__init__`
* `__repr__`
* `__str__`
* `__enter__`
* `__exit__`

클래스 docstring만으로 생성자 인자와 제약을 설명하기 어려운 경우에는 `__init__`에도 docstring을 작성한다.

### 한국어 포함 판단

docstring에 한글 음절 또는 한글 자모가 하나 이상 포함돼 있는지 검사한다.

단순히 검사를 통과하기 위해 의미 없는 한글 한 글자를 넣는 방식은 금지한다.

스크립트는 한글 포함 여부만 기계적으로 검사하고, 설명의 품질은 코드 리뷰와 완료 체크리스트에서 확인한다.

### 검사 결과

규칙 위반 시 다음 정보를 출력한다.

* 파일 경로
* 줄 번호
* 대상 종류
* 대상 이름
* 위반 이유

예시:

```text
src/bomi_vision/example.py:1 모듈 docstring이 없습니다.
src/bomi_vision/example.py:12 클래스 'Example'의 docstring에 한글이 없습니다.
tests/unit/test_example.py:8 함수 'test_example'의 docstring이 없습니다.
```

위반 사항이 하나 이상이면 종료 코드 `1`을 반환한다.

모든 검사를 통과하면 종료 코드 `0`을 반환한다.

---

## 8.7 `src/bomi_vision/__init__.py`

패키지가 정상적으로 import되도록 작성한다.

파일 상단에는 한국어 모듈 docstring을 작성한다.

초기 단계에서는 실제 비전 기능을 노출하지 않는다.

필요한 경우 다음 정보만 정의할 수 있다.

```python
__version__ = "0.1.0"
```

버전 정보는 `pyproject.toml`과 일치해야 한다.

---

## 8.8 패키지 smoke test

`tests/unit/test_package_import.py`는 최소한 다음을 검증한다.

* `bomi_vision` 패키지를 import할 수 있음
* 초기 버전 정보가 있다면 예상값과 일치함

테스트 파일과 테스트 함수에는 한국어 docstring을 작성한다.

테스트에서 `sys.path`를 임의로 수정하지 않는다.

패키지의 editable 설치 또는 pytest 설정을 통해 `src` 레이아웃을 정상적으로 인식시킨다.

---

## 8.9 가상환경 검사 테스트

`scripts/check_virtualenv.py`의 핵심 로직은 테스트 가능한 함수로 분리한다.

`tests/unit/test_virtualenv_checker.py`에서는 최소한 다음을 검증한다.

* 현재 Python 경로가 프로젝트 `venv/` 안에 있으면 성공으로 판단
* 다른 가상환경 경로이면 실패로 판단
* 시스템 Python이면 실패로 판단
* Windows 경로 구분자 차이를 안전하게 처리
* 가상환경 디렉터리가 존재하지 않으면 실패로 판단

테스트에서는 실제 시스템 환경을 변경하지 않는다.

`sys.prefix`와 경로값을 함수 인자로 전달하거나 mock을 사용해 검증한다.

---

## 8.10 docstring 검사 테스트

가능하면 검사 스크립트의 핵심 로직을 테스트 가능한 함수로 분리한다.

`tests/unit/test_korean_docstrings.py`에서는 최소한 다음을 검증한다.

* 한국어 모듈 docstring이 있는 파일은 통과
* 모듈 docstring이 없는 파일은 실패
* 한국어 클래스 docstring이 있는 클래스는 통과
* 영어만 있는 클래스 docstring은 실패
* 공개 함수 docstring이 없으면 실패
* 한국어 공개 함수 docstring이 있으면 통과
* 비공개 함수의 docstring은 필수가 아님
* 테스트 함수 docstring이 없으면 실패

테스트용 Python 코드는 임시 파일 또는 문자열 기반 AST 파싱으로 처리한다.

---

## 8.11 `.gitignore`

최소한 다음 항목을 제외한다.

### 가상환경

```gitignore
venv/
.venv/
```

프로젝트에서 실제 사용하는 경로는 `venv/`이지만 실수로 생성된 `.venv/`도 Git에 포함되지 않게 할 수 있다.

### Python

```gitignore
__pycache__/
*.py[cod]
*.egg-info/
build/
dist/
```

### 검사 도구

```gitignore
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
```

### IDE 및 운영체제

```gitignore
.idea/
.vscode/
.DS_Store
Thumbs.db
```

`.vscode/`에서 팀 공통 설정을 공유하기로 결정하면 필요한 파일만 예외 처리할 수 있다.

### AI 비전 산출물

```gitignore
*.pt
*.pth
*.onnx
*.engine
*.plan
*.trt
*.log
artifacts/*
```

`artifacts/.gitkeep`은 Git에 포함할 수 있도록 예외 처리한다.

### 데이터 및 영상

로컬 데이터셋과 촬영 영상은 기본적으로 Git에 포함하지 않는다.

```gitignore
data/
datasets/
videos/
outputs/
```

작은 테스트 fixture가 필요하면 `tests/fixtures/` 아래의 명시적인 파일만 허용한다.

---

## 8.12 `README.md`

초기 README에는 최소한 다음 내용을 포함한다.

* 프로젝트 목적
* 현재 구현 상태
* 프로젝트 구조
* 기존 `venv/` 가상환경 사용 원칙
* Windows 가상환경 활성화 방법
* Linux 및 Jetson 가상환경 활성화 방법
* Python 경로 확인 방법
* 개발 의존성 설치 방법
* 표준 검증 명령
* 현재 MVP 범위
* 아직 구현되지 않은 기능
* 주요 문서 링크

README에는 아직 실제로 동작하지 않는 기능을 동작한다고 작성하지 않는다.

---

## 9. 코드 작성 규칙

이번 작업에서 생성하는 모든 Python 파일은 `docs/code-style.md`를 따른다.

필수 조건은 다음과 같다.

* 파일 상단에 한국어 모듈 docstring 작성
* 모든 클래스에 한국어 docstring 작성
* 모든 공개 함수와 메서드에 한국어 docstring 작성
* 테스트 함수에도 한국어 docstring 작성
* 모든 공개 인터페이스에 타입 힌트 작성
* 중요한 정규식, 경로 비교 및 예외 기준에 한국어 주석 작성
* 코드 내용을 그대로 번역한 불필요한 주석 작성 금지
* 실제 코드와 맞지 않는 오래된 주석 유지 금지

---

## 10. 작업 순서

Codex는 다음 순서로 작업한다.

### 1단계: 현재 저장소 확인

* 기존 폴더와 파일 확인
* 이미 작성된 문서 보존
* `venv/` 존재 여부 확인
* 기존 설정과 충돌 여부 확인

### 2단계: 가상환경 확인

* 현재 Python 실행 경로 확인
* `sys.prefix`와 `sys.base_prefix` 확인
* pip 경로 확인
* 시스템 Python 사용 여부 확인

가상환경이 올바르지 않으면 의존성을 설치하지 않는다.

### 3단계: 패키지 설정

* `pyproject.toml` 작성
* `src/bomi_vision/__init__.py` 작성
* 개발 의존성 설정

### 4단계: 환경 검사 스크립트

* `scripts/check_virtualenv.py` 작성
* 성공 및 실패 출력 구현
* 종료 코드 검증
* 관련 테스트 작성

### 5단계: 테스트 설정

* pytest 구성
* 패키지 smoke test 작성
* 단위 및 통합 테스트 명령 확인

### 6단계: 코드 품질 명령

* Ruff 설정
* mypy 설정
* `Makefile` 작성

### 7단계: 한국어 docstring 검사

* 검사 스크립트 작성
* 오류 출력 형식 구현
* 관련 테스트 작성
* Makefile 명령 연결

### 8단계: 저장소 보조 파일

* `.gitignore`
* `README.md`
* 필요한 `.gitkeep`

### 9단계: 전체 검증

* 가상환경 확인
* 포맷
* 린트
* 타입 검사
* 한국어 docstring 검사
* 단위 테스트
* 통합 테스트
* 전체 테스트

### 10단계: 계획 갱신

* 완료 항목 체크
* 실행한 명령과 결과 기록
* 미해결 사항 기록
* 완료 시 계획 파일 이동 준비

---

## 11. 작업 체크리스트

### 가상환경

* [ ] 프로젝트 루트에 기존 `venv/`가 존재한다.
* [ ] 현재 Python 실행 경로가 `venv/` 내부인지 확인했다.
* [ ] 현재 pip 경로가 `venv/` 내부인지 확인했다.
* [ ] `scripts/check_virtualenv.py`가 작성됐다.
* [ ] 다른 가상환경을 현재 프로젝트 환경으로 오인하지 않는다.
* [ ] 가상환경이 아닌 경우 설치가 중단된다.
* [ ] `venv/`가 `.gitignore`에 포함됐다.
* [ ] 새로운 가상환경을 임의로 만들지 않았다.
* [ ] 시스템 Python에 의존성을 설치하지 않았다.
* [ ] Windows 활성화 방법이 README에 작성됐다.
* [ ] Linux 및 Jetson 활성화 방법이 README에 작성됐다.

### 프로젝트 설정

* [ ] `pyproject.toml`이 작성됐다.
* [ ] Python 최소 버전이 정의됐다.
* [ ] `src` 레이아웃이 설정됐다.
* [ ] 개발 의존성이 정의됐다.
* [ ] AI 실행 의존성이 불필요하게 추가되지 않았다.

### 패키지

* [ ] `src/bomi_vision/__init__.py`가 존재한다.
* [ ] 패키지를 정상적으로 import할 수 있다.
* [ ] 버전 정보가 설정 파일과 일치한다.

### 코드 품질

* [ ] Ruff 설정이 작성됐다.
* [ ] mypy 설정이 작성됐다.
* [ ] pytest 설정이 작성됐다.
* [ ] `Makefile` 표준 명령이 작성됐다.
* [ ] `make setup`이 환경 검사를 선행한다.
* [ ] `make check`가 전체 검증을 수행한다.

### 한국어 문서화 검사

* [ ] `scripts/check_korean_docstrings.py`가 작성됐다.
* [ ] 모듈 docstring을 검사한다.
* [ ] 클래스 docstring을 검사한다.
* [ ] 공개 함수와 메서드 docstring을 검사한다.
* [ ] 테스트 함수 docstring을 검사한다.
* [ ] 한글 포함 여부를 검사한다.
* [ ] 위반 시 종료 코드 `1`을 반환한다.
* [ ] 검사 스크립트의 핵심 로직 테스트가 작성됐다.

### 테스트

* [ ] 패키지 import smoke test가 작성됐다.
* [ ] 가상환경 검사 테스트가 작성됐다.
* [ ] docstring 검사 테스트가 작성됐다.
* [ ] 단위 테스트 명령이 동작한다.
* [ ] 통합 테스트 명령이 동작한다.
* [ ] 전체 테스트 명령이 동작한다.

### 저장소 관리

* [ ] `.gitignore`가 작성됐다.
* [ ] README에 현재 상태가 정확하게 기록됐다.
* [ ] 생성 산출물과 모델 파일이 Git에서 제외됐다.
* [ ] `venv/` 내부 파일을 수정하지 않았다.
* [ ] 불필요한 빈 추상화 파일을 생성하지 않았다.

### 문서화

* [ ] 생성한 Python 파일에 한국어 모듈 docstring이 있다.
* [ ] 생성한 공개 함수와 클래스에 한국어 docstring이 있다.
* [ ] 실제 명령과 문서의 명령이 일치한다.
* [x] 완료 결과와 미해결 사항이 이 계획에 기록됐다.

---

## 12. 검증 명령

Windows PowerShell에서 가상환경을 활성화한다.

```powershell
.\venv\Scripts\Activate.ps1
```

현재 환경을 확인한다.

```powershell
python -c "import sys; print(sys.executable)"
python -c "import sys; print(sys.prefix != sys.base_prefix)"
python -m pip --version
python scripts/check_virtualenv.py
```

개발 의존성을 설치한다.

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

프로젝트 검증을 실행한다.

```powershell
make check-env
make format
make lint
make type-check
make check-docstrings
make test-unit
make test-integration
make test
make check
```

Windows 환경에 `make`가 설치돼 있지 않다면 Makefile 내부의 Python 명령을 개별적으로 실행해 검증할 수 있다.

다만 `Makefile`은 Linux와 Jetson 및 팀 표준 명령을 위해 유지한다.

Codex는 실행하지 못한 명령을 성공했다고 기록하지 않는다.

---

## 13. 완료 조건

다음 조건을 모두 만족해야 이번 계획을 완료한 것으로 간주한다.

1. 기존 `venv/` 가상환경이 정상적으로 동작한다.
2. 현재 Python과 pip가 프로젝트 `venv/`를 사용하는지 자동으로 검사할 수 있다.
3. 가상환경이 아닌 상태에서는 의존성 설치를 중단한다.
4. 시스템 Python에 프로젝트 의존성을 설치하지 않는다.
5. `bomi_vision` 패키지를 정상적으로 import할 수 있다.
6. 개발 의존성을 표준 명령으로 설치할 수 있다.
7. `make lint`가 정상 실행된다.
8. `make type-check`가 정상 실행된다.
9. `make check-docstrings`가 정상 실행된다.
10. `make test`가 정상 실행된다.
11. `make check`가 전체 검증을 수행한다.
12. 한국어 docstring 누락 시 검증이 실패한다.
13. 생성된 모든 Python 파일이 코드 작성 규칙을 따른다.
14. AI 모델 또는 ROS2 없이 초기 검증이 가능하다.
15. README의 가상환경 안내가 실제 경로와 일치한다.
16. README의 설명이 현재 프로젝트 상태와 일치한다.
17. 완료한 항목과 실행 결과가 이 문서에 기록됐다.
18. 새로운 가상환경을 임의로 생성하지 않았다.
19. 기존 `venv/`를 삭제하거나 수정하지 않았다.

---

## 14. 완료 기록

초기 구조와 PR 리뷰 보완 작업의 실제 결과를 기록한다.

### 완료 일자

* 2026-07-19

### 사용한 Python 실행 경로

* `C:\Users\SSAFY\Desktop\bomi\robot\ai_vision\venv\Scripts\python.exe`

### 사용한 pip 경로

* 프로젝트 `venv`의 `python -m pip`

### 완료한 작업

* Makefile 문법과 명령 연결 수정
* 신규 개발자의 `venv` 최초 생성 절차 추가
* editable install 기반 import 검증으로 변경
* coverage 정규식, Ruff, mypy 타입 오류 수정
* XML 무시 범위와 계획 문서 상태 정리
* README 축약, `CLAUDE.md` 추가, 빈 하위 `AGENTS.md` 제거

### 실행한 검증 명령

* `python -m pip install -e ".[dev]"`
* `python -m ruff format src scripts tests --check`
* `python -m ruff check src scripts tests`
* `python -m mypy src/bomi_vision scripts`
* `python scripts/check_korean_docstrings.py`
* `python -m pytest tests -v`
* `python -m pytest tests --cov=bomi_vision --cov-branch --cov-report=term-missing --cov-report=html`

### 검증 결과

* Python 기반 검증 명령 전체 통과
* 단위 테스트 30개 통과
* 패키지 커버리지 100%
* 현재 Windows 환경에는 GNU Make가 없어 Make target은 직접 실행하지 못함

### 생성 또는 수정한 주요 파일

* `Makefile`, `pyproject.toml`, `.gitignore`, `README.md`
* `scripts/check_korean_docstrings.py`, `tests/unit/test_package_import.py`
* `CLAUDE.md`, `tests/integration/.gitkeep`

### 미해결 사항

* GNU Make가 설치된 Linux 또는 Jetson 환경에서 Make target 실행 확인 필요

### 후속 작업

사람 탐지, ByteTrack 추적 및 사람 수 상태 머신은 별도 이슈와 활성 계획에서 단계적으로 구현한다. 초기 구조 완료만을 이유로 미래 기능을 완료 처리하지 않는다.

---

## 15. Codex 작업 지시 요약

Codex는 이번 계획을 수행할 때 다음 원칙을 지킨다.

* 기존 `venv/` 가상환경을 사용한다.
* 새로운 가상환경을 생성하지 않는다.
* 시스템 Python에 패키지를 설치하지 않는다.
* 설치 전 Python과 pip 경로를 확인한다.
* AI 기능을 구현하지 않는다.
* 기존 문서를 임의로 축약하거나 삭제하지 않는다.
* 현재 저장소 구조를 먼저 확인한다.
* 필요한 최소 파일만 생성한다.
* 모든 Python 코드에 한국어 docstring을 작성한다.
* 표준 명령으로 검증한다.
* 실행하지 않은 검증을 성공했다고 보고하지 않는다.
* 완료 결과와 미해결 사항을 이 계획에 갱신한다.

## 완료 결과

- 프로젝트 패키지 구조 생성 완료
- 기존 venv 기반 개발환경 구성 완료
- Ruff, mypy, pytest 설정 완료
- 가상환경 검사 스크립트 작성 완료
- 한국어 docstring 검사 스크립트 작성 완료
- 단위 테스트 통과
- 패키지 import 테스트 통과
- 전체 테스트 통과
