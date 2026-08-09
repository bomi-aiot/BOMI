"""회전 탐색 노드 — "보미야" 호출을 받아 제자리에서 돌며 사람을 찾는다.

이 노드가 채우는 빈칸
    기존 코드에는 "사람이 보이면 따라간다"(person_follower)는 있었지만,
    "사람을 찾으러 스스로 돈다"는 없었다. 사람이 안 보이면 person_follower 는
    정지만 하므로 닭이 먼저냐 달걀이 먼저냐가 된다. 이 노드가 그 고리를 끊는다.

배선 (구현계획 §0)
    시작 신호  ROS 2 ``/wake_search/start`` (std_msgs/Bool)
               백엔드가 MQTT 로 FOLLOW_START 를 보내면 bridge 가 여기에 True 를
               발행한다. "언제 시작할지"는 백엔드가 정한다.
    방향 힌트  UDP (기본 127.0.0.1:5006), ai_chat 이 웨이크워드 직후 보낸다.
               {"type": "wake", "azimuth_deg": <로봇 정면 기준 각도>}
               백엔드 MQTT 계약은 필드 화이트리스트가 엄격해 각도를 실을 수
               없다. 그래서 "어디로 돌지"만 로봇 내부 UDP 로 따로 나른다.

    start_trigger 파라미터로 어느 신호를 시작으로 인정할지 고른다.
        "topic" 백엔드 경유만 (구현계획 결정 1의 정식 경로)
        "udp"   로봇 안에서만 (백엔드·네트워크 없이 시연·개발)
        "both"  둘 다 (기본값). 백엔드가 FOLLOW_START 로 전환되기 전에도
                시나리오를 그대로 돌려 볼 수 있다. 두 신호가 겹쳐 들어와도
                이미 탐색 중이면 다시 시작할 뿐 위험하지 않다.
    즉시 정지  같은 UDP 로 {"type": "stop", "reason": "..."} 또는
               ``/wake_search/start`` 에 False.
    현재 각도  ``/odom`` (nav_msgs/Odometry) 의 yaw.
               pico_driver.yaml 주석대로 이 yaw 는 자이로에서 온다 — 바퀴
               미끄러짐에 영향받지 않으므로 회전각 기준으로 쓸 수 있다.
    사람 여부  ``/vision/follow_result`` (std_msgs/String, JSON).
               status 가 "tracking" 이면 비전이 한 사람을 확정 추적 중이다.
    출력       ``/cmd_vel_search`` (twist_mux 우선순위 80)
               ``/person_following/enable`` (std_msgs/Bool)

안전
    - 판단 로직은 core.search_policy 에 있고 이 노드는 배선만 한다.
    - /odom 이 끊기면(odom_timeout_sec) 즉시 정지한다. 각도를 모르는 채 도는
      것은 통제 불능이다.
    - 탐색 중이 아닐 때는 /cmd_vel_search 에 아무것도 발행하지 않는다.
      twist_mux 는 timeout 이 지나면 그 입력을 무시하므로, 침묵이 곧 양보다.
    - 종료(정상·예외 모두)에서 정지 명령과 추종 끄기를 반드시 낸다.
    - 각속도는 max_angular_speed 로 한 번 더 자른다(설정 실수 방어).
"""

import json
import math
import socket

from core.search_policy import (
    SearchConfig,
    SearchDecision,
    SearchState,
    WakeSearchPolicy,
)
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

# UDP 로 받는 메시지 타입.
SIGNAL_WAKE = "wake"
SIGNAL_STOP = "stop"
SIGNAL_FOLLOW = "follow"

# ai_vision 이 사람 한 명을 확정 추적 중일 때 보내는 status 값
# (ai_vision/domain/tracking.py 의 TrackingResultStatus.TRACKING).
VISION_STATUS_TRACKING = "tracking"


def yaw_from_quaternion(x: float, y: float, z: float, w: float) -> float:
    """쿼터니언에서 Z축 회전(yaw)만 뽑는다.

    역할: Odometry 의 자세에서 우리가 쓰는 유일한 값인 yaw 를 계산한다.
    입력값: x, y, z, w - 쿼터니언 성분.
    반환값: -pi ~ pi 범위의 yaw(라디안).
    주의: tf_transformations 패키지에 의존하지 않으려고 직접 계산한다 —
        이 노드가 필요한 것은 yaw 하나뿐이고, 의존성을 하나 줄이면 젯슨
        설치 단계가 그만큼 줄어든다.
    """
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


def is_person_currently_visible(
    *,
    vision_tracking: bool,
    vision_stamp_sec: float,
    now_sec: float,
    vision_timeout_sec: float,
    search_started_at_sec: float,
) -> bool:
    """비전 결과가 최신이고, 이번 탐색이 시작된 뒤에 도착했는지 확인한다.

    search_started_at_sec 조건이 없으면 탐색 시작 전부터 남아있던 낡은
    결과를 "방금 찾았다"로 오인해 회전 없이 즉시 추종으로 넘어간다.
    """
    return (
        vision_tracking
        and (now_sec - vision_stamp_sec) <= vision_timeout_sec
        and vision_stamp_sec >= search_started_at_sec
    )


class WakeSearchNode(Node):
    """회전 탐색 정책을 ROS 2 토픽과 UDP 에 연결하는 노드다."""

    def __init__(self) -> None:
        """파라미터를 읽고 구독·발행·UDP 소켓·제어 타이머를 만든다."""
        super().__init__("wake_search")

        self._declare_parameters()

        self._cmd_vel_topic = self._string_param("cmd_vel_topic")
        self._follow_enable_topic = self._string_param("follow_enable_topic")
        self._follow_status_topic = self._string_param("follow_status_topic")
        patrol_enable_topic = self._string_param("patrol_enable_topic")
        self._enable_patrol_on_not_found = bool(
            self.get_parameter("enable_patrol_on_not_found").value)
        odom_topic = self._string_param("odom_topic")
        vision_topic = self._string_param("vision_topic")
        start_topic = self._string_param("start_topic")

        self._max_angular_speed = self._positive_param("max_angular_speed")
        self._odom_timeout_sec = self._positive_param("odom_timeout_sec")
        self._vision_timeout_sec = self._positive_param("vision_timeout_sec")
        publish_rate_hz = self._positive_param("publish_rate_hz")

        self._hint_bind_host = self._string_param("hint_bind_host")
        self._hint_bind_port = int(self.get_parameter("hint_bind_port").value)
        self._use_sound_hint = bool(self.get_parameter("use_sound_hint").value)

        self._start_debounce_sec = self._positive_param(
            "start_debounce_sec")
        self._start_trigger = self._string_param("start_trigger").lower()
        if self._start_trigger not in ("topic", "udp", "both"):
            raise ValueError(
                "start_trigger는 topic, udp, both 중 하나여야 합니다: "
                f"{self._start_trigger}")

        self._policy = WakeSearchPolicy(self._build_config())

        if not 1 <= self._hint_bind_port <= 65535:
            raise ValueError("hint_bind_port는 1부터 65535 사이여야 합니다.")
        if self._max_angular_speed < self._policy.config.angular_speed:
            raise ValueError(
                "max_angular_speed는 angular_speed 이상이어야 합니다.")

        # ── 상태 (모두 제어 타이머 콜백에서만 읽고 쓴다) ────────────────────
        self._yaw_rad: float | None = None
        self._yaw_stamp_sec = 0.0
        self._vision_tracking = False
        self._vision_stamp_sec = 0.0
        self._search_started_at_sec = 0.0
        self._hint_deg: float | None = None
        self._hint_stamp_sec = 0.0
        self._pending_stop_reason: str | None = None
        self._pending_start = False
        self._pending_resume = False
        self._pending_arrived = False
        self._was_active = False
        self._last_state = SearchState.IDLE

        # ── 발행 ───────────────────────────────────────────────────────────
        self._cmd_publisher = self.create_publisher(
            Twist, self._cmd_vel_topic, 10)
        self._follow_publisher = self.create_publisher(
            Bool, self._follow_enable_topic, 10)
        self._patrol_publisher = self.create_publisher(
            Bool, patrol_enable_topic, 10)

        # ── 구독 ───────────────────────────────────────────────────────────
        self.create_subscription(Odometry, odom_topic, self._on_odom, 10)
        self.create_subscription(String, vision_topic, self._on_vision, 10)
        self.create_subscription(Bool, start_topic, self._on_start, 10)
        self.create_subscription(
            String, self._follow_status_topic, self._on_follow_status, 10)

        # ── UDP 힌트 수신 ──────────────────────────────────────────────────
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self._hint_bind_host, self._hint_bind_port))
        self._socket.setblocking(False)

        self._timer = self.create_timer(
            1.0 / publish_rate_hz, self._on_control_tick)

        config = self._policy.config
        self.get_logger().info(
            "회전 탐색 노드를 시작했습니다. "
            f"시작 토픽={start_topic}, 속도 출력={self._cmd_vel_topic}, "
            f"추종 스위치={self._follow_enable_topic}, "
            f"힌트 수신={self._hint_bind_host}:{self._hint_bind_port}"
            f"({'사용' if self._use_sound_hint else '무시'}), "
            f"시작 트리거={self._start_trigger}, "
            f"스텝={config.step_angle_deg:.0f}도, "
            f"속도={config.angular_speed:.2f}rad/s, "
            f"관찰={config.observe_duration_sec:.1f}초, "
            f"한바퀴={config.sweep_limit_deg:.0f}도"
        )

    # ── 파라미터 ────────────────────────────────────────────────────────────

    def _declare_parameters(self) -> None:
        """설정값을 선언한다. 기본값은 config/wake_search.yaml 과 같게 둔다."""
        self.declare_parameter("cmd_vel_topic", "/cmd_vel_search")
        self.declare_parameter(
            "follow_enable_topic", "/person_following/enable")
        self.declare_parameter(
            "follow_status_topic", "/person_following/status")
        self.declare_parameter("patrol_enable_topic", "/person_search/enable")
        self.declare_parameter("enable_patrol_on_not_found", False)
        self.declare_parameter("odom_topic", "/odom")
        self.declare_parameter("vision_topic", "/vision/follow_result")
        self.declare_parameter("start_topic", "/wake_search/start")

        self.declare_parameter("step_angle_deg", 40.0)
        self.declare_parameter("angular_speed", 0.6)
        self.declare_parameter("min_angular_speed", 0.15)
        self.declare_parameter("max_angular_speed", 1.0)
        self.declare_parameter("slowdown_band_deg", 15.0)
        self.declare_parameter("step_min_angular_speed", 0.3)
        self.declare_parameter("step_slowdown_band_deg", 10.0)
        self.declare_parameter("goal_tolerance_deg", 3.0)
        self.declare_parameter("observe_duration_sec", 0.8)
        self.declare_parameter("sweep_limit_deg", 320.0)
        self.declare_parameter("local_search_max_steps", 2)
        self.declare_parameter("hint_max_age_sec", 10.0)
        self.declare_parameter("follow_timeout_sec", 60.0)
        self.declare_parameter("search_timeout_sec", 45.0)
        self.declare_parameter("return_to_start", True)

        self.declare_parameter("publish_rate_hz", 20.0)
        self.declare_parameter("odom_timeout_sec", 0.5)
        self.declare_parameter("vision_timeout_sec", 1.0)

        self.declare_parameter("hint_bind_host", "127.0.0.1")
        self.declare_parameter("hint_bind_port", 5006)
        self.declare_parameter("use_sound_hint", True)
        self.declare_parameter("start_trigger", "both")
        self.declare_parameter("start_debounce_sec", 3.0)

    def _build_config(self) -> SearchConfig:
        """파라미터에서 순수 로직용 설정을 만든다(값 검증은 SearchConfig 가 한다)."""
        return SearchConfig(
            step_angle_deg=float(self.get_parameter("step_angle_deg").value),
            angular_speed=float(self.get_parameter("angular_speed").value),
            min_angular_speed=float(
                self.get_parameter("min_angular_speed").value),
            slowdown_band_deg=float(
                self.get_parameter("slowdown_band_deg").value),
            step_min_angular_speed=float(
                self.get_parameter("step_min_angular_speed").value),
            step_slowdown_band_deg=float(
                self.get_parameter("step_slowdown_band_deg").value),
            goal_tolerance_deg=float(
                self.get_parameter("goal_tolerance_deg").value),
            observe_duration_sec=float(
                self.get_parameter("observe_duration_sec").value),
            sweep_limit_deg=float(self.get_parameter("sweep_limit_deg").value),
            local_search_max_steps=int(
                self.get_parameter("local_search_max_steps").value),
            hint_max_age_sec=float(
                self.get_parameter("hint_max_age_sec").value),
            follow_timeout_sec=float(
                self.get_parameter("follow_timeout_sec").value),
            search_timeout_sec=float(
                self.get_parameter("search_timeout_sec").value),
            return_to_start=bool(self.get_parameter("return_to_start").value),
        )

    def _string_param(self, name: str) -> str:
        value = str(self.get_parameter(name).value).strip()
        if not value:
            raise ValueError(f"{name}은 비어 있을 수 없습니다.")
        return value

    def _positive_param(self, name: str) -> float:
        value = float(self.get_parameter(name).value)
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"{name}은 유한한 양수여야 합니다.")
        return value

    # ── 구독 콜백 ───────────────────────────────────────────────────────────

    def _on_odom(self, message: Odometry) -> None:
        """현재 yaw 를 갱신한다."""
        orientation = message.pose.pose.orientation
        yaw = yaw_from_quaternion(
            orientation.x, orientation.y, orientation.z, orientation.w)
        if not math.isfinite(yaw):
            self.get_logger().warning("유한하지 않은 odom yaw 를 무시합니다.")
            return
        self._yaw_rad = yaw
        self._yaw_stamp_sec = self._now_sec()

    def _on_vision(self, message: String) -> None:
        """비전 결과에서 "사람 한 명을 확정 추적 중인가"만 뽑는다."""
        try:
            payload = json.loads(message.data)
        except (TypeError, ValueError):
            self.get_logger().warning("비전 결과 JSON 해석 실패, 무시합니다.")
            return
        if not isinstance(payload, dict):
            return
        self._vision_tracking = payload.get("status") == VISION_STATUS_TRACKING
        self._vision_stamp_sec = self._now_sec()

    def _on_follow_status(self, message: String) -> None:
        """person_follower 가 추종을 포기했음을 알리면 표시만 남긴다.

        엉뚱한 사람이 화각에 잠깐 들어와도 person_visible 은 참이 되어 바로
        FOLLOWING 으로 넘어간다. person_follower 가 그 사람을 놓치고
        완전히 포기(target_lost_timeout)해도 이 노드는 그 사실을 몰라
        FOLLOWING 에 멈춰 서 있었다(2026-08-08 실기, 팀원 오인식으로 재현).
        실제 정책 호출은 제어 주기에서만 한다 — 다른 콜백들과 같은 이유.
        """
        try:
            payload = json.loads(message.data)
        except (TypeError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        if payload.get("reason") == "target_lost_timeout":
            if self._policy.is_active:
                self._pending_resume = True
            else:
                self._pending_start = True
        elif payload.get("state") == "arrived":
            self._pending_arrived = True

    def _on_start(self, message: Bool) -> None:
        """bridge 가 보내는 시작/정지 신호. 실제 처리는 제어 주기에서 한다.

        콜백에서 바로 정책을 만지지 않는 이유: 상태를 한 스레드(타이머)에서만
        건드리면 락이 필요 없다. 여기서는 의사만 남긴다.
        """
        if message.data:
            self._pending_start = True
        else:
            self._pending_stop_reason = "start_topic_false"

    # ── UDP ─────────────────────────────────────────────────────────────────

    def _drain_hint_socket(self) -> None:
        """대기 중인 UDP 신호를 모두 읽는다. 마지막 값이 이긴다."""
        for _ in range(16):
            try:
                data, _address = self._socket.recvfrom(1024)
            except BlockingIOError:
                return
            except OSError as error:
                self.get_logger().error(f"힌트 UDP 수신 오류: {error}")
                return
            self._handle_hint_packet(data)

    def _handle_hint_packet(self, data: bytes) -> None:
        """UDP 한 통을 해석한다. 잘못된 패킷은 로그만 남기고 버린다."""
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self.get_logger().warning("힌트 UDP 패킷 해석 실패, 무시합니다.")
            return
        if not isinstance(payload, dict):
            return

        signal_type = payload.get("type")
        if signal_type == SIGNAL_FOLLOW:
            self._publish_follow_enable(True)
            self.get_logger().info("UDP 직접 추종 신호를 받았습니다.")
            return
        if signal_type == SIGNAL_STOP:
            reason = str(payload.get("reason") or "udp_stop")
            self._pending_stop_reason = reason
            self.get_logger().info(f"UDP 정지 신호: {reason}")
            return

        if signal_type != SIGNAL_WAKE:
            return

        azimuth = payload.get("azimuth_deg")
        if azimuth is None:
            self._hint_deg = None
            self._hint_stamp_sec = 0.0
            self.get_logger().info("웨이크 신호(방향 없음)를 받았습니다.")
            self._maybe_start_from_udp()
            return
        try:
            azimuth_deg = float(azimuth)
        except (TypeError, ValueError):
            self.get_logger().warning("azimuth_deg 가 숫자가 아니라 무시합니다.")
            return
        if not math.isfinite(azimuth_deg):
            self.get_logger().warning("azimuth_deg 가 유한하지 않아 무시합니다.")
            return

        self._hint_deg = azimuth_deg
        self._hint_stamp_sec = self._now_sec()
        self.get_logger().info(f"소리 방향 힌트: {azimuth_deg:+.1f}도")
        self._maybe_start_from_udp()

    def _maybe_start_from_udp(self) -> None:
        """start_trigger 가 udp 를 인정하면 웨이크 신호로 탐색을 시작한다.

        백엔드 경유(topic)만 쓰는 설정에서는 각도만 기억하고 시작하지 않는다 —
        "언제 시작할지"의 결정권을 한 곳에만 두기 위해서다.
        """
        if self._start_trigger in ("udp", "both"):
            self._pending_start = True

    # ── 제어 주기 ───────────────────────────────────────────────────────────

    def _on_control_tick(self) -> None:
        """20Hz 로 불린다. 신호를 반영하고 정책에 물어 속도를 발행한다."""
        self._drain_hint_socket()
        now = self._now_sec()

        if self._pending_stop_reason is not None:
            reason = self._pending_stop_reason
            self._pending_stop_reason = None
            self._pending_start = False
            self._pending_resume = False
            self._pending_arrived = False
            if self._policy.is_active:
                self._apply(self._policy.stop(reason))
            else:
                # 탐색 중이 아니어도 끄기는 발행한다. 이전 실행이 남긴 추종이
                # 켜져 있을 수 있는데, 그 상태를 모르는 채 "아마 꺼져 있겠지"로
                # 두는 것보다 확실히 꺼진 상태를 만드는 편이 안전하다
                # (bridge/approach.py 의 stop() 과 같은 이유).
                self.get_logger().info(f"정지 요청({reason}) — 탐색 중이 아닙니다.")
                self._publish_follow_enable(False)
            return

        if self._pending_start:
            self._pending_start = False
            self._pending_resume = False
            self._pending_arrived = False
            self._begin_search(now)
            return

        # 사람 앞에 도착했으면 추종을 끄고 그 자리에 머문다. 켜 둔 채로 두면
        # 대화 중 어르신이 조금만 움직여도 계속 재정렬·재접근한다.
        if self._pending_arrived:
            self._pending_arrived = False
            self._pending_resume = False
            if self._policy.is_active:
                self.get_logger().info(
                    "사람 앞에 도착해 추종을 끕니다.")
                self._apply(self._policy.stop("arrived"))
            return

        if self._pending_resume:
            self._pending_resume = False
            if self._policy.is_active:
                if not self._odom_is_fresh(now):
                    self.get_logger().error(
                        "odom 이 끊겨 재탐색을 시작하지 못합니다.")
                    self._apply(self._policy.stop("odom_timeout"))
                else:
                    self.get_logger().info(
                        "추종 대상을 놓쳐 남은 방향 탐색을 재개합니다.")
                    self._apply(
                        self._policy.resume_after_lost(
                            now, float(self._yaw_rad)))
            return

        if not self._policy.is_active:
            # 탐색 중이 아니면 침묵한다. twist_mux 가 타임아웃으로 이 입력을
            # 무시하므로, 아무것도 안 보내는 것이 곧 다른 명령원에게 양보다.
            return

        if not self._odom_is_fresh(now):
            self.get_logger().error(
                "odom 이 끊겨 회전을 중단합니다(각도를 모르는 채 돌 수 없습니다).")
            self._apply(self._policy.stop("odom_timeout"))
            return

        person_visible = is_person_currently_visible(
            vision_tracking=self._vision_tracking,
            vision_stamp_sec=self._vision_stamp_sec,
            now_sec=now,
            vision_timeout_sec=self._vision_timeout_sec,
            search_started_at_sec=self._search_started_at_sec,
        )
        self._apply(
            self._policy.update(now, float(self._yaw_rad), person_visible))

    def _begin_search(self, now: float) -> None:
        """시작 신호를 실제 탐색 시작으로 옮긴다."""
        # 같은 호출에 대해 신호가 두 번 올 수 있다: ai_chat 의 UDP(방향 포함)와
        # 백엔드 경유 FOLLOW_START(방향 없음). 뒤에 온 신호로 다시 시작하면
        # 이미 써서 비운 힌트가 없으므로 방향을 잃고 전체 탐색이 된다
        # (2026-08-09 실기: UDP 로 돌기 시작한 0.44초 뒤 FOLLOW_START 가
        # 도착해 힌트가 날아갔다). 방금 시작했으면 중복으로 보고 무시한다.
        if (
            self._policy.is_active
            and now - self._search_started_at_sec
            < self._start_debounce_sec
        ):
            self.get_logger().info(
                "이미 탐색 중입니다 — 중복 시작 신호를 무시합니다.")
            return

        if not self._odom_is_fresh(now):
            self.get_logger().error(
                "odom 이 없어 탐색을 시작하지 않습니다. Pico 드라이버를 확인하세요.")
            self._publish_follow_enable(False)
            return

        self._search_started_at_sec = now
        hint = self._fresh_hint_deg(now)
        # 한 번 쓴 힌트는 비운다. 남겨 두면 다음 시작(예: 백엔드 재시도)이 지난
        # 호출의 방향으로 돌아 버린다 — 그때는 소리가 어디서 났는지 모르는
        # 상태이므로 전체 탐색이 옳다.
        self._hint_deg = None
        self._hint_stamp_sec = 0.0
        if hint is None:
            self.get_logger().info(
                "소리 방향 힌트가 없어 현재 방향부터 한 바퀴 탐색합니다.")
        else:
            self.get_logger().info(f"소리 방향 {hint:+.1f}도부터 탐색을 시작합니다.")
        self._apply(self._policy.start(now, float(self._yaw_rad), hint))

    def _fresh_hint_deg(self, now: float) -> float | None:
        """유효 기간 안에 들어온 방향 힌트만 돌려준다.

        오래된 힌트를 쓰면 지난번 호출 방향으로 돌아버린다. 힌트는 UDP 라
        도착 보장이 없으므로, 없으면 없는 대로 전체 탐색으로 폴백한다.
        """
        if not self._use_sound_hint or self._hint_deg is None:
            return None
        age = now - self._hint_stamp_sec
        if age > self._policy.config.hint_max_age_sec:
            self.get_logger().warning(
                f"방향 힌트가 오래되어({age:.1f}초) 무시합니다.")
            return None
        return self._hint_deg

    def _odom_is_fresh(self, now: float) -> bool:
        """/odom 이 최근에 들어왔는지 확인한다."""
        if self._yaw_rad is None:
            return False
        return (now - self._yaw_stamp_sec) <= self._odom_timeout_sec

    # ── 발행 ────────────────────────────────────────────────────────────────

    def _apply(self, decision: SearchDecision) -> None:
        """정책 결정을 실제 토픽 발행으로 옮긴다."""
        if decision.follow_enable is not None:
            self._publish_follow_enable(decision.follow_enable)

        entered_following = (
            decision.state is SearchState.FOLLOWING
            and self._last_state is not SearchState.FOLLOWING
        )

        # 추종 중에는 person_follower 가 /cmd_vel_follow 로 운전한다. 이 노드가
        # 0을 계속 쏘면 twist_mux 입력이 살아 있는 것으로 보여 추종 명령을 막는다
        # (같은 우선순위 표에서 살아 있는 입력이 하나라도 있으면 자리를 차지한다).
        #
        # 다만 '추종으로 넘어가는 그 순간'에는 반드시 0을 한 번 보낸다. 그냥
        # 침묵하면 twist_mux 는 timeout(0.5초)까지 마지막 회전 명령을 계속
        # 내보내므로, 사람을 찾고도 0.5초 더 도는 일이 생긴다.
        if decision.state is not SearchState.FOLLOWING or entered_following:
            self._publish_angular(
                0.0 if entered_following else decision.angular_z)

        # 상태가 바뀔 때마다 남긴다. 20Hz 로 매번 찍으면 로그를 못 읽고,
        # 시작·종료만 찍으면 어느 스텝에서 멈췄는지 알 수 없다.
        if decision.state is not self._last_state or decision.finished:
            self.get_logger().info(
                f"탐색 상태={decision.state.value}, 사유={decision.reason}, "
                f"각속도={decision.angular_z:+.2f}rad/s, "
                f"누적회전={self._policy.swept_deg:.0f}도")

        self._last_state = decision.state
        self._was_active = self._policy.is_active

        if decision.finished:
            # 끝났으면 마지막으로 확실히 멈춘다.
            self._publish_angular(0.0)
            if (
                self._enable_patrol_on_not_found
                and (
                    "person_not_found" in decision.reason
                    or "search_timeout" in decision.reason
                )
            ):
                self.get_logger().info(
                    "회전 탐색에서 사람을 찾지 못해 웨이포인트 순찰을 시작합니다.")
                self._patrol_publisher.publish(Bool(data=True))

    def _publish_angular(self, angular_z: float) -> None:
        """각속도만 담은 Twist 를 발행한다. 상한으로 한 번 더 자른다."""
        limited = max(-self._max_angular_speed,
                      min(self._max_angular_speed, float(angular_z)))
        message = Twist()
        message.linear.x = 0.0
        message.angular.z = limited
        self._cmd_publisher.publish(message)

    def _publish_follow_enable(self, enable: bool) -> None:
        """추종 스위치를 발행한다."""
        self._follow_publisher.publish(Bool(data=bool(enable)))
        self.get_logger().info(
            f"추종 스위치를 {'켭니다' if enable else '끕니다'}.")

    def _now_sec(self) -> float:
        """ROS 시계의 현재 시각(초)."""
        return self.get_clock().now().nanoseconds / 1e9

    # ── 종료 ────────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """정지 명령과 추종 끄기를 낸 뒤 소켓을 닫는다.

        두 번 불려도 안전하다. 종료 경로가 여러 개(정상 종료, Ctrl+C, 예외)라
        멱등이어야 한다.
        """
        try:
            self._publish_angular(0.0)
            self._publish_follow_enable(False)
        except Exception:  # noqa: BLE001 - 종료 정리 실패가 종료를 막으면 안 된다
            self.get_logger().warning("종료 정지 발행에 실패했습니다.")
        try:
            self._socket.close()
        except OSError:
            pass


def main(args=None) -> None:
    """회전 탐색 노드를 실행한다."""
    rclpy.init(args=args)

    node: WakeSearchNode | None = None
    try:
        node = WakeSearchNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.shutdown()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
