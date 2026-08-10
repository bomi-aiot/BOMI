"""자이로 배율 보정 계수(gyro_scale)를 실측으로 정한다.

왜 필요한가: EKF는 yaw를 자이로 하나로만 만든다(core/config/ekf.yaml).
자이로가 회전량을 실제보다 크게 세면 로봇이 90° 돌 때 지도는 103° 돌았다고
믿는다. 그러면 회전할 때마다 방이 조금씩 어긋난 채 겹쳐 쌓인다.
2026-08-07 실기에서 한 바퀴를 411°로 세는 것을 확인했다.

이 오차는 공간이 특징적이면 스캔 매칭이 가려준다. 특징 없는 빈 직사각형
방에서는 가려줄 근거가 없어 그대로 드러난다. 그래서 같은 코드가 어떤
공간에서는 멀쩡하고 어떤 공간에서는 무너진다.

쓰는 법 (매핑 스택이 떠 있는 상태에서):

  1. 로봇 정면을 벽이나 바닥 테이프에 맞춰 세운다. 시작 방향을 눈으로
     확실히 기억할 수 있는 자리여야 한다.

  2. 이 스크립트를 띄운다. 바퀴 수는 많을수록 정확하다(권장 2바퀴).

       python3 calibrate_gyro.py 2

  3. 안내가 나오면 조이스틱으로 제자리에서 **왼쪽(반시계)** 으로 정확히
     그 바퀴 수만큼 돌리고, 처음 방향에 정확히 맞춰 멈춘다.
     천천히 돌린다. 급회전은 바퀴가 긁혀 측정을 흐린다.

  4. Enter를 누르면 계수를 계산해 알려준다.

  5. 알려준 값을 core/config/pico_driver.yaml의 gyro_scale에 적고
     colcon build --packages-select core 후 스택을 다시 띄운다.
     검증은 이 스크립트를 다시 돌려 계수가 1.00 근처로 나오는지 본다.
"""
import math
import sys
import threading
import time

import rclpy
from rclpy.node import Node
from tf2_ros import Buffer, TransformListener


def _yaw_of(transform) -> float:
    """평면 회전만 있는 변환에서 yaw(rad)를 뽑는다."""
    q = transform.transform.rotation
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)

    return math.atan2(siny, cosy)


def main() -> int:
    """제자리 회전을 재서 gyro_scale 권장값을 출력한다."""
    turns = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    expected_deg = 360.0 * turns

    rclpy.init()
    node = Node("calibrate_gyro")
    buffer = Buffer()
    TransformListener(buffer, node)

    total_deg = 0.0
    previous = None
    running = True

    def spin() -> None:
        nonlocal total_deg, previous
        while running:
            rclpy.spin_once(node, timeout_sec=0.05)
            try:
                transform = buffer.lookup_transform(
                    "odom", "base_link", rclpy.time.Time()
                )
            except Exception:
                continue

            yaw = _yaw_of(transform)
            if previous is not None:
                # -pi/pi 경계를 한 바퀴로 세지 않도록 최단각으로 누적한다.
                total_deg += math.degrees(
                    math.atan2(
                        math.sin(yaw - previous),
                        math.cos(yaw - previous),
                    )
                )
            previous = yaw

    thread = threading.Thread(target=spin, daemon=True)

    print(f"\n제자리에서 왼쪽(반시계)으로 {turns:g}바퀴 = {expected_deg:.0f}°")
    print("시작 방향을 벽이나 테이프에 맞춰 세우고 Enter를 누르세요.")
    input("준비되면 Enter > ")

    thread.start()
    time.sleep(0.5)
    total_deg = 0.0
    previous = None

    print("\n돌리세요. 처음 방향으로 정확히 돌아와 멈춘 뒤 Enter.")
    last_print = 0.0
    while True:
        if time.time() - last_print > 0.3:
            last_print = time.time()
            print(f"  현재 누적 {total_deg:+8.1f}°", end="\r", flush=True)

        import select
        if select.select([sys.stdin], [], [], 0.1)[0]:
            sys.stdin.readline()
            break

    running = False
    measured = total_deg
    print(f"\n\n측정 누적 회전 : {measured:+.1f}°")
    print(f"실제 회전      : {expected_deg:+.1f}°")

    if abs(measured) < 1.0:
        print("\n측정값이 0에 가깝습니다. TF가 안 들어왔거나 안 돌았습니다.")
        node.destroy_node()
        rclpy.shutdown()
        return 1

    scale = expected_deg / abs(measured)
    print(f"\n권장 gyro_scale : {scale:.4f}")

    if abs(scale - 1.0) < 0.02:
        print("  (1.0에 가깝습니다 — 배율은 정상입니다.")
        print("   그래도 지도가 틀어지면 배율이 아니라 다른 원인입니다.)")
    else:
        percent = (1.0 / scale - 1.0) * 100.0
        print(f"  자이로가 실제보다 {percent:+.1f}% 크게 세고 있습니다.")
        print("\n  core/config/pico_driver.yaml 에 아래를 넣고")
        print("  colcon build --packages-select core 후 스택을 다시 띄우세요.")
        print(f"\n    gyro_scale: {scale:.4f}\n")

    node.destroy_node()
    rclpy.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
