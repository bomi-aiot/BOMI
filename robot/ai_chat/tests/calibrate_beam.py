# robot/ai_chat/tests/calibrate_beam.py
"""로봇 조립 후 '정면이 몇 도인지' 한 번 측정하는 스크립트.

[왜 필요한가]
마이크가 말하는 '0도, 90도' 같은 각도는, 마이크를 로봇에 어느 방향으로
붙이느냐에 따라 실제 가리키는 곳이 달라진다. 그래서 조립을 끝낸 뒤
'로봇 정면이 마이크 기준 몇 도인지'를 직접 재서 알아내야 한다.
여기서 나온 각도를 .env의 BEAM_FRONT_AZIMUTH_DEG 에 넣으면, 그 뒤로는
로봇이 항상 그 방향(정면)만 듣게 된다.

[사용 방법]
    1. .env에 XVF_HOST_PATH(xvf_host 프로그램 위치)를 적어둔다.
    2. 로봇 정면(사람이 설 자리)에 사람이 서서 계속 말할 준비를 한다.
    3. ai_chat 폴더에서 실행:  python tests/calibrate_beam.py
    4. 10초 뒤 나오는 '정면 각도'를 .env의 BEAM_FRONT_AZIMUTH_DEG 에 적는다.

[어떻게 측정하나]
    측정하는 동안에는 빔 고정을 잠깐 꺼서(자동 추적 켜서) 마이크가 말하는
    사람 쪽을 따라가게 한다. 그 방향을 0.5초마다 여러 번 읽어서 평균을 낸다.
    단, 각도는 359도 다음이 0도로 돌아가는 '동그란' 값이라, 단순 평균을 쓰면
    엉뚱한 값(예: 350도와 10도의 평균을 180도로 계산)이 나올 수 있다.
    그래서 이런 경우에도 맞게 나오는 '원형 평균'을 사용한다.
"""

import math
import time

from dotenv import load_dotenv

from bomi_ai_chat.audio_io.beam_control import (
    BeamController,
    robust_azimuth_deg,
)

# BeamController 는 import 시점이 아니라 __init__ 에서 os.getenv 를 읽는다. 실제로 env 를
# 읽는 시점은 main() 의 BeamController() 이므로, 이 한 줄이 그보다 앞서면 충분하다.
load_dotenv()

SAMPLE_SECONDS = 10     # 총 몇 초 동안 측정할지
SAMPLE_INTERVAL = 0.5   # 몇 초 간격으로 방향을 읽을지


def circular_mean_deg(degrees: list[float]) -> float:
    """각도들의 '원형 평균'을 0~360 범위로 계산한다.

    각도는 동그랗게 이어져서(359도 다음이 0도) 그냥 더해서 나누면 틀린다.
    그래서 각 각도를 좌표(sin, cos)로 바꿔 평균을 낸 뒤 다시 각도로 되돌린다.
    이렇게 하면 350도와 10도의 평균이 제대로 0도로 나온다.
    """
    sin_sum = sum(math.sin(math.radians(d)) for d in degrees)
    cos_sum = sum(math.cos(math.radians(d)) for d in degrees)
    return math.degrees(math.atan2(sin_sum, cos_sum)) % 360.0


def main():
    bc = BeamController()

    # xvf_host 위치가 없거나 파일을 못 찾으면 안내 후 종료.
    if not bc.host_path:
        raise SystemExit("XVF_HOST_PATH가 설정되지 않았습니다 (.env를 확인하세요)")
    if not bc._available():
        raise SystemExit(f"xvf_host 프로그램을 찾을 수 없습니다: {bc.host_path!r}")

    # 측정 중에는 빔 고정을 꺼서 마이크가 말하는 사람을 따라가게 한다.
    bc._run("AEC_FIXEDBEAMSONOFF", "0")

    print(f"로봇 '정면'에 서서 계속 말씀해주세요. {SAMPLE_SECONDS}초간 방향을 측정합니다...")

    # 0.5초마다 현재 방향을 읽어서 모은다.
    samples: list[float] = []
    end = time.time() + SAMPLE_SECONDS
    while time.time() < end:
        try:
            deg = bc.read_direction_deg()
            print(f"  현재 방향: {deg:6.1f} 도")
            samples.append(deg)
        except RuntimeError as exc:
            print(f"  (읽기 실패: {exc})")
        time.sleep(SAMPLE_INTERVAL)

    # 한 번도 못 읽었으면 연결/말소리 문제일 가능성이 높다.
    if not samples:
        raise SystemExit("방향을 하나도 읽지 못했습니다. 마이크 연결과 말소리를 확인하세요.")

    # 말이 끊기면 마이크가 전혀 다른 방향을 잡는다. 단순 평균은 그런 값까지
    # 섞어 두 무리 사이의 무의미한 각도를 내므로, 가장 큰 무리만 평균한다.
    front = robust_azimuth_deg(samples)
    agreed = [
        value for value in samples
        if abs((value - front + 180.0) % 360.0 - 180.0) <= 30.0
    ]

    print("\n=== 측정 결과 ===")
    print(f"읽은 횟수: {len(samples)}회 (그 중 일치 {len(agreed)}회)")
    print(f"정면 각도: {front:.1f} 도")

    if len(agreed) < len(samples) * 0.6:
        print(
            "\n⚠️ 일치하는 값이 적습니다. 10초 내내 쉬지 않고 말해야 합니다 —"
            "\n   말이 끊기면 마이크가 엉뚱한 방향을 잡습니다. 다시 측정하세요."
        )
        return

    print(f"\n아래 값을 .env에 넣으세요:\n  BEAM_FRONT_AZIMUTH_DEG={front:.1f}")


if __name__ == "__main__":
    main()
