# S15P11E102-213 사람 추적 상태 머신 구현 계획

## 목표

`docs/state-machine.md`가 정의한 6개 사람 추적 상태와 §10 전환표를 그대로 구현한다.

현재 `UserTrackingService`는 상태를 저장하지 않고 사람 수만으로 결과를 즉석 계산해
`MULTIPLE_PENDING`과 `SINGLE_RECOVERY`를 표현할 수 없고, 두 명 이상이 검출되면 완충 없이
곧바로 확정 상태로 전환한다. 이번 작업에서 현재 상태를 명시적으로 보관하고 히스테리시스
카운터를 적용해 문서와 코드의 동작을 일치시킨다.

## 대상 상태

```text
NOT_DETECTED
TRACKING
TEMPORARILY_LOST
MULTIPLE_PENDING
MULTIPLE_PERSONS
SINGLE_RECOVERY
```

## 입력과 출력 계약

- 입력: 현재 프레임의 `Sequence[TrackedPerson]`, 프레임 너비·높이
- 상태 입력: 0 이상의 정수 사람 수(음수·비정수·`None`은 거부)
- 출력: `TrackingResult(status, person_count, track_id, position)`
- `TRACKING`에서만 대표 Track ID와 위치를 제공한다. 나머지 5개 상태는 항상 `None`이다.

## 상태 전환 규칙(`docs/state-machine.md` §10)

| 현재 상태            | 0명                                     | 1명                            | 2명 이상                 |
| ---------------- | -------------------------------------- | ----------------------------- | -------------------- |
| NOT_DETECTED     | `NOT_DETECTED`                         | `TRACKING`                    | `MULTIPLE_PENDING`   |
| TRACKING         | `TEMPORARILY_LOST`(허용 초과 시 `NOT_DETECTED`) | `TRACKING`                    | `MULTIPLE_PENDING`   |
| TEMPORARILY_LOST | 허용 내 `TEMPORARILY_LOST`, 초과 시 `NOT_DETECTED` | `TRACKING`                    | `MULTIPLE_PENDING`   |
| MULTIPLE_PENDING | 직전 단일 대상 이력이 있으면 `TEMPORARILY_LOST`, 없으면 `NOT_DETECTED` | `TRACKING`                    | 확인 완료 시 `MULTIPLE_PERSONS` |
| MULTIPLE_PERSONS | `NOT_DETECTED`                         | `SINGLE_RECOVERY`             | `MULTIPLE_PERSONS`   |
| SINGLE_RECOVERY  | `NOT_DETECTED`                         | 안정화 완료 시 `TRACKING`           | `MULTIPLE_PERSONS`   |

비상 탈출 전환(0명 또는 2명 이상)은 모든 상태에서 위 표대로 처리한다.

## 히스테리시스 카운터

- `lost_tolerance_frames`: 연속 0명 프레임이 이 값을 초과하면 `NOT_DETECTED`로 폐기한다.
- `multiple_confirm_frames`: 연속 2명 이상 프레임이 이 값에 도달하면 다중 인물을 확정한다.
- `single_recovery_frames`: 연속 1명 프레임이 이 값에 도달하면 정상 추적으로 복귀한다.

세 값 모두 생성자 인자로 주입하며 상태 머신 내부에 하드코딩하지 않는다
(`docs/state-machine.md` §25, `docs/vision-requirements.md` §8.3, `AGENTS.md` §7).

## 작업 범위

1. `domain/tracking.py`
   - `TrackingResultStatus`에 `MULTIPLE_PENDING`, `SINGLE_RECOVERY`를 추가한다.
   - `NOT_FOUND` → `NOT_DETECTED`, `MULTIPLE_PEOPLE` → `MULTIPLE_PERSONS`로 문서 기준 정합화한다.
   - `TrackingResult.__post_init__`의 상태별 사람 수·대표 대상 검증을 6개 상태로 확장한다.
2. `tracking.py`
   - 현재 상태를 `self._state`로 보관하고 초기값을 `NOT_DETECTED`로 둔다.
   - 사람 수만 입력받는 `update_state()`로 §10 전환표를 구현하고, `update()`는 그 결과에
     대표 위치를 붙이는 책임만 담당한다.
   - 세 개의 히스테리시스 카운터와 직전 단일 대상 이력을 관리한다.
3. `main.py`
   - `--multiple-confirm-frames`, `--single-recovery-frames` 옵션과 파서를 추가한다.
   - 기본값 상수에 선정 근거를 한국어 주석으로 남긴다.
4. 호출부 정합화
   - `follow.py`: 이름 변경 반영, `MULTIPLE_PENDING`과 `SINGLE_RECOVERY`도 명시적으로 정지 처리한다.
   - `adapters/opencv.py`: 이름 변경 반영, 완충 다중 인물 상태에서도 사람 수를 표시한다.
5. 테스트: `tests/unit/test_tracking.py`에 §24 시나리오를 추가하고, 이름·생성자 변경을
   `tests/unit/test_follow.py`, `tests/integration/test_position_pipeline.py`에 반영한다.
6. `README.md`의 상태 설명과 실행 옵션을 현재 동작에 맞춘다.

## 제외 범위

사용자 상태(`UNKNOWN`/`AWAKE`/`RESTING`/`SLEEPING_ESTIMATED`), 수면·휴식 판단, 능동 대화
허용 여부, 이동 허용 플래그, 상태 판단 이유 필드, 시간 기반 전환, ROS2 연동, Re-ID는
이번 범위에 포함하지 않는다. `position.py`와 `VisionResultStatus` 계약도 변경하지 않는다.

## 기본값과 근거

| 설정                        | 기본값 | 근거                                                                 |
| ------------------------- | --- | ------------------------------------------------------------------ |
| `lost_tolerance_frames`   | 3   | 기존 값 유지. 30 FPS 기준 약 0.1초의 순간 누락을 흡수한다.                             |
| `multiple_confirm_frames` | 5   | `docs/code-style.md` §6.3의 예시값. 30 FPS 기준 약 0.17초로 순간 오탐을 흡수한다.     |
| `single_recovery_frames`  | 10  | `docs/code-style.md` §6.1의 예시값. 잘못된 대상 추적 재개를 막기 위해 확인 값보다 길게 잡는다.  |

실제 기본값은 카메라 FPS와 영상 검증 후 조정한다(`docs/state-machine.md` §26).

## 테스트 계획

`docs/state-machine.md` §24 시나리오를 YOLO·ByteTrack·OpenCV 없이 사람 수만으로 검증한다.

- 기본 탐지: 초기 `NOT_DETECTED`, 0명 유지, 1명 → `TRACKING`
- 일시적 추적 실패: `TRACKING` → 0명 → `TEMPORARILY_LOST`, 허용 내 복귀, 허용 초과 시 `NOT_DETECTED`
- 다중 인물 확인: `TRACKING` → 2명 → `MULTIPLE_PENDING`, 확인 전 1명 복귀, 확인 후 `MULTIPLE_PERSONS`
- 한 명 복귀: `MULTIPLE_PERSONS` → 1명 → `SINGLE_RECOVERY`, 안정화 후 `TRACKING`, 도중 2명 재검출
- 비상 탈출: `TEMPORARILY_LOST`에서 2명, `MULTIPLE_PENDING`에서 0명(이력 유무별), 확정·복귀 상태에서 0명
- 안전 규칙: `TRACKING`이 아닌 모든 상태에서 `track_id`와 `position`이 `None`
- 잘못된 입력: 음수·비정수 사람 수, 1 미만·비정수 설정값, 잘못된 Track ID와 박스

## 완료 조건

- `docs/state-machine.md` §10 전환표와 §24 시나리오, `docs/vision-requirements.md` §13.3
  수용 기준을 모두 만족한다.
- `TRACKING` 외 상태에서 대표 Track ID와 위치를 제공하지 않는다.
- 임계값이 코드에 하드코딩되지 않고 명령행으로 조정 가능하다.
- `make check`(format-check, lint, type-check, check-docstrings, test)가 통과한다.

## 결정 사항

### 1. 상태 이름은 문서를 따른다

코드의 `NOT_FOUND`, `MULTIPLE_PEOPLE`은 `docs/state-machine.md` §3, §10과
`docs/vision-requirements.md` §4.4가 정의한 `NOT_DETECTED`, `MULTIPLE_PERSONS`와 다르다.

`AGENTS.md` §3에 따라 기존 요구사항 문서를 우선해 코드 이름을 문서 기준으로 변경한다.
`vision-requirements.md` §1도 "코드를 기준으로 문서를 변경하지 않는다"고 규정한다.

영향: `follow.py`, `adapters/opencv.py`, `tests/unit/test_follow.py`,
`tests/integration/test_position_pipeline.py`의 참조를 기계적으로 갱신한다. 판정 로직과
기대 동작은 바꾸지 않는다.

### 2. `VisionResultStatus`는 변경하지 않는다

`domain/position.py`의 `VisionResultStatus.NOT_FOUND`, `MULTIPLE_PEOPLE`은 상태 머신이 아니라
한 프레임의 위치 계산 결과 계약이며 이번 이슈 범위 밖이다. 두 열거형의 이름 규칙이 당분간
달라지는 점은 아래 미해결 항목으로 남긴다.

### 3. Enum 문자열 값은 소문자를 유지한다

`docs/code-style.md` §10 예시는 `NOT_DETECTED = "NOT_DETECTED"` 형태를 사용하지만, 이 저장소의
`FollowCommand`와 `VisionResultStatus`는 소문자 값을 사용하고 디버그 화면이 `status.value`를
그대로 출력한다. 멤버 이름만 문서 기준으로 맞추고 문자열 값은 기존 규칙을 유지한다.

### 4. 한 프레임으로 확정·복귀하지 않는다

`multiple_confirm_frames`나 `single_recovery_frames`가 `1`이어도 다중 인물 검출 첫 프레임은
항상 `MULTIPLE_PENDING`, 다중 인물 해제 첫 프레임은 항상 `SINGLE_RECOVERY`로 처리한다.

근거: `docs/vision-requirements.md` §4.6.1은 한 프레임의 다중 인물 검출로 즉시 확정 상태에
가지 않도록, §4.6.6은 다시 한 명이 되더라도 즉시 정상 추적으로 복귀하지 않도록 요구한다.
`docs/state-machine.md` §2.1의 단일 프레임 확정 금지 원칙과도 일치한다.

### 5. 카운터 도달 시점

`docs/code-style.md` §14.3 예시(`single_recovery_frames=3` → `SINGLE_RECOVERY`,
`SINGLE_RECOVERY`, `TRACKING`)에 맞춰, 설정값에 **도달하는** 프레임에서 전환한다.

### 6. `MULTIPLE_PENDING`에서 0명이 된 경우

`docs/state-machine.md` §7.5에 따라 다중 인물 진입 전에 단일 대상을 추적하던 이력이 있으면
`TEMPORARILY_LOST`로, 없으면 `NOT_DETECTED`로 전환한다. 이때 일시 누락 관찰 창은 다시
시작한다. `TEMPORARILY_LOST`는 대표 대상을 제공하지 않는 완충 상태이므로 창을 다시
시작해도 안전 정책이 완화되지 않는다.

## 미해결 / 결정 필요

1. **`SINGLE_RECOVERY`에서 2명 이상 재검출 시 전이 대상이 문서 안에서 충돌한다.**
   `docs/state-machine.md` §9.5와 §10 요약도는 `MULTIPLE_PERSONS`로,
   같은 문서 §7.2는 `SINGLE_RECOVERY`를 `MULTIPLE_PENDING` 진입 가능 상태로 기술한다.
   이번 구현은 이슈에 명시된 §10 전환표를 우선해 `MULTIPLE_PERSONS`로 전이한다.
   §7.2 문장의 수정 여부는 문서 담당자의 확인이 필요하다.
2. **설정 검증 하한과 안전 원칙이 충돌한다.**
   `docs/vision-requirements.md` §9.4는 "확인 프레임 수가 1 미만"만 잘못된 설정으로 규정해
   `1`을 허용하지만, §4.6.1과 §2.1은 한 프레임 확정을 금지한다. 검증 하한은 문서대로 `1`로
   두고, 결정 사항 4의 완충 규칙으로 안전 원칙을 만족시킨다.
3. **`docs/vision-requirements.md` §7.3의 상태 판단 이유와 §7.4의 출력 형식이 아직 계약에 없다.**
   현재 `TrackingResult`에는 `reason`, `interaction_allowed`, `movement_allowed`가 없고 §7.4
   예시는 대문자 상태 문자열을 사용한다. 최종 비전 결과 계약을 정의하는 별도 이슈에서
   다루며, 이번 이슈에서 임의로 추가하지 않는다.
4. **`follow.py`의 판단 이유 문자열은 기존 값을 유지한다.**
   상태 이름은 `MULTIPLE_PERSONS`로 바뀌지만 추종 명령 이유는 기존 계약과 README를 유지하기
   위해 `multiple_people_detected`를 그대로 사용한다. 문자열 정합화가 필요하면 추종 명령
   계약 변경 이슈에서 처리한다.
5. **예외 메시지 언어가 문서와 다르다.**
   `docs/code-style.md` §11.4 예시는 한국어 예외 메시지를 사용하지만 현재 코드베이스는 영어
   메시지로 통일돼 있고 기존 테스트가 영어 문구를 검증한다. 이번 작업은 기존 코드 규칙을
   따르며, 언어 통일은 별도 이슈에서 일괄 처리해야 한다.
6. 프레임 수 기준과 시간 기준 중 무엇을 주 전환 기준으로 삼을지는 실제 FPS 측정 후 결정한다
   (`docs/state-machine.md` §26). 이번 구현은 프레임 수 기준만 사용한다.
7. 기본값 `5`, `10`은 문서 예시에서 가져온 초기값이며 실제 카메라 검증으로 조정해야 한다.

## 검증 결과

`make check`(format-check, lint, type-check, check-docstrings, test)를 프로젝트 `venv`에서
실행해 모두 통과했다. 단위·통합 테스트 171개가 통과했고 타입 검사 대상 17개 파일에서
오류가 없었다.

검증 환경 참고: `venv`의 editable 설치가 이전 프로젝트 경로(`Desktop\bomi\...`)를 가리키고
있어 모든 테스트가 `ModuleNotFoundError`로 실패했다. 이번 변경과 무관한 환경 문제이며
`python -m pip install -e . --no-deps --no-build-isolation`으로 현재 경로에 다시 연결했다.
의존성 버전은 변경하지 않았다.

검증하지 못한 항목:

- 실제 카메라와 YOLO·ByteTrack을 사용한 전환 품질과 기본 프레임 수의 적절성
- 실제 처리 FPS 기준의 체감 지연시간

## 변경 요약(리뷰용)

| 파일                                        | 변경 내용                                              |
| ----------------------------------------- | -------------------------------------------------- |
| `src/bomi_vision/domain/tracking.py`      | 상태 2개 추가, 상태 이름 정합화, 6개 상태 일관성 검증                   |
| `src/bomi_vision/tracking.py`             | 명시적 상태 보관과 §10 전환표, 히스테리시스 카운터 3종                   |
| `src/bomi_vision/main.py`                 | 확인·복귀 프레임 수 CLI 옵션과 기본값 근거 주석                       |
| `src/bomi_vision/follow.py`               | 상태 이름 반영, 신규 완충 상태 정지 처리                            |
| `src/bomi_vision/adapters/opencv.py`      | 상태 이름 반영, 완충 다중 인물 상태 사람 수 표시                       |
| `tests/unit/test_tracking.py`             | §24 시나리오 전체와 안전 규칙·잘못된 입력 검증                        |
| `tests/unit/test_main.py`                 | 신규 명령행 옵션 파서 검증                                     |
| `tests/unit/test_follow.py`               | 상태 이름 반영, 신규 완충 상태 정지 검증                            |
| `tests/integration/test_position_pipeline.py` | 생성자 인자 반영                                       |
| `README.md`                               | 상태 설명과 실행 옵션 갱신                                     |
