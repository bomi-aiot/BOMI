"""회전 탐색의 순수 판단 로직 — "지금 얼마나 돌아야 하는가"만 계산한다.

왜 노드와 분리하는가
    ROS 2 나 하드웨어 없이 각도 계산과 상태 전이를 테스트할 수 있어야 한다
    (robot/AGENTS.md §3 "하드웨어 접근과 순수 로직을 분리해 순수 로직을
    하드웨어 없이 테스트할 수 있게 한다"). 각도 wrap-around(359° 다음이 0°)는
    실기에서 눈으로 확인하기 어려운 종류의 버그라, 여기서 단위 테스트로 막는다.

무엇을 하고 무엇을 하지 않는가
    한다:   현재 yaw 와 경과 시간을 받아 목표 각속도, 추종 스위치, 종료 여부를
            돌려준다.
    안 한다: ROS 발행, 시간 측정, 로그, 하드웨어 접근. 전부 호출부(wake_search
            노드)가 맡는다. 이 모듈은 시계조차 갖지 않고 now_sec 을 받는다.

탐색 대본 (CLAUDE.md 보미야 호출 대본 / 구현계획 §0, 2026-08-08 실기 개정)
    1. 소리 방향 힌트가 있으면 그쪽으로 먼저 돈다 (TURN_TO_HINT).
    2. 멈춰서 관찰한다 (OBSERVE). 카메라가 사람을 확정할 시간을 준다.
    3. 못 찾으면 힌트 방향을 중심으로 좌우 지그재그로 한 스텝씩 넓혀가며
       본다 — **힌트로 돈 방향을 먼저 잇는다**(예: 오른쪽에서 불렀으면
       오른쪽으로 한 스텝 더) → 반대쪽 → 먼저 방향으로 2스텝 → 반대쪽으로
       2스텝 → …. 마이크 방향 추정은 완벽하지 않으니 "대충 그 근처"부터
       촘촘히 본다 — 실기에서 힌트를 무시하고 바로 전체 회전부터
       시작하는 것처럼 보인다는 피드백으로 추가됐다. 처음엔 항상 왼쪽부터
       봐서, 오른쪽에서 불렀을 때는 오히려 반대편(중앙 쪽)부터 보는
       것처럼 느껴진다는 후속 피드백으로 힌트 방향을 따라가도록 고쳤다.
       local_search_max_steps 가 이 좌우 탐색을 몇 차까지 할지다.
    4. 좌우 탐색 폭을 다 써도 못 찾으면, 그 시점 방향에서부터 한 방향으로
       계속 스텝 회전하는 기존 방식으로 넘어간다(STEP_TURN → OBSERVE).
       sweep_limit_deg 만큼 돌아 한 바퀴를 다 보면 원래 방향으로 복귀한다
       (RETURNING). 복귀 여부는 return_to_start 로 끈다.
    5. 힌트가 없으면 1~3 을 건너뛰고 4 부터 시작한다(비교 기준이 없으니
       좌우를 구분할 수 없다).
    6. 도중에 사람을 찾으면 즉시 회전을 멈추고 추종을 켠다 (FOLLOWING).
       그 뒤로 사람 앞까지 다가가 서는 것은 이 모듈이 아니라 person_follower
       의 몫이다(비전 결과로 거리·좌우 오차를 계산해 접근·정지).

왜 연속 회전이 아니라 스텝 회전인가
    ai_vision 은 "연속 프레임 수"로 추적을 확정한다. 계속 돌면 모션 블러와
    프레임 이탈로 확정이 잘 안 된다. 조금 돌고 멈춰서 보는 편이 실제 발견율이
    높고, 사람 눈에도 두리번거리는 것처럼 자연스럽다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

# 각도 정규화에 반복해서 쓰는 상수.
TWO_PI = 2.0 * math.pi

# 부동소수점 비교 여유. 각도(라디안)와 누적 회전량 비교에 함께 쓴다.
_EPSILON = 1e-9


def normalize_angle(radians: float) -> float:
    """각도를 -pi ~ +pi 범위로 접는다.

    역할: 359°와 1°가 2° 차이라는 사실을 계산이 알게 한다. 단순 뺄셈으로
        각도를 비교하면 358° 차이로 읽혀 로봇이 반대로 한 바퀴 돈다.
    입력값: radians - 임의의 각도(라디안). 유한한 값이어야 한다.
    반환값: -pi 이상 pi 이하로 접힌 각도.
    실패: 유한하지 않은 값이면 ValueError.
    """
    if isinstance(radians, bool) or not isinstance(radians, (int, float)):
        raise ValueError("angle must be a real number")
    if not math.isfinite(radians):
        raise ValueError("angle must be finite")
    wrapped = math.fmod(float(radians) + math.pi, TWO_PI)
    if wrapped < 0.0:
        wrapped += TWO_PI
    return wrapped - math.pi


def angle_error(target_rad: float, current_rad: float) -> float:
    """현재 각도에서 목표 각도까지의 최단 회전량을 구한다.

    역할: 부호가 곧 회전 방향이다. 양수면 반시계(왼쪽), 음수면 시계(오른쪽).
    입력값: target_rad - 목표 yaw. current_rad - 현재 yaw. 둘 다 라디안.
    반환값: -pi ~ +pi 범위의 회전량(라디안).
    """
    return normalize_angle(target_rad - current_rad)


class SearchState(str, Enum):
    """회전 탐색의 상태.

    IDLE        아직 시작하지 않았다. 속도를 내지 않는다.
    TURN_TO_HINT 소리 방향 힌트로 회전 중이다.
    OBSERVE     멈춰서 카메라가 사람을 확정하기를 기다린다.
    STEP_TURN   다음 관찰 지점까지 한 스텝 회전 중이다.
    RETURNING   못 찾아서 시작 방향으로 복귀 중이다.
    FOLLOWING   사람을 찾아 추종에 넘겼다. 이 노드는 더 이상 속도를 내지 않는다.
    FINISHED    끝났다. 성공(추종 종료)이든 실패(미발견)든 여기로 모인다.
    """

    IDLE = "idle"
    TURN_TO_HINT = "turn_to_hint"
    OBSERVE = "observe"
    STEP_TURN = "step_turn"
    RETURNING = "returning"
    FOLLOWING = "following"
    FINISHED = "finished"


@dataclass(frozen=True)
class SearchDecision:
    """한 번의 판단 결과.

    angular_z: 발행할 목표 각속도(rad/s). 정지는 0.0 이다.
    follow_enable: 추종 스위치를 바꿔야 하면 True/False, 그대로 두면 None.
    state: 판단 직후의 상태.
    reason: 사람이 로그에서 읽을 판단 근거.
    finished: 이번 판단으로 탐색이 끝났으면 True.
    """

    angular_z: float
    follow_enable: bool | None
    state: SearchState
    reason: str
    finished: bool


@dataclass(frozen=True)
class SearchConfig:
    """탐색 파라미터. 단위와 근거를 값 옆에 남긴다.

    기본값 근거 (robot/docs 및 실측)
        step_angle_deg 40   카메라 화각 58°에서 가장자리 왜곡을 뺀 유효 화각을
                            45°로 보고, 5° 겹침을 남긴 값이다. 키우면 빨라지지만
                            경계에 선 사람을 건너뛴다.
        angular_speed 0.6   pico_driver.yaml 의 실측값(트레드 0.278 m,
                            최대 0.8 rev/s)에서 나오는 제자리 회전 물리 한계는
                            약 1.11 rad/s 다. 그 55% 로 안전 여유를 둔다.
        observe_duration_sec 0.8
                            person_follower 의 target_confirm_sec(0.5초)보다
                            여유 있게 잡는다. 줄이면 발견율이 떨어진다.
        sweep_limit_deg 320  40°씩 8스텝이면 관찰 지점이 9곳(0·40·…·320°)이 되어
                            360°를 모두 덮는다. 360으로 두면 마지막 스텝이 첫
                            관찰 지점과 겹쳐 0.8초를 낭비한다.
        local_search_max_steps 2
                            힌트를 중심으로 좌우 지그재그를 몇 스텝까지 볼지
                            (1차 ±1스텝, 2차 ±2스텝, …). 2026-08-08 실기
                            피드백으로 "1차, 2차, 그다음 전체 회전"으로
                            명시적으로 굳혔다 — 도(度) 폭으로 계산하면
                            step_angle_deg 를 바꿀 때마다 몇 차까지 도는지
                            같이 흔들려서 스텝 수로 직접 정한다. 힌트가
                            없으면 쓰이지 않는다.
        step_min_angular_speed 0.3, step_slowdown_band_deg 10
                            STEP_TURN(지그재그·전체 회전)의 감속 하한과
                            감속 시작 각도. TURN_TO_HINT 용
                            min_angular_speed/slowdown_band_deg 를 그대로
                            같이 쓰면 40° 짜리 스텝의 62%(25°/40°) 구간을
                            감속만 하다 끝나 "전체 회전이 너무 느리다"는
                            불만으로 이어졌다(2026-08-08 실기). 힌트 회전은
                            한 번뿐이라 정밀 착지가 중요하지만, 스텝은
                            어차피 다음 관찰 지점일 뿐이라 goal_tolerance_deg
                            안에서만 짧게 감속해도 된다.
        follow_timeout_sec 60
                            추종을 켜 둔 채로 둘 최대 시간(구현계획 결정 C).
        search_timeout_sec 45
                            최악 시나리오(힌트 180° + 9관찰 + 8스텝 + 복귀
                            180°)가 약 23초다. 그 두 배 가까이를 상한으로 둔다.
    """

    step_angle_deg: float = 40.0
    angular_speed: float = 0.6
    min_angular_speed: float = 0.15
    slowdown_band_deg: float = 15.0
    step_min_angular_speed: float = 0.3
    step_slowdown_band_deg: float = 10.0
    goal_tolerance_deg: float = 3.0
    observe_duration_sec: float = 0.8
    sweep_limit_deg: float = 320.0
    local_search_max_steps: int = 2
    hint_max_age_sec: float = 10.0
    follow_timeout_sec: float = 60.0
    search_timeout_sec: float = 45.0
    return_to_start: bool = True

    def __post_init__(self) -> None:
        """단위와 허용 범위를 시작 시점에 검증한다.

        왜 여기서 죽는가: 잘못된 값은 실기에서 "왜 안 돌지"로 나타난다.
        노드가 뜨는 순간 죽는 편이 원인을 찾기 쉽다(robot/AGENTS.md §4).
        """
        _require_positive(self.step_angle_deg, "step_angle_deg")
        _require_positive(self.angular_speed, "angular_speed")
        _require_positive(self.min_angular_speed, "min_angular_speed")
        _require_positive(self.slowdown_band_deg, "slowdown_band_deg")
        _require_positive(
            self.step_min_angular_speed, "step_min_angular_speed")
        _require_positive(
            self.step_slowdown_band_deg, "step_slowdown_band_deg")
        _require_positive(self.goal_tolerance_deg, "goal_tolerance_deg")
        _require_positive(self.observe_duration_sec, "observe_duration_sec")
        _require_positive(self.sweep_limit_deg, "sweep_limit_deg")
        _require_positive(self.hint_max_age_sec, "hint_max_age_sec")
        _require_positive(self.follow_timeout_sec, "follow_timeout_sec")
        _require_positive(self.search_timeout_sec, "search_timeout_sec")

        if (
            isinstance(self.local_search_max_steps, bool)
            or not isinstance(self.local_search_max_steps, int)
            or self.local_search_max_steps < 0
        ):
            raise ValueError(
                "local_search_max_steps must be a non-negative integer")

        if self.step_angle_deg > 180.0:
            raise ValueError("step_angle_deg must be 180 or less")
        if self.goal_tolerance_deg >= self.step_angle_deg:
            # 허용 오차가 스텝보다 크면 "도착"이 즉시 참이 되어 제자리에서
            # 관찰만 반복하고 영원히 돌지 않는다.
            raise ValueError(
                "goal_tolerance_deg must be smaller than step_angle_deg")
        if self.min_angular_speed > self.angular_speed:
            raise ValueError(
                "min_angular_speed must not exceed angular_speed")
        if self.step_min_angular_speed > self.angular_speed:
            raise ValueError(
                "step_min_angular_speed must not exceed angular_speed")
        if not isinstance(self.return_to_start, bool):
            raise ValueError("return_to_start must be a boolean")


def _require_positive(value: float, name: str) -> None:
    """설정값이 유한한 양수인지 확인한다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")


class WakeSearchPolicy:
    """회전 탐색 상태 기계. 시계도 I/O 도 갖지 않는 순수 객체다.

    사용법
        policy.start(now, yaw, hint_deg)  로 시작하고,
        제어 주기마다 policy.update(now, yaw, person_visible) 을 부른다.
        외부 정지(재호출·대화 종료)는 policy.stop(reason) 이다.

    스레드 안전성
        보장하지 않는다. wake_search 노드의 단일 타이머 콜백에서만 부른다.
    """

    def __init__(self, config: SearchConfig | None = None) -> None:
        """설정을 검증하고 IDLE 상태로 초기화한다."""
        self._config = config if config is not None else SearchConfig()
        self._state = SearchState.IDLE
        self._start_yaw = 0.0
        self._target_yaw = 0.0
        self._swept_rad = 0.0
        self._observe_until_sec = 0.0
        self._started_at_sec = 0.0
        self._follow_until_sec = 0.0
        self._last_reason = "idle"

        # 힌트 중심 좌우 지그재그 탐색(local phase)의 진행 상태. 힌트가 없는
        # 탐색이나, 좌우 탐색 폭을 다 쓴 뒤에는 쓰이지 않는다.
        self._hint_yaw = 0.0
        self._local_phase_active = False
        self._local_next_side = 1
        self._local_next_magnitude = 1
        # 지금 진행 중인 STEP_TURN 이 지그재그(local)인지 전체 회전
        # (global)인지 — 완료됐을 때 swept_rad 에 더할지를 가른다. 지그재그는
        # 힌트 회전과 같은 이유로 누적 회전량에서 뺀다(전체 커버리지가
        # 아니라 힌트 근처 재확인일 뿐이므로).
        self._pending_step_is_local = False

    # ── 조회 ────────────────────────────────────────────────────────────────

    @property
    def state(self) -> SearchState:
        """현재 상태를 돌려준다."""
        return self._state

    @property
    def config(self) -> SearchConfig:
        """이 정책이 쓰는 설정을 돌려준다."""
        return self._config

    @property
    def is_active(self) -> bool:
        """탐색이나 추종이 진행 중이면 True."""
        return self._state not in (SearchState.IDLE, SearchState.FINISHED)

    @property
    def swept_deg(self) -> float:
        """전체 회전(global) 스텝으로 누적한 회전량(도).

        힌트 회전과 힌트 중심 좌우 지그재그(local) 스텝은 포함하지 않는다
        — 둘 다 "아직 안 본 곳을 새로 본다"가 아니라 힌트 근처를 다시
        확인하는 것이라 sweep_limit_deg 예산과는 별개다.
        """
        return math.degrees(self._swept_rad)

    # ── 제어 ────────────────────────────────────────────────────────────────

    def start(
        self,
        now_sec: float,
        current_yaw_rad: float,
        hint_deg: float | None = None,
    ) -> SearchDecision:
        """탐색을 시작한다.

        역할: 시작 방향을 기록하고, 힌트가 있으면 그 방향으로 먼저 돌게 한다.
        입력값:
            now_sec - 단조 증가 시각(초).
            current_yaw_rad - 현재 로봇 yaw(라디안). /odom 에서 온다.
            hint_deg - 로봇 정면 기준 소리 방향(도). 왼쪽이 양수. 없으면 None.
        반환값: 이번 주기에 발행할 SearchDecision.
        주의: 이미 진행 중이어도 새로 시작한다 — 재호출이 곧 재시작이다.
        """
        start_yaw = normalize_angle(current_yaw_rad)
        _require_finite(now_sec, "now_sec")

        self._start_yaw = start_yaw
        self._started_at_sec = float(now_sec)
        self._swept_rad = 0.0
        self._follow_until_sec = 0.0
        self._local_phase_active = False
        self._local_next_side = 1
        self._local_next_magnitude = 1
        self._pending_step_is_local = False

        if hint_deg is None:
            # 힌트가 없으면 좌우를 가를 기준이 없다 — 곧장 전체 회전이다.
            return self._enter_observe(now_sec, "search_started_without_hint")

        hint_rad = normalize_angle(math.radians(_as_float(hint_deg, "hint_deg")))
        self._hint_yaw = normalize_angle(start_yaw + hint_rad)
        self._local_phase_active = True
        # 지그재그 1차는 힌트로 돈 방향을 이어간다(오른쪽에서 불렀으면
        # 오른쪽으로 한 스텝 더, 왼쪽이면 왼쪽으로) — 항상 +1(왼쪽)부터
        # 시작하면, 오른쪽에서 부른 경우 첫 스텝이 오히려 중앙 쪽으로
        # 되돌아가 "반대편부터 본다"로 보였다(2026-08-08 실기).
        if hint_rad < 0.0:
            self._local_next_side = -1

        if abs(hint_rad) <= self._tolerance_rad:
            # 이미 그 방향을 보고 있다. 굳이 돌지 않는다.
            return self._enter_observe(now_sec, "hint_already_in_front")

        self._target_yaw = self._hint_yaw
        self._state = SearchState.TURN_TO_HINT
        return self._turn_decision(
            current_yaw_rad, SearchState.TURN_TO_HINT, "turning_to_sound")

    def update(
        self,
        now_sec: float,
        current_yaw_rad: float,
        person_visible: bool,
    ) -> SearchDecision:
        """제어 주기마다 불러 다음 명령을 받는다.

        역할: 상태에 따라 회전·관찰·복귀·추종을 결정한다.
        입력값:
            now_sec - 단조 증가 시각(초).
            current_yaw_rad - 현재 yaw(라디안).
            person_visible - 비전이 지금 사람을 확정 추적 중이면 True.
        반환값: SearchDecision.
        주의: IDLE/FINISHED 에서 불러도 안전하다 — 정지 명령을 돌려준다.
        """
        _require_finite(now_sec, "now_sec")
        yaw = normalize_angle(current_yaw_rad)
        if not isinstance(person_visible, bool):
            raise ValueError("person_visible must be a boolean")

        if self._state in (SearchState.IDLE, SearchState.FINISHED):
            return self._idle_decision()

        if self._state is SearchState.FOLLOWING:
            return self._update_following(now_sec)

        # 사람을 찾았으면 멈추고 추종에 넘긴다. 단 힌트로 도는 중에는
        # 무시한다 — 부른 사람은 힌트 방향에 있는데, 마침 정면에 있던 다른
        # 사람에게 가 버리면 "부르면 나에게 온다"가 성립하지 않는다
        # (2026-08-09 실기 논의). 힌트 회전을 마친 뒤부터 인정한다.
        if person_visible and self._state is not SearchState.TURN_TO_HINT:
            return self._enter_following(now_sec)

        # 전체 상한. 어떤 이유로든 여기서 반드시 끝난다.
        if now_sec - self._started_at_sec > self._config.search_timeout_sec:
            if self._state is SearchState.RETURNING:
                return self._finish("search_timeout_while_returning")
            return self._begin_return(now_sec, "search_timeout")

        if self._state is SearchState.OBSERVE:
            return self._update_observe(now_sec, yaw)
        if self._state in (SearchState.TURN_TO_HINT, SearchState.STEP_TURN):
            return self._update_turning(now_sec, yaw)
        if self._state is SearchState.RETURNING:
            return self._update_returning(yaw)

        # 여기에 오면 상태 정의가 빠진 것이다. 조용히 도는 것보다 멈추는 편이 낫다.
        return self._finish(f"unhandled_state_{self._state.value}")

    def resume_after_lost(
        self, now_sec: float, current_yaw_rad: float
    ) -> SearchDecision:
        """추종이 대상을 완전히 놓쳤을 때, 남은 탐색을 이어간다.

        왜 필요한가 (2026-08-08 실기)
            엉뚱한 사람(부르지 않은 사람)이 화각에 잠깐 들어와도 person_visible
            은 참이 되어 즉시 FOLLOWING 으로 넘어간다(person_search_patrol 과
            달리 이 정책엔 아직 대상 확정 지연이 없다). person_follower 가
            그 사람을 놓치고 완전히 포기해도, 이 정책은 그 사실을 몰라 계속
            FOLLOWING 에 머물며 아무 것도 하지 않는다 — 로봇이 "멈춘 것처럼"
            보이는 원인이었다. wake_search 노드가 person_follower 의 상태
            토픽에서 "target_lost_timeout" 을 받으면 이 메서드를 부른다.

        역할: 처음부터 다시 찾지 않는다 — 원래 탐색의 남은 스윕 예산
            (sweep_limit_deg 중 아직 안 돈 만큼)과 전체 시간 상한
            (search_timeout_sec, _started_at_sec 기준)을 그대로 이어받아
            지금 방향에서 한 스텝 더 돈다.
        입력값: now_sec - 단조 증가 시각(초). current_yaw_rad - 현재 yaw.
        반환값: 이번 주기에 발행할 SearchDecision.
        주의: FOLLOWING 상태가 아니면 아무 것도 하지 않는다 — 이미 새
            탐색이 시작됐거나 끝난 뒤에 뒤늦게 도착한 신호를 걸러낸다.
        """
        if self._state is not SearchState.FOLLOWING:
            return self._idle_decision()

        # 한 번 사람을 찾았던 시점의 힌트는 이미 낡았다 — 좌우 지그재그를
        # 다시 시작하지 않고 곧장 전체 회전으로 이어간다.
        self._local_phase_active = False

        yaw = normalize_angle(current_yaw_rad)
        sweep_limit_rad = math.radians(self._config.sweep_limit_deg)
        if self._swept_rad >= sweep_limit_rad - _EPSILON:
            return self._begin_return(now_sec, "resumed_sweep_complete")

        step_rad = math.radians(self._config.step_angle_deg)
        self._target_yaw = normalize_angle(yaw + step_rad)
        self._pending_step_is_local = False
        self._state = SearchState.STEP_TURN
        return self._turn_decision(
            yaw, SearchState.STEP_TURN, "resuming_after_lost")

    def stop(self, reason: str = "external_stop") -> SearchDecision:
        """외부 요청으로 즉시 끝낸다("보미야" 재호출, 대화 종료, 종료 정리).

        역할: 회전을 멈추고 추종 스위치를 확실히 끈다.
        주의: 몇 번 불러도 안전하다. 추종이 켜져 있지 않아도 끄기를 발행한다 —
            상태를 모르는 채 "아마 꺼져 있겠지"로 두는 것보다 안전하다
            (bridge/approach.py 의 stop() 과 같은 이유).
        """
        return self._finish(str(reason) or "external_stop")

    # ── 상태별 처리 ─────────────────────────────────────────────────────────

    def _update_following(self, now_sec: float) -> SearchDecision:
        """추종 중. 시간 상한만 감시하고 속도는 내지 않는다."""
        if now_sec >= self._follow_until_sec:
            return self._finish("follow_time_limit")
        return SearchDecision(
            angular_z=0.0,
            follow_enable=None,
            state=SearchState.FOLLOWING,
            reason="following",
            finished=False,
        )

    def _update_observe(self, now_sec: float, yaw: float) -> SearchDecision:
        """관찰 중. 시간이 차면 다음 스텝을 잡거나 복귀를 시작한다."""
        if now_sec < self._observe_until_sec:
            return SearchDecision(
                angular_z=0.0,
                follow_enable=None,
                state=SearchState.OBSERVE,
                reason="observing",
                finished=False,
            )

        if self._local_phase_active:
            local_decision = self._try_local_search_step(yaw)
            if local_decision is not None:
                return local_decision
            # 좌우 탐색 폭을 다 썼다 — 여기서부터는 기존 전체 회전이다.
            self._local_phase_active = False

        sweep_limit_rad = math.radians(self._config.sweep_limit_deg)
        if self._swept_rad >= sweep_limit_rad - _EPSILON:
            return self._begin_return(now_sec, "sweep_complete_person_not_found")

        step_rad = math.radians(self._config.step_angle_deg)
        # 항상 반시계(왼쪽)로 돈다. 방향을 번갈아 바꾸면 누적 회전량 계산이
        # 복잡해지고, 어느 쪽을 이미 봤는지 사람이 추적하기 어렵다.
        self._target_yaw = normalize_angle(yaw + step_rad)
        self._pending_step_is_local = False
        self._state = SearchState.STEP_TURN
        return self._turn_decision(yaw, SearchState.STEP_TURN, "stepping")

    def _try_local_search_step(self, yaw: float) -> SearchDecision | None:
        """힌트를 중심으로 다음 좌우 지그재그 지점을 잡는다.

        순서: 힌트로 돈 방향을 먼저 잇는다 -> 반대쪽 -> 먼저 방향으로
        2스텝 -> 반대쪽으로 2스텝 -> … (start() 에서 hint_rad 부호로
        _local_next_side 의 첫 값을 정한다). 다음 차수가
        local_search_max_steps 를 넘으면 좌우 탐색을 다 쓴 것이다 — None
        을 돌려줘 호출부가 전체 회전으로 넘어가게 한다.
        """
        if self._local_next_magnitude > self._config.local_search_max_steps:
            return None

        step_rad = math.radians(self._config.step_angle_deg)
        offset_rad = self._local_next_side * self._local_next_magnitude * step_rad
        self._target_yaw = normalize_angle(self._hint_yaw + offset_rad)

        if self._local_next_side > 0:
            self._local_next_side = -1
        else:
            self._local_next_side = 1
            self._local_next_magnitude += 1

        self._pending_step_is_local = True
        self._state = SearchState.STEP_TURN
        return self._turn_decision(yaw, SearchState.STEP_TURN, "local_search_step")

    def _update_turning(self, now_sec: float, yaw: float) -> SearchDecision:
        """힌트 회전 또는 스텝 회전 중. 목표에 닿으면 관찰로 넘어간다."""
        error = angle_error(self._target_yaw, yaw)
        if abs(error) <= self._tolerance_rad:
            if self._state is SearchState.STEP_TURN and not self._pending_step_is_local:
                self._swept_rad += math.radians(self._config.step_angle_deg)
            return self._enter_observe(now_sec, "reached_observation_heading")
        return self._turn_decision(yaw, self._state, "turning")

    def _update_returning(self, yaw: float) -> SearchDecision:
        """시작 방향으로 복귀 중(구현계획 결정 B)."""
        error = angle_error(self._start_yaw, yaw)
        if abs(error) <= self._tolerance_rad:
            return self._finish("returned_person_not_found")
        return self._turn_decision(yaw, SearchState.RETURNING, "returning")

    # ── 전이 보조 ───────────────────────────────────────────────────────────

    def _enter_observe(self, now_sec: float, reason: str) -> SearchDecision:
        """관찰 상태로 들어간다. 들어가는 순간 반드시 속도를 0으로 만든다."""
        self._state = SearchState.OBSERVE
        self._observe_until_sec = (
            float(now_sec) + self._config.observe_duration_sec)
        return SearchDecision(
            angular_z=0.0,
            follow_enable=None,
            state=SearchState.OBSERVE,
            reason=reason,
            finished=False,
        )

    def _enter_following(self, now_sec: float) -> SearchDecision:
        """사람을 찾았다. 회전을 멈추고 추종 스위치를 켠다."""
        self._state = SearchState.FOLLOWING
        self._follow_until_sec = (
            float(now_sec) + self._config.follow_timeout_sec)
        return SearchDecision(
            angular_z=0.0,
            follow_enable=True,
            state=SearchState.FOLLOWING,
            reason="person_found",
            finished=False,
        )

    def _begin_return(self, now_sec: float, reason: str) -> SearchDecision:
        """복귀를 시작한다. return_to_start 가 꺼져 있으면 그 자리에서 끝낸다."""
        if not self._config.return_to_start:
            return self._finish(reason)
        self._target_yaw = self._start_yaw
        self._state = SearchState.RETURNING
        self._started_at_sec = float(now_sec)  # 복귀에도 상한을 새로 준다
        return SearchDecision(
            angular_z=0.0,
            follow_enable=None,
            state=SearchState.RETURNING,
            reason=reason,
            finished=False,
        )

    def _finish(self, reason: str) -> SearchDecision:
        """탐색을 끝낸다. 속도 0 과 추종 끄기를 항상 함께 낸다."""
        self._state = SearchState.FINISHED
        self._last_reason = reason
        return SearchDecision(
            angular_z=0.0,
            follow_enable=False,
            state=SearchState.FINISHED,
            reason=reason,
            finished=True,
        )

    def _idle_decision(self) -> SearchDecision:
        """IDLE/FINISHED 에서 돌려주는 무동작 결정."""
        return SearchDecision(
            angular_z=0.0,
            follow_enable=None,
            state=self._state,
            reason="inactive",
            finished=False,
        )

    def _turn_decision(
        self,
        yaw: float,
        state: SearchState,
        reason: str,
    ) -> SearchDecision:
        """목표까지의 오차로 각속도를 만든다."""
        error = angle_error(self._target_yaw, yaw)
        return SearchDecision(
            angular_z=self._speed_for(error, state),
            follow_enable=None,
            state=state,
            reason=reason,
            finished=False,
        )

    def _speed_for(self, error_rad: float, state: SearchState) -> float:
        """오차 각도에서 목표 각속도를 만든다. 목표 근처에서는 감속한다.

        감속이 없으면 제어 주기(50ms) 사이에 목표를 지나쳐 좌우로 떨게 된다.
        너무 느려지면 정지 마찰을 못 이기므로 바닥 속도를 둔다.

        TURN_TO_HINT 는 단 한 번뿐인 큰 회전이라 정밀 착지가 중요해서
        일찍·많이 감속한다(slowdown_band_deg/min_angular_speed). 그 밖의
        회전(STEP_TURN — 지그재그·전체 회전·복귀)은 목표가 정확한 사람
        방향이 아니라 그냥 다음 관찰 지점이라, 같은 감속 프로파일을 쓰면
        40° 스텝의 62%(25°/40°) 구간을 감속만 하다 끝나 전체 탐색이
        느려진다(2026-08-08 실기) — 훨씬 늦게, 짧게 감속하는
        step_slowdown_band_deg/step_min_angular_speed 를 쓴다.
        """
        if state is SearchState.TURN_TO_HINT:
            band_deg = self._config.slowdown_band_deg
            floor = self._config.min_angular_speed
        else:
            band_deg = self._config.step_slowdown_band_deg
            floor = self._config.step_min_angular_speed

        magnitude = abs(error_rad)
        band = math.radians(band_deg)
        speed = self._config.angular_speed
        if magnitude < band:
            scaled = self._config.angular_speed * (magnitude / band)
            speed = max(floor, scaled)
        return math.copysign(speed, error_rad)

    @property
    def _tolerance_rad(self) -> float:
        """목표 도달로 인정할 각도 오차(라디안)."""
        return math.radians(self._config.goal_tolerance_deg)


def _require_finite(value: float, name: str) -> None:
    """시각처럼 유한해야 하는 실수를 검증한다."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _as_float(value: float, name: str) -> float:
    """유한한 실수로 변환한다."""
    _require_finite(value, name)
    return float(value)
