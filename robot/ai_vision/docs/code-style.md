# BOMI AI Vision 코드 작성 규칙

## 1. 문서 목적

이 문서는 BOMI AI Vision 프로젝트의 코드 작성 규칙을 정의한다.

프로젝트의 가장 중요한 코드 작성 원칙은 다음과 같다.

> 다른 개발자가 코드를 처음 읽더라도 파일의 목적, 주요 처리 흐름, 함수와 클래스의 책임, 중요한 판단 기준을 쉽게 이해할 수 있어야 한다.

Codex를 포함한 모든 개발자는 코드를 생성하거나 수정할 때 이 문서를 따라야 한다.

이 문서는 특히 다음 항목을 구체적으로 규정한다.

* 한국어 주석 작성 기준
* 모듈, 클래스, 함수 docstring 작성 기준
* 중요한 변수와 상태값 설명 기준
* 변수, 함수, 클래스 이름 작성 기준
* 함수와 클래스의 책임 분리
* 타입 힌트 작성 기준
* 예외 처리 기준
* 로그 작성 기준
* 테스트 코드 작성 기준
* 금지되는 코드와 주석 형태

---

## 2. 기본 작성 원칙

### 2.1 가독성을 우선한다

코드는 단순히 동작하는 것에 그치지 않고 다른 개발자가 읽고 수정하기 쉬워야 한다.

다음 원칙을 따른다.

* 한 함수는 가능한 한 하나의 책임만 가진다.
* 한 클래스는 명확한 하나의 역할을 중심으로 설계한다.
* 긴 조건문은 의미 있는 함수나 변수로 분리한다.
* 중복되는 판단 로직은 하나의 함수 또는 클래스로 통합한다.
* 이름만으로 의미를 알기 어려운 숫자나 문자열을 직접 사용하지 않는다.
* 복잡한 축약어보다 의미가 명확한 이름을 사용한다.
* 코드의 의도와 실제 동작이 일치해야 한다.
* 미래에 사용할 가능성만으로 불필요한 추상화를 미리 만들지 않는다.

---

### 2.2 이름은 영어, 설명은 한국어로 작성한다

다음 요소의 이름은 영어로 작성한다.

* 파일명
* 모듈명
* 변수명
* 함수명
* 클래스명
* Enum 이름
* 상수명
* 테스트 함수명

다음 요소의 설명은 한국어로 작성한다.

* 모듈 docstring
* 클래스 docstring
* 함수와 메서드 docstring
* 인라인 주석
* 설정값 설명
* 예외 발생 이유
* 로그 메시지

예시:

```python
class PersonStateManager:
    """프레임별 사람 수를 기반으로 보호대상자 추적 상태를 관리한다."""
```

---

### 2.3 주석은 코드의 의도를 설명한다

주석은 코드 내용을 그대로 한국어로 번역하는 용도로 사용하지 않는다.

나쁜 예시:

```python
count += 1  # count를 1 증가시킨다.
```

좋은 예시:

```python
# 한 프레임의 오탐으로 다중 인물 상태가 확정되지 않도록 연속 검출 횟수를 누적한다.
multiple_detection_frames += 1
```

주석에는 가능한 한 다음 내용을 담는다.

* 이 로직이 필요한 이유
* 특정 기준값을 사용하는 이유
* 안전상 보수적으로 처리하는 이유
* 외부 라이브러리의 한계를 보완하는 방법
* 해당 상태 전환이 서비스에 미치는 영향
* 이후 개발자가 주의해야 할 조건

---

## 3. Python 파일 상단 설명 규칙

모든 Python 파일의 가장 위에는 한국어 모듈 docstring을 작성한다.

단, shebang 또는 인코딩 선언이 필요한 경우 해당 선언 다음에 작성한다.

### 3.1 필수 포함 내용

모듈 docstring에는 필요한 범위에서 다음 내용을 포함한다.

1. 파일의 목적
2. 주요 기능
3. 다른 모듈과의 관계
4. 주요 입력과 출력
5. 사용 시 주의사항

### 3.2 짧은 모듈 예시

```python
"""
보호대상자 추적 상태를 정의하는 열거형 모듈이다.

사람 미검출, 정상 추적, 다중 인물 감지 등 AI 비전에서 사용하는
공통 상태값을 정의하며 외부 라이브러리에 의존하지 않는다.
"""
```

### 3.3 외부 라이브러리 어댑터 예시

```python
"""
Ultralytics YOLO 모델을 이용해 영상 프레임에서 사람을 탐지하는 모듈이다.

OpenCV 형식의 프레임을 입력받아 프로젝트 내부에서 사용하는 탐지 결과 객체로
변환한다. Ultralytics의 결과 객체가 다른 계층으로 노출되지 않도록 변환 책임을
이 모듈에서 담당한다.

이 모듈은 사람 수에 따른 상태 판단이나 로봇 행동 결정은 수행하지 않는다.
"""
```

### 3.4 실행 스크립트 예시

```python
"""
웹캠 영상을 이용해 AI 비전 사람 추적 기능을 확인하는 개발용 실행 스크립트다.

웹캠 프레임을 비전 파이프라인에 전달하고 사람 바운딩 박스, Track ID,
사람 수와 현재 추적 상태를 화면에 표시한다.

운영 환경의 진입점이 아니라 로컬 기능 검증을 목적으로 사용한다.
"""
```

---

## 4. 클래스 docstring 규칙

모든 클래스에는 클래스 선언 직후 한국어 docstring을 작성한다.

### 4.1 클래스 docstring에 포함할 내용

필요한 범위에서 다음 내용을 설명한다.

* 클래스의 주요 책임
* 관리하는 내부 상태
* 입력과 출력
* 다른 클래스와의 관계
* 외부 라이브러리 사용 여부
* 상태를 유지하는 클래스인지 여부
* thread safety 등 중요한 제약사항

### 4.2 간단한 클래스 예시

```python
class TrackedPerson:
    """프레임에서 추적 중인 한 사람의 위치와 추적 정보를 표현한다."""
```

### 4.3 상태를 관리하는 클래스 예시

```python
class PersonStateManager:
    """
    프레임별 유효한 사람 수를 기반으로 보호대상자 추적 상태를 관리한다.

    다중 인물의 순간 오탐으로 로봇 상태가 즉시 변경되지 않도록 연속 검출 횟수를
    누적한다. 다중 인물 상태에서 한 명으로 돌아온 경우에도 설정된 안정화 기간이
    지난 뒤에만 정상 추적 상태로 복귀시킨다.
    """
```

### 4.4 외부 모델을 사용하는 클래스 예시

```python
class YoloPersonDetector:
    """
    YOLO 모델을 이용해 입력 영상에서 사람 클래스만 탐지한다.

    Ultralytics 모델의 생성과 추론을 담당하며, 추론 결과를 프로젝트 내부의
    PersonDetection 객체로 변환한다. 사람 수에 따른 상태 판단은 수행하지 않는다.
    """
```

---

## 5. 함수와 메서드 docstring 규칙

모든 공개 함수와 메서드에는 한국어 docstring을 작성한다.

비공개 함수라도 이름만으로 역할을 파악하기 어렵거나 중요한 정책을 포함한다면 docstring을 작성한다.

### 5.1 기본 작성 형식

Google 스타일 docstring을 기본 형식으로 사용한다.

```python
def calculate_center(
    bbox: tuple[int, int, int, int],
) -> tuple[float, float]:
    """
    바운딩 박스의 화면상 중심 좌표를 계산한다.

    Args:
        bbox: 왼쪽 위와 오른쪽 아래 좌표를 담은
            `(x1, y1, x2, y2)` 형식의 바운딩 박스.

    Returns:
        바운딩 박스 중심의 `(center_x, center_y)` 좌표.
    """
```

### 5.2 상태를 변경하는 메서드 예시

```python
def update(self, person_count: int) -> PersonState:
    """
    현재 프레임의 사람 수를 반영해 추적 상태를 갱신한다.

    한 프레임의 다중 인물 오탐을 즉시 확정하지 않고 연속 검출 횟수를
    확인한다. 다중 인물 상태에서 한 명으로 복귀한 경우에도 안정화 기간이
    끝날 때까지 정상 추적을 허용하지 않는다.

    Args:
        person_count: 현재 프레임에서 유효하다고 판단된 사람 수.

    Returns:
        현재 조건과 이전 상태를 반영한 보호대상자 추적 상태.

    Raises:
        ValueError: 사람 수가 음수인 경우.
    """
```

### 5.3 부작용이 있는 함수 예시

```python
def save_debug_frame(
    frame: np.ndarray,
    output_path: Path,
) -> None:
    """
    디버깅을 위한 영상 프레임을 지정한 경로에 저장한다.

    이 함수는 파일 시스템에 이미지를 생성하며, 기존 파일이 있으면
    동일한 이름의 파일을 덮어쓴다.

    Args:
        frame: BGR 형식의 OpenCV 영상 프레임.
        output_path: 이미지를 저장할 파일 경로.

    Raises:
        OSError: 출력 디렉터리를 생성하거나 파일을 저장하지 못한 경우.
    """
```

### 5.4 생성자 docstring

클래스 docstring으로 책임이 충분히 설명되고 생성자 인자가 명확한 경우
`__init__`에 같은 설명을 반복하지 않아도 된다.

다만 인자의 제약이나 중요한 기본값이 있으면 `__init__`에도 docstring을 작성한다.

---

## 6. 변수와 상수 작성 규칙

### 6.1 변수 이름

변수 이름만으로 역할을 최대한 이해할 수 있어야 한다.

나쁜 예시:

```python
n = 5
c = 0.5
t = 10
```

좋은 예시:

```python
multiple_confirm_frames = 5
confidence_threshold = 0.5
single_recovery_frames = 10
```

---

### 6.2 Boolean 변수

Boolean 변수는 참과 거짓의 의미를 알 수 있게 작성한다.

권장 접두사:

* `is_`
* `has_`
* `can_`
* `should_`
* `allow_`
* `enable_`

예시:

```python
is_person_visible = True
has_valid_track_id = False
can_start_interaction = False
should_publish_debug_image = True
```

다음과 같이 의미가 불분명한 이름은 피한다.

```python
status = True
check = False
flag = True
```

---

### 6.3 상수

변경되지 않는 설정값과 정책값은 대문자 스네이크 표기법을 사용한다.

```python
PERSON_CLASS_ID = 0
DEFAULT_CONFIDENCE_THRESHOLD = 0.5
DEFAULT_MULTIPLE_CONFIRM_FRAMES = 5
```

중요한 상수에는 선정 이유를 설명하는 한국어 주석을 작성한다.

```python
# 한두 프레임의 오탐으로 다중 인물 상태가 확정되지 않도록 사용하는 기본 확인 프레임 수
DEFAULT_MULTIPLE_CONFIRM_FRAMES = 5
```

---

### 6.4 단위가 있는 변수

시간, 거리, 비율처럼 단위가 중요한 변수는 이름에 단위를 포함한다.

```python
sleeping_duration_seconds = 15.0
lost_timeout_seconds = 3.0
camera_width_pixels = 640
movement_distance_pixels = 12.5
confidence_ratio = 0.8
```

단위를 이름에서 알 수 없는 형태는 피한다.

```python
sleep_time = 15
distance = 12.5
timeout = 3
```

---

## 7. 함수 작성 규칙

### 7.1 하나의 책임만 갖게 한다

한 함수에서 다음 작업을 모두 수행하지 않는다.

```text
영상 읽기
→ YOLO 추론
→ 상태 판단
→ 화면 그리기
→ ROS2 메시지 발행
```

기능을 역할별로 분리한다.

```text
read_frame()
detect_people()
track_people()
update_person_state()
draw_debug_overlay()
publish_vision_status()
```

---

### 7.2 함수 길이

함수 길이를 기계적으로 제한하지는 않지만 다음 상황에서는 분리를 검토한다.

* 서로 다른 목적의 코드 블록이 여러 개 존재함
* 중첩 조건문이 세 단계 이상 반복됨
* 함수 설명에 “그리고”가 반복됨
* 테스트하기 어려운 외부 동작과 순수 계산이 섞여 있음
* 동일한 일부 코드가 다른 함수에서도 필요함

---

### 7.3 조기 반환

오류나 예외 조건은 조기 반환을 활용해 정상 흐름의 중첩을 줄인다.

권장 예시:

```python
def convert_tracking_result(result: object) -> list[TrackedPerson]:
    """
    외부 추적 결과를 프로젝트 내부 추적 객체 목록으로 변환한다.

    유효한 바운딩 박스나 Track ID가 없으면 빈 목록을 반환한다.
    """
    if result is None:
        return []

    if result.boxes is None:
        return []

    if result.boxes.id is None:
        return []

    return _build_tracked_people(result.boxes)
```

---

### 7.4 숨겨진 상태 변경 최소화

함수 이름과 반환값으로 상태 변경 여부가 드러나야 한다.

단순 조회 함수 안에서 내부 상태를 변경하지 않는다.

나쁜 예시:

```python
def get_state(self) -> PersonState:
    self.multiple_count += 1
    return self.state
```

좋은 예시:

```python
def update_state(self, person_count: int) -> PersonState:
    ...
```

---

## 8. 클래스 작성 규칙

### 8.1 책임을 분리한다

다음 역할을 하나의 클래스가 모두 담당하지 않는다.

* YOLO 모델 로딩
* ByteTrack 설정
* 사람 수 상태 판단
* 수면 상태 판단
* 화면 출력
* ROS2 Topic 발행

각 클래스는 역할 중심으로 분리한다.

현재 저장소의 실제 분리는 다음과 같다. 새 클래스를 만들 때 이 명명 방식을 따른다.

```text
UltralyticsByteTracker    외부 추적 모델 호출과 결과 변환 (adapters/tracking.py)
OpenCVCamera              프레임 입력 (adapters/opencv.py)
OpenCVDebugView           디버그 화면 (adapters/opencv.py)
UdpFollowView             UDP 송신 + 선택적 디버그 화면 (adapters/udp.py)
PrimaryPersonSelector     여러 명일 때 후보를 한 명으로 줄이는 전처리 (primary_person.py)
UserTrackingService       사람 수 기반 추적 상태 머신 (tracking.py)
FollowCommandGenerator    추종 희망 명령 판단 (follow.py)
run_person_tracking()     위 요소를 조립하는 함수 (application.py)
```

이름의 앞부분이 외부 기술(`Ultralytics`, `OpenCV`, `Udp`)이면 어댑터, 뒷부분이 역할(`Service`, `Generator`, `Selector`)이면 판단 로직이라는 규칙이 자연스럽게 서 있다. 자세·움직임 분석과 수면 상태 관리 클래스는 아직 없으며, 필요해질 때 같은 방식으로 추가한다.

---

### 8.2 데이터 클래스 활용

상태와 결과만 표현하는 객체는 `dataclass` 사용을 우선 검토한다.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class BoundingBox:
    """화면 좌표계의 사람 바운딩 박스를 표현한다."""

    x1: int
    y1: int
    x2: int
    y2: int
```

변경될 필요가 없는 결과 객체는 `frozen=True` 사용을 우선 검토한다.

---

### 8.3 상속보다 조합을 우선한다

단순한 코드 재사용을 위해 복잡한 상속 구조를 만들지 않는다.

다음과 같은 조합을 우선한다.

```python
class VisionPipeline:
    """탐지, 추적, 상태 분석 컴포넌트를 조합해 최종 비전 결과를 생성한다."""

    def __init__(
        self,
        detector: PersonDetector,
        tracker: PersonTracker,
        state_manager: PersonStateManager,
    ) -> None:
        self.detector = detector
        self.tracker = tracker
        self.state_manager = state_manager
```

---

## 9. 타입 힌트 규칙

### 9.1 모든 공개 인터페이스에 타입 힌트를 작성한다

다음 항목에는 타입 힌트를 필수로 작성한다.

* 공개 함수의 인자
* 공개 함수의 반환값
* 클래스 생성자 인자
* 데이터 클래스 필드
* 외부로 노출되는 속성

```python
def track(self, frame: Frame) -> list[TrackedPerson]:
    ...
```

프레임 타입에 `np.ndarray`를 직접 쓰지 않는 것에 주의한다. `ARCHITECTURE.md` §4.3이 `domain` 계층의 `numpy.ndarray` 의존을 금지하므로, 프레임은 어댑터가 정의한 타입 별칭(`Frame`)이나 `object`로 다루고 외부 객체는 `typing.Protocol`로 흉내 낸다.

---

### 9.2 구체적인 타입을 사용한다

가능하면 `Any`, `dict`, `list`만 사용하는 것을 피한다.

나쁜 예시:

```python
def detect(frame: Any) -> list[dict]:
    ...
```

좋은 예시:

```python
def track(self, frame: Frame) -> list[TrackedPerson]:
    ...
```

> **현재 예외 하나가 남아 있다.** `primary_person.py`의 시그니처가 느슨하다 — `select(tracked_people: Sequence, ...) -> Sequence`처럼 제네릭 파라미터가 없고, `_is_candidate(self, person, ...)`·`_center_x_of(person)`은 인자 타입이 아예 없으며 `getattr(person, "confidence", 0.0)` 같은 덕타이핑에 의존한다. mypy의 `disallow_untyped_defs`는 반환 타입만 있으면 통과하므로 이 느슨함은 검사에 잡히지 않는다. 새 코드를 이 파일에 맞추지 말고 위 규칙을 따른다.

### 9.4 외부 객체는 Protocol로 흉내 낸다

Ultralytics 결과 객체처럼 우리가 정의하지 않은 타입은 그대로 import하지 않고 필요한 속성만 `typing.Protocol`로 선언한다(`adapters/detection.py`, `adapters/tracking.py`에 4종이 있다). 그러면 타입 검사를 받으면서도 외부 타입이 계층 경계를 넘지 않는다.

무거운 라이브러리는 **함수·생성자 안에서 지연 import**한다. `ultralytics`를 `__init__` 안에서 import하는 이유는 CLI 파싱과 단위 테스트가 모델 로딩 비용을 치르지 않게 하기 위해서다.

---

### 9.3 선택적 값은 명확하게 표현한다

값이 없을 수 있다면 `None` 가능성을 타입에 포함한다.

```python
current_target: TrackedPerson | None
```

`None`이 어떤 상태를 의미하는지는 docstring이나 데이터 모델에서 설명한다.

---

## 10. Enum과 상태값 작성 규칙

상태를 문자열이나 숫자로 코드 여러 곳에 직접 작성하지 않는다.

나쁜 예시:

```python
if state == "tracking":
    ...
```

좋은 예시:

```python
if status is TrackingResultStatus.TRACKING:
    ...
```

Enum 예시는 저장소의 실제 코드다(`domain/tracking.py`).

```python
from enum import Enum


class TrackingResultStatus(str, Enum):
    """`docs/state-machine.md` §3이 정의한 사람 추적 상태를 표현한다."""

    # 값은 소문자다. 이 문자열이 UDP 페이로드의 status로 그대로 나가는
    # 외부 계약이므로, 대소문자를 바꾸면 수신측(vision_udp_bridge →
    # person_follower)이 조용히 깨진다.
    NOT_DETECTED = "not_detected"
    TRACKING = "tracking"
    TEMPORARILY_LOST = "temporarily_lost"
    MULTIPLE_PENDING = "multiple_pending"
    MULTIPLE_PERSONS = "multiple_persons"
    SINGLE_RECOVERY = "single_recovery"
```

### 10.1 프로세스 밖으로 나가는 문자열의 명명 규칙

이 프로젝트에서 **파이썬 밖으로 나가는 문자열은 UDP 페이로드의 네 필드뿐**이다. 이 값들에는 별도 규칙이 적용된다.

* 필드 이름은 `status` / `command` / `track_id` / `reason` 넷으로 고정이다.
* enum 값은 **소문자 스네이크**다. 멤버 이름(대문자)이 아니라 값이 나간다.
* `reason` 토큰도 소문자 스네이크의 영문이다(`user_far_and_centered` 등 13종). 사람이 읽을 한국어 문장을 여기 넣지 않는다 — 수신측이 분기하는 값이기 때문이다.
* 이 값들을 바꾸는 것은 리팩터링이 아니라 **두 저장소 라인이 공유하는 계약 변경**이다. `robot/ros2_ws/src/core`의 `vision_udp_bridge`·`person_follower`와 함께 바꾼다.

상태 전환 조건은 하나의 상태 관리자 또는 상태 머신에 모은다.

---

## 11. 예외 처리 규칙

### 11.1 예외를 무시하지 않는다

다음과 같이 모든 예외를 조용히 무시하지 않는다.

```python
try:
    load_model()
except Exception:
    pass
```

예외를 처리할 수 없다면 구체적인 정보와 함께 다시 발생시킨다.

```python
try:
    model = YOLO(model_path)
except OSError as error:
    raise ModelLoadError(
        f"YOLO 모델 파일을 불러오지 못했습니다: {model_path}"
    ) from error
```

---

### 11.2 예상 가능한 예외를 구체적으로 처리한다

가능하면 `Exception` 전체보다 예상되는 예외 타입을 처리한다.

```python
except (OSError, ValueError) as error:
    ...
```

최상위 실행 루프처럼 예기치 않은 오류를 안전 상태로 바꿔야 하는 경우에만
포괄적인 예외 처리를 사용한다.

이 경우 반드시 오류를 기록하고 안전한 결과를 반환한다.

---

### 11.3 안전한 기본 결과

AI 비전 처리에 실패한 경우 임의로 정상 상태를 반환하지 않는다.

권장 기본 처리:

```text
person_state = UNKNOWN 또는 NOT_DETECTED
sleep_state = UNKNOWN
interaction_allowed = false
movement_allowed = false
```

**현재 구현은 같은 취지를 정지 명령으로 표현한다.** `sleep_state`·`interaction_allowed`·`movement_allowed`는 아직 존재하지 않는 값이고, 대신 `FollowCommandResult(STOP, reason, None)`이 나간다. 실패 상황을 이유별로 구분하되(`invalid_tracking_result`, `position_missing`, `track_id_missing`) 결과는 언제나 정지다.

실패 상황에서 사용자가 깨어 있다고 가정하거나 대화를 허용하면 안 된다.

### 11.5 `bool`을 `int`로 통과시키지 않는다

파이썬에서 `bool`은 `int`의 하위 타입이라 `isinstance(True, int)`가 참이다. 그래서 사람 수나 포트 번호 검증에 `isinstance(x, int)`만 쓰면 `True`가 `1`로 조용히 통과한다. 이 프로젝트는 정수·실수를 받는 검증 지점마다 `isinstance(x, bool)`을 **먼저** 차단한다.

```python
if isinstance(person_count, bool) or not isinstance(person_count, int):
    raise ValueError("Person count must be a non-negative integer.")
```

검증 실패를 조용히 통과시키지 않기 위한 규칙이며, 도메인 생성자·상태 머신·설정 dataclass·UDP 포트 검증 등 여러 곳에서 같은 형태로 반복된다. 새 검증을 쓸 때도 이 형태를 따른다.

---

### 11.4 예외 메시지

예외 메시지는 문제 원인과 관련 값을 포함해야 한다.

나쁜 예시:

```python
raise ValueError("잘못된 값입니다.")
```

좋은 예시:

```python
raise ValueError(
    f"사람 수는 0 이상이어야 합니다. 입력값: {person_count}"
)
```

---

## 12. 로그 작성 규칙

로그 메시지는 한국어로 작성하며 문제 상황을 재현하는 데 필요한 정보를 포함한다.

### 12.1 로그 수준

* `debug`: 프레임별 세부 상태와 개발용 정보
* `info`: 모델 로딩, 파이프라인 시작, 상태 전환
* `warning`: 일시적 탐지 실패, 다중 인물 감지, 성능 저하
* `error`: 프레임 처리 실패, 모델 추론 실패, 설정 오류
* `critical`: 비전 기능을 계속 실행할 수 없는 오류

### 12.2 좋은 로그 예시

```python
logger.info(
    "보호대상자 추적 상태가 변경되었습니다: %s -> %s",
    previous_state.value,
    current_state.value,
)
```

```python
logger.warning(
    "두 명 이상의 사람이 연속으로 검출되었습니다: person_count=%d, frames=%d",
    person_count,
    multiple_detection_frames,
)
```

### 12.3 피해야 할 로그

프레임마다 동일한 내용을 `info`로 기록해 로그를 과도하게 생성하지 않는다.

반복되는 프레임 정보는 `debug` 수준을 사용하거나 상태가 변경될 때만 기록한다.

---

## 13. 설정값 작성 규칙

모델 경로, 임계값, 프레임 수와 같은 값은 코드에 직접 분산해서 작성하지 않는다.

설정 객체나 명령행 인자로 관리한다.

**현재 이 프로젝트는 YAML 설정 파일을 쓰지 않는다.** `main.build_parser()`의 argparse 인자 12개와 모듈 상수(선정 이유 주석 포함)로 주입하며, 값 검증은 `parse_confidence`·`parse_unit_ratio` 같은 타입 함수가 파싱 시점에 수행한다. 아래 `VisionConfig` 예시는 설정 항목이 늘어 argparse로 감당하기 어려워질 때의 목표 형태이며 **아직 구현하지 않았다** — 이 예시를 보고 존재하지 않는 `VisionConfig`를 찾지 않는다.

현재 실제 형태는 `PrimaryPersonConfig`(`primary_person.py`)에 가깝다. frozen dataclass에 `__post_init__` 검증을 붙이고, 값의 의미와 단위를 클래스 docstring에 적는다.

예시(목표 형태):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class VisionConfig:
    """AI 비전 파이프라인 실행에 필요한 설정값을 관리한다."""

    model_path: str
    confidence_threshold: float
    image_size: int
    multiple_confirm_frames: int
    single_recovery_frames: int
```

설정값은 시작 시 검증한다.

```python
def validate(self) -> None:
    """설정값이 허용 범위에 있는지 검증한다."""
    if not 0.0 <= self.confidence_threshold <= 1.0:
        raise ValueError(
            "confidence_threshold는 0.0 이상 1.0 이하여야 합니다."
        )
```

---

## 14. 테스트 코드 작성 규칙

### 14.1 테스트 파일 상단

테스트 파일에도 한국어 모듈 docstring을 작성한다.

```python
"""
보호대상자 사람 수 상태 머신의 전환 규칙을 검증하는 단위 테스트 모듈이다.

외부 모델이나 영상 입력 없이 사람 수 시퀀스를 직접 전달해
다중 인물 확인과 한 명 복귀 안정화 동작을 검증한다.
"""
```

---

### 14.2 테스트 함수 docstring

모든 테스트 함수에는 어떤 상황과 결과를 검증하는지 한국어 docstring을 작성한다. `scripts/check_korean_docstrings.py`가 이 규칙을 기계적으로 검사하며, `make check-docstrings`(따라서 `make check`)가 이를 선행 의존으로 건다.

```python
def test_multiple_people_are_confirmed_after_threshold() -> None:
    """두 명 이상이 기준 프레임만큼 지속되면 다중 인물 상태가 되는지 검증한다."""
```

> **현재 상태: 이 규칙을 어긴 파일이 하나 있다.** `tests/test_primary_person.py`의 테스트 20개와 가짜 클래스·메서드에 docstring이 없어 검사가 34건의 위반으로 실패하고, `make check`도 함께 실패한다. 이 파일은 다른 규약으로 나중에 추가된 흔적이다. 정리 전까지는 **"내 변경이 새 위반을 추가하지 않았는가"**를 완료 판정 기준으로 삼는다. 검사 실패를 자기 변경 탓으로 오해하지 않도록 여기 기록해 둔다.

---

### 14.3 테스트 구성

테스트는 가능하면 다음 세 단계가 드러나게 작성한다.

```text
Given: 테스트 전제와 입력 준비
When: 검증할 동작 수행
Then: 기대 결과 확인
```

주석으로 반드시 `Given`, `When`, `Then`을 작성할 필요는 없지만 코드 구조에서 구분돼야 한다.

예시:

```python
def test_single_person_recovers_after_stable_frames() -> None:
    """다중 인물 상태 이후 한 명이 안정적으로 유지되면 정상 추적으로 복귀하는지 검증한다."""
    state_manager = PersonStateManager(
        multiple_confirm_frames=2,
        single_recovery_frames=3,
    )

    state_manager.update(2)
    state_manager.update(2)

    recovery_states = [
        state_manager.update(1),
        state_manager.update(1),
        state_manager.update(1),
    ]

    assert recovery_states == [
        PersonState.SINGLE_RECOVERY,
        PersonState.SINGLE_RECOVERY,
        PersonState.TRACKING,
    ]
```

---

### 14.4 외부 의존성 사용 제한

단위 테스트에서는 다음 작업을 수행하지 않는다.

* 실제 YOLO 모델 다운로드
* GPU 사용
* 인터넷 요청
* 실제 카메라 접근
* ROS2 실행
* 대용량 영상 처리

외부 모델과 카메라 입력은 mock, fake 또는 fixture로 대체한다.

실제 영상과 모델을 사용하는 검증은 통합 테스트 또는 별도의 eval에서 수행한다.

---

## 15. 주석 작성이 필요한 위치

다음 위치에는 한국어 주석을 우선 작성한다.

### 15.1 안전 정책

```python
# 다중 인물 상황에서는 보호대상자를 특정할 수 없으므로 임의의 대상을 선택하지 않는다.
if person_count >= 2:
    return PersonState.MULTIPLE_PERSONS
```

### 15.2 상태 안정화

```python
# 다중 인물 상태가 해제된 직후 잘못된 대상 추적을 재개하지 않도록 한 명 상태를 추가 확인한다.
if self.single_recovery_frames < self.required_recovery_frames:
    return PersonState.SINGLE_RECOVERY
```

### 15.3 외부 라이브러리 한계 보완

```python
# ByteTrack은 최초 탐지 직후 Track ID를 제공하지 않을 수 있으므로 ID가 없는 결과는 제외한다.
if boxes.id is None:
    return []
```

### 15.4 좌표와 단위

```python
# 중심 좌표는 원본 프레임 픽셀 좌표계를 기준으로 계산한다.
center_x = (x1 + x2) / 2
```

### 15.5 임계값 선정 이유

```python
# 시연 환경에서는 짧은 시간 안에 상태 전환을 확인할 수 있도록 운영 기본값보다 낮게 설정한다.
DEMO_SLEEPING_DURATION_SECONDS = 15.0
```

---

## 16. 주석을 작성하지 않아도 되는 위치

이름과 코드만으로 의미가 명확한 경우에는 주석을 생략한다.

불필요한 예시:

```python
people = []  # 빈 사람 리스트를 생성한다.

for person in people:  # people을 반복한다.
    print(person)  # person을 출력한다.
```

간단한 데이터 할당이나 반복문까지 모두 설명하면 중요한 주석을 찾기 어려워진다.

주석은 다음 질문에 답할 가치가 있을 때 작성한다.

* 왜 이 방식으로 처리하는가?
* 왜 이 값이 필요한가?
* 이 조건이 서비스에 어떤 영향을 미치는가?
* 이 코드를 변경할 때 무엇을 주의해야 하는가?

---

## 17. 금지되는 코드 작성 방식

다음 방식은 사용하지 않는다.

### 17.1 의미 없는 이름

```python
a = 5
tmp = result
data = process()
flag = True
```

### 17.2 하드코딩된 상태 문자열

```python
if state == "sleep":
    ...
```

### 17.3 여러 역할이 섞인 거대한 함수

```python
def run_everything():
    # 카메라 입력, 추론, 상태 판단, 화면 출력, ROS2 발행을 모두 처리
    ...
```

### 17.4 오류 무시

```python
except Exception:
    pass
```

### 17.5 실제 동작과 다른 오래된 주석

코드를 변경했다면 관련 주석과 docstring도 반드시 함께 갱신한다.

> **저장소에 실물 위반이 하나 있다.** `main.py`의 `--confidence` 도움말 문자열이 `(default: 0.5)`를 출력하지만 실제 기본값은 `DEFAULT_CONFIDENCE = 0.8`이다. 사용자가 `--help`로 보는 값과 실제 동작이 다르다. 그 파일을 고칠 일이 생기면 함께 정리한다.

### 17.6 코드 번역형 주석

```python
count += 1  # count를 증가시킨다.
```

### 17.7 미래를 위한 불필요한 추상화

현재 요구사항에 없는 모델 지원, 여러 사용자 구별, 다중 카메라 기능 등을
미리 구현하지 않는다.

---

## 18. 코드 작성 완료 전 점검표

코드 작업을 완료하기 전에 다음 항목을 확인한다. 마크다운 체크박스이므로 그대로 복사해 MR 본문에 붙여 쓰면 된다.

### 파일

* [ ] 모든 신규 Python 파일에 한국어 모듈 docstring이 있는가?
* [ ] 모듈의 목적과 책임이 명확한가?
* [ ] 다른 계층과의 관계가 필요한 경우 설명돼 있는가?

### 클래스

* [ ] 모든 신규 클래스에 한국어 docstring이 있는가?
* [ ] 클래스가 하나의 명확한 책임을 갖는가?
* [ ] 관리하는 상태와 외부 의존성이 설명돼 있는가?

### 함수와 메서드

* [ ] 모든 공개 함수와 메서드에 한국어 docstring이 있는가?
* [ ] 인자와 반환값이 필요한 수준으로 설명돼 있는가?
* [ ] 예외와 부작용이 있다면 설명돼 있는가?
* [ ] 함수가 너무 많은 책임을 갖고 있지 않은가?

### 변수와 설정값

* [ ] 중요한 임계값과 상태값의 목적이 설명돼 있는가?
* [ ] 시간과 거리 변수에 단위가 포함돼 있는가?
* [ ] Boolean 변수의 참과 거짓 의미가 명확한가?
* [ ] 환경별 설정값이 하드코딩돼 있지 않은가?

### 주석

* [ ] 주석이 코드의 의도와 이유를 설명하는가?
* [ ] 코드 내용을 단순히 번역한 주석이 없는가?
* [ ] 실제 코드 동작과 일치하지 않는 주석이 없는가?
* [ ] 너무 많은 주석으로 코드 흐름을 방해하지 않는가?

### 안정성

* [ ] 오류를 조용히 무시하지 않는가?
* [ ] 불확실한 결과를 안전하게 처리하는가?
* [ ] 다중 인물 상황에서 임의의 보호대상자를 선택하지 않는가?
* [ ] 수면 상태를 의료적 진단처럼 표현하지 않는가?

### 검증

* [ ] 포맷 검사를 실행했는가? (`make format-check`)
* [ ] 린트 검사를 실행했는가? (`make lint`)
* [ ] 한국어 docstring 검사를 실행했는가? (`make check-docstrings` — 기존 34건 외에 **새 위반이 없는지** 본다. §14.2 참고)
* [ ] 관련 단위 테스트를 실행했는가? (`make test` — `make test-unit`은 마커 없는 테스트를 수집하지 않는다)
* [ ] 관련 통합 테스트를 실행했는가?

`make check`는 `check-docstrings` 실패 때문에 현재 통과하지 않는다. 이 점검표를 문자 그대로 지키려다 막히면 §14.2의 기준을 적용한다.
