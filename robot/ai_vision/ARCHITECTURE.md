# BOMI AI Vision 아키텍처

## 1. 문서 목적

이 문서는 BOMI AI Vision 프로젝트의 코드 구조, 계층별 책임과 의존성 규칙을 정의한다.

프로젝트의 주요 아키텍처 목표는 다음과 같다.

* AI 비전 핵심 로직을 YOLO, OpenCV, ROS2 같은 외부 기술과 분리한다.
* 영상 입력 방식을 변경해도 핵심 분석 로직을 재사용할 수 있게 한다.
* 사람 탐지, 추적, 상태 판단과 결과 출력을 개별적으로 테스트할 수 있게 한다.
* Codex가 기능을 추가할 때 기존 책임을 침범하지 않도록 명확한 경계를 제공한다.
* Jetson Orin Nano 최적화나 ROS2 연동을 나중에 추가해도 핵심 로직 변경을 최소화한다.
* 읽기 쉽고 수정하기 쉬운 구조를 유지한다.

이 문서는 구체적인 모델과 수면 분석 방법을 확정하는 문서가 아니다.

기능 요구사항은 `docs/vision-requirements.md`, 상태 전환 규칙은 `docs/state-machine.md`를 기준으로 한다.

---

## 2. 아키텍처 기본 원칙

### 2.1 관심사를 분리한다

프로젝트는 다음 관심사를 서로 분리한다.

* 핵심 데이터와 상태 정의
* 사람 탐지
* 사람 추적
* 사람 수 및 추적 상태 판단
* 사용자 상태 분석
* 전체 처리 흐름 조합
* 영상 파일 및 카메라 입력
* 외부 AI 라이브러리 연결
* ROS2 연결
* 디버그 화면과 결과 저장
* 설정 로딩
* 로그 및 오류 변환

하나의 클래스나 함수가 여러 계층의 역할을 동시에 수행하지 않도록 한다.

---

### 2.2 의존성은 안쪽을 향한다

프로젝트의 의존성 방향은 다음과 같다.

```text
adapters
    ↓
application
    ↓
domain
```

외부 프레임워크와 라이브러리는 바깥쪽 계층에서만 사용한다.

안쪽 계층은 바깥쪽 계층을 알지 못한다.

예를 들어 `domain` 계층은 다음 모듈을 import하면 안 된다.

* OpenCV
* Ultralytics
* PyTorch
* TensorRT
* ROS2
* FastAPI
* Spring 관련 클라이언트
* 특정 카메라 SDK

---

### 2.3 핵심 로직은 외부 환경 없이 테스트할 수 있어야 한다

다음 기능은 실제 카메라, YOLO 모델, GPU 및 ROS2 없이 단위 테스트할 수 있어야 한다.

* 바운딩 박스 좌표 계산
* 사람 수 검증
* 사람 추적 상태 전환
* 다중 인물 확인
* 한 명 복귀 안정화
* 일시적 탐지 실패 처리
* 상호작용 허용 정책
* 설정값 검증
* 외부 결과를 내부 데이터 구조로 변환하는 순수 로직

---

### 2.4 구현되지 않은 미래 기능을 미리 추상화하지 않는다

현재 확정되지 않은 다음 기능을 위한 복잡한 구조를 미리 만들지 않는다.

* 얼굴인식
* Person Re-ID
* 다중 보호대상자
* 여러 카메라 간 추적
* 침대 인식
* 특정 공간 자동 인식
* 별도 수면 분류 모델
* 의료적 수면 분석

해당 기능이 실제 실행 계획에 포함됐을 때 필요한 최소 구조를 추가한다.

---

## 3. 권장 프로젝트 구조

초기 권장 구조는 다음과 같다.

```text
bomi-ai-vision/
├── AGENTS.md
├── ARCHITECTURE.md
├── README.md
├── pyproject.toml
├── Makefile
│
├── config/
│   ├── vision.default.yaml
│   └── vision.demo.yaml
│
├── docs/
│   ├── code-style.md
│   ├── vision-requirements.md
│   ├── state-machine.md
│   ├── decisions/
│   └── plans/
│       ├── active/
│       └── completed/
│
├── src/
│   └── bomi_vision/
│       ├── __init__.py
│       ├── domain/
│       ├── application/
│       ├── adapters/
│       └── config/
│
├── scripts/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── evals/
│
└── artifacts/
```

하위 디렉터리는 실제 기능 구현 시점에 필요한 범위만 생성한다.

빈 추상화 파일이나 사용되지 않는 패키지를 미리 대량으로 만들지 않는다.

---

## 4. `domain` 계층

### 4.1 책임

`domain` 계층은 AI 비전 프로젝트에서 사용하는 핵심 데이터와 상태를 정의한다.

예상되는 구성 요소는 다음과 같다.

* 바운딩 박스
* 사람 탐지 결과
* 추적 중인 사람
* 사람 추적 상태
* 사용자 상태
* 화면상 방향
* 비전 파이프라인 최종 결과
* 도메인 예외
* 탐지기와 추적기의 추상 인터페이스

### 4.2 허용되는 의존성

`domain` 계층은 다음에만 의존하는 것을 원칙으로 한다.

* Python 표준 라이브러리
* 프로젝트 내부의 다른 `domain` 모듈
* 필요한 경우 가벼운 타입 전용 라이브러리

### 4.3 금지되는 의존성

`domain` 계층은 다음에 직접 의존하지 않는다.

* `numpy.ndarray`
* OpenCV 객체
* Ultralytics 결과 객체
* PyTorch Tensor
* TensorRT 객체
* ROS2 메시지
* YAML 파서
* 파일 시스템
* 네트워크

단, 프레임 데이터 타입이 초기 구현에서 불가피하게 NumPy 배열을 사용할 경우 해당 타입은 application 또는 adapter 경계에서 다룬다.

### 4.4 예시

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class BoundingBox:
    """원본 영상의 픽셀 좌표를 기준으로 한 바운딩 박스를 표현한다."""

    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(frozen=True)
class TrackedPerson:
    """현재 프레임에서 추적된 한 사람의 위치와 추적 정보를 표현한다."""

    track_id: int
    confidence: float
    bounding_box: BoundingBox
```

---

## 5. `application` 계층

### 5.1 책임

`application` 계층은 여러 핵심 기능을 조합해 하나의 비전 처리 흐름을 구성한다.

주요 책임은 다음과 같다.

* 프레임 처리 순서 제어
* 탐지기 호출
* 추적기 호출
* 유효한 사람 수 계산
* 추적 상태 머신 갱신
* 사용자 상태 분석 호출
* 최종 결과 생성
* 외부 오류를 안전한 결과로 변환

### 5.2 하지 않는 일

`application` 계층은 다음을 직접 수행하지 않는다.

* YOLO 모델 생성
* ByteTrack 라이브러리 세부 설정
* 웹캠 열기
* 영상 파일 읽기
* OpenCV 화면 출력
* ROS2 Topic 구독 또는 발행
* TensorRT 엔진 로딩
* 파일 저장
* 네트워크 요청

### 5.3 예상 구성 요소

```text
application/
├── vision_pipeline.py
├── person_state_service.py
├── interaction_policy.py
└── result_factory.py
```

실제 파일은 구현 필요성이 생겼을 때 추가한다.

### 5.4 예시 처리 흐름

```text
영상 프레임
    ↓
사람 탐지
    ↓
사람 추적
    ↓
유효한 사람 수 계산
    ↓
사람 추적 상태 갱신
    ↓
사용자 상태 분석
    ↓
상호작용 및 이동 허용 정책 계산
    ↓
VisionResult 반환
```

---

## 6. `adapters` 계층

### 6.1 책임

`adapters` 계층은 프로젝트의 내부 인터페이스와 외부 기술을 연결한다.

외부 라이브러리의 데이터 구조를 내부 데이터 구조로 변환하는 책임도 갖는다.

### 6.2 예상 adapter 종류

```text
adapters/
├── detection/
│   └── ultralytics_detector.py
├── tracking/
│   └── bytetrack_tracker.py
├── input/
│   ├── video_file_source.py
│   └── webcam_source.py
├── output/
│   ├── opencv_debug_view.py
│   └── result_writer.py
└── ros2/
    └── vision_node.py
```

ROS2 관련 폴더는 ROS2 연동 작업이 실행 계획에 포함됐을 때 생성한다.

### 6.3 외부 객체 노출 금지

다음 객체가 application 또는 domain 계층으로 직접 전달되면 안 된다.

* Ultralytics `Results`
* Ultralytics `Boxes`
* PyTorch Tensor
* OpenCV `VideoCapture`
* ROS2 메시지 객체

adapter 계층에서 프로젝트 내부 객체로 변환한다.

예시:

```text
Ultralytics Results
    ↓ adapter 변환
list[PersonDetection]
```

### 6.4 예외 변환

외부 라이브러리의 예외는 가능한 경우 프로젝트가 이해할 수 있는 예외로 변환한다.

예:

```text
FileNotFoundError
Ultralytics 내부 오류
CUDA 오류
    ↓
ModelLoadError 또는 InferenceError
```

예외를 변환할 때 원래 예외를 `from error`로 연결한다.

---

## 7. 설정 계층

### 7.1 책임

설정 계층은 실행 환경에 따라 달라지는 값을 코드에서 분리한다.

관리 대상은 다음과 같다.

* 모델 경로
* 모델 입력 크기
* confidence 임계값
* 실행 장치
* 추적 설정
* 상태 확인 기준
* 카메라 번호
* 입력 영상 경로
* 디버그 출력 여부
* 로그 수준
* 향후 ROS2 Topic 이름

### 7.2 기본 구조

```text
config/
├── vision.default.yaml
└── vision.demo.yaml
```

Python 설정 객체는 다음 위치 중 하나에 둘 수 있다.

```text
src/bomi_vision/config/
```

### 7.3 설정 처리 흐름

```text
YAML 또는 명령행 인자
    ↓
설정 로더
    ↓
타입이 명확한 설정 객체
    ↓
유효성 검증
    ↓
application 및 adapter에 주입
```

핵심 로직이 YAML 파일을 직접 읽지 않도록 한다.

### 7.4 환경별 설정

기본 설정과 시연 설정은 분리할 수 있다.

* `vision.default.yaml`: 일반 개발 기본값
* `vision.demo.yaml`: 짧은 상태 전환과 디버그 출력을 위한 시연용 설정

시연용 값을 운영 기본값처럼 사용하지 않는다.

---

## 8. 영상 입력 구조

### 8.1 공통 원칙

영상 입력 방식은 핵심 비전 파이프라인과 분리한다.

다음 입력 방식이 동일한 파이프라인을 사용할 수 있어야 한다.

* 영상 파일
* USB 웹캠
* 노트북 카메라
* 향후 ROS2 이미지 Topic

### 8.2 입력 adapter의 책임

* 프레임 읽기
* 입력 소스 종료 여부 판단
* 프레임 시각 또는 시퀀스 관리
* 프레임 크기 제공
* 입력 오류 처리

### 8.3 입력 adapter가 하지 않는 일

* YOLO 추론
* 사람 상태 판단
* 수면 상태 판단
* 상호작용 허용 결정
* 화면 표시

---

## 9. 탐지 구조

### 9.1 내부 탐지 인터페이스

탐지 기능은 특정 YOLO 버전에 직접 고정하지 않는다.

개념적으로 다음 인터페이스를 사용할 수 있다.

```python
from typing import Protocol


class PersonDetector(Protocol):
    """영상 프레임에서 사람 탐지 결과를 반환하는 인터페이스다."""

    def detect(self, frame: object) -> list[PersonDetection]:
        """입력 프레임에서 유효한 사람 탐지 결과를 반환한다."""
```

실제 프레임 타입은 구현 단계에서 결정하되 외부 결과 타입은 반환하지 않는다.

### 9.2 YOLO adapter 책임

* 모델 로딩
* 사람 클래스 필터링
* confidence 적용
* 추론 실행
* 외부 좌표와 타입 변환
* 모델 오류 변환
* 추론시간 측정

### 9.3 탐지 adapter가 하지 않는 일

* 보호대상자 선택
* 다중 인물 상태 결정
* Track ID 관리
* 능동 대화 허용 판단

---

## 10. 추적 구조

### 10.1 내부 추적 인터페이스

추적기는 탐지 결과 또는 영상 프레임을 받아 내부 추적 결과를 반환한다.

구체적인 인터페이스는 Ultralytics 통합 방식과 별도 ByteTrack 사용 방식 중 실제 구현에 맞춰 결정한다.

### 10.2 ByteTrack adapter 책임

* ByteTrack 설정 적용
* Track ID 생성과 유지
* 외부 추적 결과 변환
* Track ID가 없는 결과 처리
* 추적기 초기화와 재설정

### 10.3 추적기가 하지 않는 일

* Track ID를 사용자 신원으로 해석
* 다중 인물 중 보호대상자 선택
* 모터 제어
* 사용자 수면 판단

---

## 11. 상태 머신 구조

### 11.1 위치

사람 추적 상태 머신은 외부 모델과 분리된 핵심 로직으로 구현한다.

예상 위치:

```text
src/bomi_vision/domain/
```

또는 책임이 커질 경우:

```text
src/bomi_vision/application/
```

상태 머신은 가능한 한 Python 표준 타입만 입력받아야 한다.

### 11.2 입력

예상 입력은 다음과 같다.

* 현재 유효한 사람 수
* 현재 프레임 시각
* 이전 상태
* 필요한 경우 Track ID 유효성
* 설정된 확인 및 복귀 기준

### 11.3 출력

* 새로운 사람 추적 상태
* 보호대상자 선택 가능 여부
* 상태 변경 여부
* 상태 판단 이유

### 11.4 시간 의존성 분리

테스트 가능성을 위해 상태 머신 내부에서 `time.time()`이나 `time.monotonic()`을 직접 호출하지 않는 것을 권장한다.

현재 시각이나 경과시간을 외부에서 주입한다.

예:

```python
def update(
    self,
    person_count: int,
    observed_at_seconds: float,
) -> PersonStateResult:
    """현재 사람 수와 관찰 시각을 기반으로 추적 상태를 갱신한다."""
```

프레임 수 기준만 사용하는 초기 구현에서는 시각 입력을 생략할 수 있다.

---

## 12. 사용자 상태 분석 구조

### 12.1 현재 상태

사용자 상태 기능의 목적은 확정됐지만 구체적인 분석 방법은 아직 확정되지 않았다.

확정된 목적:

* 쉬거나 잠든 가능성이 있는 사용자에게 능동적으로 말을 걸지 않는다.

미확정 방법:

* 바운딩 박스 비율
* Pose
* 움직임 분석
* ROI
* 별도 분류 모델

### 12.2 아키텍처 원칙

사용자 상태 분석은 교체 가능한 컴포넌트로 구현한다.

예상 입력:

* 현재 보호대상자 정보
* 필요한 프레임 이력
* 자세 분석 결과
* 움직임 분석 결과

예상 출력:

* `UNKNOWN`
* `AWAKE`
* `RESTING`
* `SLEEPING_ESTIMATED`
* confidence
* 판단 이유

### 12.3 구현 제한

구체적인 분석 방식이 확정되기 전에는 다음 구조를 미리 만들지 않는다.

* 침대 전용 모델
* Pose 전용 복잡한 계층
* Optical Flow 전용 추상화
* 다수의 수면 분류 전략 클래스

실행 계획에서 선택된 방법에 필요한 최소 구조만 만든다.

---

## 13. 상호작용 정책 구조

사용자 상태 분석과 능동 대화 허용 결정은 구분한다.

예:

```text
사용자 상태 분석
    ↓
AWAKE / RESTING / SLEEPING_ESTIMATED / UNKNOWN
    ↓
상호작용 정책
    ↓
interaction_allowed
```

상호작용 정책은 최소한 다음 정보를 확인한다.

* 사람 추적 상태
* 사용자 상태
* 분석 confidence
* 영상 최신성
* 처리 오류 여부

AI 비전에서 계산하는 `interaction_allowed`는 능동적으로 먼저 말을 걸어도 되는지에 대한 값이다.

사용자가 먼저 로봇을 호출했을 때 응답할지는 대화 시스템이 결정한다.

---

## 14. 결과 모델

최종 비전 결과는 외부 라이브러리와 무관한 프로젝트 내부 데이터 구조로 정의한다.

예상 구성:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class VisionResult:
    """한 프레임의 AI 비전 처리 결과를 외부 시스템에 전달하기 위해 표현한다."""

    person_count: int
    person_state: PersonState
    user_state: UserState
    target: TrackedPerson | None
    interaction_allowed: bool
    movement_allowed: bool
    confidence: float
    reason: str
```

실제 필드는 구현 단계에서 확정한다.

최종 결과에 다음 객체를 직접 포함하지 않는다.

* Ultralytics Results
* PyTorch Tensor
* ROS2 메시지
* OpenCV VideoCapture
* 모델 인스턴스

---

## 15. ROS2 연동 원칙

ROS2 연동은 adapter 계층에서 수행한다.

예상 흐름:

```text
ROS2 Image 메시지
    ↓
ROS2 입력 adapter
    ↓
내부 프레임 형식
    ↓
VisionPipeline
    ↓
VisionResult
    ↓
ROS2 출력 adapter
    ↓
비전 상태 메시지
```

ROS2 노드는 다음 기능만 담당한다.

* Topic 구독
* 메시지 변환
* 파이프라인 호출
* 결과 메시지 변환 및 발행
* ROS2 파라미터 연결
* ROS2 로그 및 생명주기 관리

ROS2 노드 안에 다음 로직을 직접 구현하지 않는다.

* 사람 수 상태 전환
* 다중 인물 확인
* 수면 및 휴식 판단
* 보호대상자 선택 정책
* 상호작용 허용 정책

ROS2 연동이 확정되기 전에는 Topic 이름과 메시지 구조를 코드에 미리 고정하지 않는다.

---

## 16. 외부 시스템과의 책임 경계

### 16.1 AI 비전이 제공하는 정보

* 사람 수
* 추적 상태
* 사용자 상태
* 보호대상자 화면 위치
* 능동 대화 허용 여부
* AI 비전 관점 이동 허용 여부
* confidence
* 판단 이유
* 오류 정보

### 16.2 AI 비전이 하지 않는 일

* 실제 모터 속도 결정
* 장애물 회피
* 비상 정지 우선순위 결정
* 주행 경로 생성
* TTS 문장 생성
* 대화 시작 시간 결정
* 사용자의 음성 호출 처리
* Spring 서버의 비즈니스 로직 처리

최종 로봇 행동은 주행, 안전 제어 및 대화 시스템이 결정한다.

---

## 17. 디버그 및 시각화 구조

디버그 화면 생성은 핵심 분석 로직과 분리한다.

디버그 adapter는 다음 정보를 화면에 표시할 수 있다.

* 사람 바운딩 박스
* Track ID
* confidence
* 사람 수
* 사람 추적 상태
* 사용자 상태
* 능동 대화 허용 여부
* 추론시간과 FPS

핵심 결과 객체를 변경하기 위해 화면 표시 코드를 수정할 필요가 없어야 한다.

운영 환경에서는 디버그 출력과 영상 저장을 비활성화할 수 있어야 한다.

---

## 18. 오류 처리 구조

### 18.1 오류 분류

프로젝트에서 예상되는 오류는 다음과 같이 구분할 수 있다.

* 설정 오류
* 모델 로딩 오류
* 영상 입력 오류
* 추론 오류
* 추적 오류
* 결과 변환 오류
* 외부 연동 오류

### 18.2 오류 전파 원칙

* 하위 adapter는 가능한 경우 구체적인 프로젝트 예외를 발생시킨다.
* application 계층은 계속 처리 가능한 오류인지 판단한다.
* 복구 불가능한 초기화 오류는 명확하게 실패시킨다.
* 프레임 단위 처리 오류는 로그를 남기고 안전한 결과로 변환할 수 있다.
* 오류를 조용히 무시하지 않는다.

### 18.3 안전 결과

프레임 처리 결과를 신뢰할 수 없으면 기본적으로 다음 정책을 사용한다.

```text
user_state = UNKNOWN
interaction_allowed = false
movement_allowed = false
```

사람 추적 상태의 오류 표현 방식은 구현 시 별도 `ERROR` 상태 추가 여부를 검토한다.

기존 `NOT_DETECTED`와 오류를 구분해야 할 필요가 확인되기 전에는 불필요하게 상태를 추가하지 않는다.

---

## 19. 테스트 구조

### 19.1 단위 테스트

```text
tests/unit/
```

대상:

* 데이터 모델 검증
* 좌표 계산
* 상태 머신
* 설정값 검증
* 상호작용 정책
* 외부 결과 변환의 순수 로직

### 19.2 통합 테스트

```text
tests/integration/
```

대상:

* 가짜 탐지기와 추적기를 이용한 전체 파이프라인
* 저장된 작은 테스트 영상 처리
* 외부 adapter와 내부 결과 변환
* 오류 발생 시 안전 결과 생성

### 19.3 평가

```text
evals/
```

실제 시나리오 기반 품질 검증에 사용한다.

예:

* 사람이 없는 영상
* 한 명이 이동하는 영상
* 잠시 가려지는 영상
* 두 명이 등장하는 영상
* 다중 인물 후 한 명이 남는 영상

평가는 단위 테스트와 다르다.

단위 테스트는 코드 규칙의 정확성을 검증하고, 평가는 실제 영상에서 기능 품질을 측정한다.

---

## 20. 스크립트 구조

개발 및 검증용 실행 코드는 `scripts/`에 둔다.

예상 스크립트:

```text
scripts/
├── run_video.py
├── run_webcam.py
├── benchmark_model.py
├── validate_environment.py
└── check_korean_docstrings.py
```

스크립트는 얇은 진입점으로 유지한다.

스크립트 안에 핵심 상태 판단이나 모델 결과 변환 로직을 중복 구현하지 않는다.

---

## 21. Artifacts 관리

실행 중 생성되는 결과는 소스 코드와 분리한다.

```text
artifacts/
├── reports/
├── benchmark/
├── debug/
└── outputs/
```

기본적으로 Git에 포함하지 않는다.

예상 결과:

* 성능 측정 결과
* 디버그 이미지
* 처리된 영상
* 테스트 보고서
* 로그 파일

모델 파일도 크기가 크다면 Git 저장소에 직접 포함하지 않는다.

---

## 22. 계층별 import 규칙

### `domain`

허용:

```text
Python 표준 라이브러리
domain 내부 모듈
```

금지:

```text
application
adapters
OpenCV
Ultralytics
ROS2
```

### `application`

허용:

```text
domain
application 내부 모듈
domain에 정의된 인터페이스
```

금지 원칙:

```text
ROS2 노드 직접 사용
OpenCV VideoCapture 직접 사용
Ultralytics Results 직접 노출
```

필요한 외부 기능은 주입받는다.

### `adapters`

허용:

```text
domain
application
외부 라이브러리
```

adapter끼리 불필요하게 서로 의존하지 않는다.

예를 들어 ROS2 adapter가 Ultralytics adapter 내부 구현에 직접 접근하지 않고 application 파이프라인을 호출하도록 한다.

---

## 23. 의존성 주입 원칙

핵심 application 객체는 필요한 기능을 생성자 등으로 전달받는 방식을 우선한다.

예:

```python
class VisionPipeline:
    """탐지기와 추적 상태 관리자를 조합해 최종 비전 결과를 생성한다."""

    def __init__(
        self,
        detector: PersonDetector,
        state_manager: PersonStateManager,
    ) -> None:
        self._detector = detector
        self._state_manager = state_manager
```

이 방식은 다음 장점이 있다.

* 테스트에서 가짜 탐지기로 교체 가능
* YOLO 모델 교체 가능
* 외부 라이브러리 의존성 축소
* 각 컴포넌트의 책임 명확화

단순한 초기 구현에 과도한 DI 프레임워크를 사용하지 않는다.

Python 생성자 주입으로 충분하다.

---

## 24. 동시성 및 실시간 처리 원칙

카메라 입력 속도가 추론 속도보다 빠를 수 있다.

이 경우 오래된 프레임을 모두 순서대로 처리해 지연이 계속 쌓이는 구조를 피한다.

권장 방식:

```text
영상 입력
    ↓
최신 프레임 보관
    ↓
추론 가능 시 최신 프레임 처리
    ↓
처리 중 도착한 오래된 프레임은 필요에 따라 대체
```

초기 로컬 영상 테스트에서는 단순한 순차 처리로 시작할 수 있다.

실시간 카메라 또는 ROS2 연동 단계에서 다음을 검토한다.

* 최신 프레임 우선 처리
* 제한된 큐 크기
* 추론 중복 실행 방지
* 프레임 시각 검증
* 처리 FPS와 입력 FPS 분리

동시성 로직은 adapter 또는 실행 계층에 두고 상태 머신 내부에 넣지 않는다.

---

## 25. 아키텍처 검증

아키텍처 규칙은 문서에만 의존하지 않고 가능한 범위에서 자동 검증한다.

검토 가능한 방법:

* Ruff import 규칙
* 별도 import 검사 스크립트
* `import-linter`
* 단위 테스트
* Codex 완료 체크리스트

최소한 다음 위반을 검사한다.

* domain에서 OpenCV import
* domain에서 Ultralytics import
* domain에서 ROS2 import
* 상태 머신에서 외부 모델 객체 사용
* scripts에 핵심 정책 중복 구현
* ROS2 노드에 상태 전환 로직 직접 구현

자동 검사 도입은 프로젝트 초기 골격 이후 실행 계획으로 추가할 수 있다.

---

## 26. 아키텍처 변경 기준

다음 상황에서는 아키텍처 변경을 검토한다.

* 새로운 기능이 기존 계층에 자연스럽게 들어가지 않음
* 동일한 외부 라이브러리 변환 코드가 여러 곳에 중복됨
* 단위 테스트를 위해 지나치게 많은 외부 환경이 필요함
* 모델 교체가 상태 로직 수정으로 이어짐
* ROS2 연동 코드가 핵심 파이프라인에 침투함
* 한 클래스가 여러 책임을 갖게 됨
* 순환 import가 발생함

단순히 파일이 길어졌다는 이유만으로 새 계층을 추가하지 않는다.

책임과 변경 이유가 명확할 때 구조를 변경한다.

---

## 27. 아키텍처 결정 기록

중요한 구조 변경은 `docs/decisions/`에 기록한다.

기록 대상 예시:

* YOLO와 ByteTrack 통합 방식
* 프레임 수와 시간 중 상태 기준 선택
* 사용자 상태 분석 방식 선택
* ROS2 메시지 구조
* TensorRT 적용 방식
* Pose 모델 사용 여부

결정 기록에는 다음 내용을 포함한다.

* 문제 상황
* 검토한 선택지
* 최종 결정
* 결정 이유
* 장단점
* 향후 영향

---

## 28. 현재 확정된 아키텍처

다음 내용은 현재 확정된 원칙이다.

* 핵심 상태 로직과 외부 AI 라이브러리를 분리한다.
* YOLO와 ByteTrack은 adapter를 통해 연결한다.
* 사람 추적 상태 머신은 외부 모델 없이 테스트 가능하게 작성한다.
* 영상 파일, 웹캠과 ROS2 입력은 같은 비전 파이프라인을 재사용한다.
* AI 비전은 모터와 TTS를 직접 제어하지 않는다.
* 외부 라이브러리 객체를 최종 결과에 노출하지 않는다.
* 설정값을 코드 여러 곳에 하드코딩하지 않는다.
* 확정되지 않은 미래 기능을 위해 복잡한 추상화를 미리 만들지 않는다.
* 오류와 불확실한 결과는 안전한 정책으로 변환한다.

---

## 29. 미확정 아키텍처 항목

다음 항목은 구현 및 성능 테스트 이후 결정한다.

* Ultralytics 통합 추적 사용 여부
* 탐지와 ByteTrack을 별도 컴포넌트로 분리할지 여부
* 최종 YOLO 모델
* 사용자 상태 분석 구조
* ROS2 패키지와 현재 Python 패키지의 배치 방식
* ROS2 커스텀 메시지 정의
* TensorRT 엔진 관리 방식
* 실시간 프레임 처리 동시성 구조
* 시간 기준 상태 머신 적용 여부
* 별도의 `ERROR` 상태 추가 여부

미확정 사항은 활성 실행 계획에서 결정되기 전까지 임의로 구현하지 않는다.

---

## 30. 변경 절차

아키텍처를 변경할 때는 다음 순서를 따른다.

1. 변경이 필요한 구체적인 문제를 확인한다.
2. 기존 `ARCHITECTURE.md` 규칙으로 해결할 수 있는지 검토한다.
3. 기능 요구사항과 상태 머신 문서를 확인한다.
4. 중요한 변경이면 `docs/decisions/`에 결정 기록을 작성한다.
5. 이 문서를 수정한다.
6. 활성 실행 계획을 수정한다.
7. 코드를 변경한다.
8. 단위 테스트와 통합 테스트를 실행한다.
9. 기존 의존성 규칙이 유지되는지 확인한다.

코드 구조를 먼저 변경한 뒤 문서를 현재 코드에 맞추는 방식은 피한다.
