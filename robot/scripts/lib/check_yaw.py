"""자이로 yaw가 실제 회전과 맞는지 사람이 확인할 수 있게 실시간으로 찍는다.

왜 필요한가: EKF는 yaw를 자이로 하나로만 만든다(core/config/ekf.yaml의
imu0_config에서 vyaw만 true). 자이로 바이어스가 틀리면 yaw는 회전량이
아니라 흐른 시간에 비례해 어긋난다. 제자리 회전은 시간이 오래 걸리므로
가장 크게 드러나고, 직진은 멀쩡해 보인다. 지도에서는 "겹마다 벽선은
깨끗한데 방이 10~20°씩 돌아간 여러 장으로 쌓이는" 모습이 된다.
2026-08-07 강의장 실기의 증상이 정확히 이것이었다.

읽기 전용이다. 로봇에 명령을 보내지 않으므로 매핑 스택이 돌고 있는
상태에서 그대로 띄워도 안전하다.

쓰는 법 (매핑 스택이 떠 있는 상태에서 다른 터미널로):

  1. 로봇을 가만히 둔 채 이 스크립트를 띄운다.
     python3 robot/scripts/lib/check_yaw.py

  2. `정지 중 표류` 값을 30초쯤 본다.
     · 0.5 °/분 미만이면 바이어스는 정상이다.
     · 그보다 크면 자이로 바이어스가 안 잡힌 것이다. 로봇을 완전히
       세운 채 매핑 스택을 다시 띄운다(기동 중 움직이면 바이어스를
       잘못 잡는다).

  3. 직진만 시킨다. 조이스틱으로 회전 없이 2 m 앞으로 갔다가 멈춘다.
     `누적 회전` 이 출발 때 값에서 크게 벗어나면 안 된다.
     · 2° 이내면 정상이다.
     · 직진만 했는데 yaw가 흐르면 바닥 진동으로 생긴 바이어스이거나
       자이로 축이 기울어 장착된 것이다. 둘 다 정지 중에는 안 나타나고
       주행 중에만 나타나므로 2번 검사로는 걸러지지 않는다. 바닥
       재질이 바뀐 뒤 지도가 나빠졌다면 여기서 드러난다.

  4. 조이스틱으로 제자리에서 정확히 한 바퀴(360°) 돌리고 멈춘 뒤,
     `누적 회전` 을 읽는다.
     · 360 ± 5° 면 자이로 스케일은 정상이다. 그러면 지도가 틀어지는
       원인은 yaw가 아니므로 SLAM 정합 쪽을 본다.
     · 340° 나 385° 처럼 일정 비율로 어긋나면 스케일 오차다. 회전
       각도에 비례하므로 회전을 많이 할수록 지도가 더 틀어진다.
"""
import math
import sys
import time

import rclpy
from rclpy.node import Node
from tf2_ros import Buffer, TransformListener

# 정지 판정 문턱. 이보다 느리면 "안 움직이는 중"으로 보고 표류를 잰다.
STILL_RATE_DEG_PER_SEC = 1.0


def _yaw_from_quaternion(q) -> float:
    """평면 회전만 있는 쿼터니언에서 yaw(rad)를 뽑는다."""
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)

    return math.atan2(siny, cosy)


def main() -> int:
    """odom -> base_link 의 yaw를 계속 읽어 누적 회전과 표류를 출력한다."""
    rclpy.init()
    node = Node("check_yaw")
    buffer = Buffer()
    TransformListener(buffer, node)

    print("자이로 yaw 확인 — Ctrl+C 로 종료")
    print("로봇을 먼저 가만히 두고 '정지 중 표류'를 보세요.\n")

    previous_yaw = None
    total_turn_deg = 0.0
    still_start = None
    still_start_total = 0.0

    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.2)

            try:
                transform = buffer.lookup_transform(
                    "odom",
                    "base_link",
                    rclpy.time.Time(),
                )
            except Exception:
                continue

            yaw = _yaw_from_quaternion(transform.transform.rotation)
            now = time.time()

            if previous_yaw is None:
                previous_yaw = yaw
                still_start = now
                continue

            # -pi/pi 경계를 넘을 때 한 바퀴로 세지 않도록 최단각으로 잰다.
            delta = math.degrees(
                math.atan2(
                    math.sin(yaw - previous_yaw),
                    math.cos(yaw - previous_yaw),
                )
            )
            previous_yaw = yaw
            total_turn_deg += delta

            rate = abs(delta) / 0.2

            if rate < STILL_RATE_DEG_PER_SEC:
                if still_start is None:
                    still_start = now
                    still_start_total = total_turn_deg
                elapsed = now - still_start
                if elapsed >= 3.0:
                    drift = (total_turn_deg - still_start_total)
                    drift_per_min = drift / elapsed * 60.0
                    print(
                        f"  정지 중 표류 {drift_per_min:+7.2f} °/분  "
                        f"(정지 {elapsed:4.0f}초)   "
                        f"누적 회전 {total_turn_deg:+8.1f}°",
                        end="\r",
                    )
            else:
                still_start = None
                print(
                    f"  회전 중 {rate:6.1f} °/초              "
                    f"누적 회전 {total_turn_deg:+8.1f}°",
                    end="\r",
                )

            sys.stdout.flush()
    except KeyboardInterrupt:
        print(f"\n\n최종 누적 회전: {total_turn_deg:+.1f}°")
    finally:
        node.destroy_node()
        rclpy.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
