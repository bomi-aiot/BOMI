# robot/ai_chat/src/bomi_ai_chat/audio_io/beam_control.py
"""마이크(ReSpeaker XVF3800)가 '앞쪽 방향'만 듣도록 고정하는 코드.

[배경 지식]
이 마이크는 안에 마이크가 4개 들어있어서, 소리가 어느 방향에서 오는지
알 수 있고 특정 방향 소리만 골라서 크게 들을 수 있다. 이렇게 특정 방향에
귀를 기울이는 걸 '빔(beam)'이라고 부른다. 기본 상태에서는 이 빔이 소리가
나는 쪽으로 자동으로 따라 움직인다(= 말하는 사람을 자동으로 쫓아감).

우리는 로봇 정면에 선 사람만 듣고 싶기 때문에, 이 빔이 따라다니지 않고
'앞쪽 한 방향'에 딱 고정되도록 설정한다. 그러면 옆이나 뒤에서 나는 잡음,
다른 사람 목소리를 덜 듣게 된다.

[중요: 소리 녹음과 방향 설정은 별개다]
- 소리를 실제로 녹음하는 건 mic_array.py가 담당한다(sounddevice 사용).
- 마이크의 방향을 어디로 고정할지 '설정'하는 건 이 파일이 담당한다.
방향 설정은 소리 녹음과 전혀 다른 통로로 이뤄진다. 제조사(Seeed)가 준
'xvf_host'라는 작은 프로그램에 명령어를 보내면 마이크 설정이 바뀐다.
이 파일은 그 프로그램을 대신 실행해 주는 역할이다.

[앞쪽 고정에 필요한 명령 3개]
1. AEC_FIXEDBEAMSAZIMUTH_VALUES <각도> <각도>
     -> 빔을 어느 방향(각도)에 고정할지 정한다. 각도 단위는 라디안.
2. AEC_FIXEDBEAMSONOFF 1
     -> '방향 고정 모드'를 켠다. 이제 빔이 자동으로 안 따라다니고 멈춘다.
3. AUDIO_MGR_OP_L 6 0
     -> 녹음되어 나오는 소리를 '고정한 방향의 빔'으로 바꾼다.
       (이게 없으면 방향만 고정될 뿐, 실제 녹음되는 소리는 여전히
        '제일 크게 들리는 사람' 쪽을 따라간다. 그래서 꼭 필요하다.)

[원래대로 되돌리려면]
    AUDIO_MGR_OP_L 8 0     -> 녹음 소리를 기본(자동 추적)으로
    AEC_FIXEDBEAMSONOFF 0  -> 방향 고정 모드 끄기

참고: 위 설정들은 마이크 전원을 껐다 켜거나 USB를 다시 꽂으면 초기화된다.
마이크에 영구 저장하고 싶으면 SAVE_CONFIGURATION 1 명령을 한 번 실행하면 된다.

[.env로 조절하는 값들]
    BEAM_FIX_ENABLED       "1"이면 대화 시작 시 빔을 앞쪽으로 고정한다. 그 외엔 안 함(기본값 "0").
    XVF_HOST_PATH          xvf_host 프로그램 파일 위치(윈도우는 xvf_host.exe).
    XVF_HOST_PROTOCOL      마이크와 통신하는 방식(보통 비워두면 USB로 자동).
    BEAM_FRONT_AZIMUTH_DEG 로봇 정면이 몇 도인지(각도). 조립 후 calibrate_beam.py로 측정해서 넣는다.
    BEAM_GATING            "1"이면 고정한 방향 외의 빔 소리를 아예 없앤다(보통 "0").
    BEAM_NOISE_THRESHOLD   간섭 제거기 문턱값. 낮출수록 먼 방향(예: 정반대) 목소리까지
                           지운다(예: 0.2). 비워두면 장치 기본값을 그대로 쓴다.
"""

import math
import os
import subprocess

AZIMUTH_COMMAND = "AEC_AZIMUTH_VALUES"


def parse_azimuth_radians(output: str) -> list[float] | None:
    """xvf_host 출력에서 방향 라디안 4개를 뽑는다.

    AEC_AZIMUTH_VALUES 로 시작하는 줄만 본다. 그 앞에 붙는 장치 배너
    ("... VID: 10374 PID: 26 ...")의 숫자가 섞이면 인덱스가 밀려 엉뚱한
    빔 각도를 읽게 되기 때문이다.

    Args:
        output: xvf_host AEC_AZIMUTH_VALUES 실행 결과 전체.

    Returns:
        라디안 4개. 해당 줄이 없거나 숫자가 4개 미만이면 None.
    """
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped.startswith(AZIMUTH_COMMAND):
            continue
        values = []
        for token in stripped[len(AZIMUTH_COMMAND):].split():
            try:
                values.append(float(token))
            except ValueError:
                continue
        if len(values) >= 4:
            return values[:4]
    return None


def azimuth_agreement(
    samples: list[float],
    tolerance_deg: float = 30.0,
) -> tuple[float | None, int]:
    """가장 큰 무리의 대표 각도와 그 무리의 표본 수를 함께 돌려준다.

    표본 수는 "이 각도를 믿어도 되는가"의 근거다. 마이크는 화자가 옮겨도
    한동안 이전 방향에 고정돼 있고, 소리가 없으면 값이 마구 튄다 —
    그럴 때는 무리가 만들어지지 않으므로 수가 작게 나온다.
    """
    if not samples:
        return None, 0

    best_cluster: list[float] = []
    for candidate in samples:
        cluster = [
            value for value in samples
            if abs(_shortest_delta_deg(value, candidate)) <= tolerance_deg
        ]
        if len(cluster) > len(best_cluster):
            best_cluster = cluster

    sin_sum = sum(math.sin(math.radians(v)) for v in best_cluster)
    cos_sum = sum(math.cos(math.radians(v)) for v in best_cluster)
    angle = math.degrees(math.atan2(sin_sum, cos_sum)) % 360.0
    return angle, len(best_cluster)


def robust_azimuth_deg(
    samples: list[float],
    tolerance_deg: float = 30.0,
) -> float | None:
    """여러 번 읽은 방향에서 튀는 값을 걸러 하나로 모은다.

    마이크의 방향 추정은 말이 이어지는 동안에는 촘촘히 일치하지만
    (실측 +64.2/+64.1/+64.5/+63.8), 중간에 전혀 다른 값이 하나씩 섞인다
    (같은 구간에 -152.5). "보미야"는 짧아서 한 번만 읽으면 그 튀는 값을
    그대로 잡을 확률이 크다 — 그래서 가장 많은 이웃을 가진 값을 고르고
    그 무리만 평균한다(다수결).

    Args:
        samples: 0~360 범위의 방향 각도들.
        tolerance_deg: 같은 무리로 볼 각도 차이.

    Returns:
        대표 각도(0~360). samples 가 비어 있으면 None.
    """
    angle, _ = azimuth_agreement(samples, tolerance_deg)
    return angle


def _shortest_delta_deg(a: float, b: float) -> float:
    """두 각도의 최단 차이(-180~180)."""
    return (a - b + 180.0) % 360.0 - 180.0


SPEAKER_DIRECTION_COMMAND = "AUDIO_MGR_SELECTED_AZIMUTHS"


def parse_speaker_direction_deg(output: str) -> float | None:
    """xvf_host 출력에서 "화자 방향"(처리된 DoA)을 도 단위로 뽑는다.

    AUDIO_MGR_SELECTED_AZIMUTHS 의 0번 값이 장치가 말소리 에너지로 골라낸
    화자 방향이다. 방향을 못 정하면 장치가 NaN 을 준다 — 그때는 None 을
    돌려줘 "모름"으로 다룬다. 쓰레기 각도를 방향인 척 넘기면 로봇이 엉뚱한
    곳으로 확신 있게 돈다(2026-08-09 실기).

    지금까지 쓰던 AEC_AZIMUTH_VALUES 는 화자 방향이 아니라 빔포머 상태
    (beam 1, beam 2, free-running)라서 화자가 옮겨도 한참 따라오지 않았다.
    """
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped.startswith(SPEAKER_DIRECTION_COMMAND):
            continue
        for token in stripped[len(SPEAKER_DIRECTION_COMMAND):].split():
            try:
                value = float(token)
            except ValueError:
                continue
            if math.isnan(value):
                return None
            return math.degrees(value) % 360.0
    return None


class BeamController:
    """xvf_host 프로그램을 실행해서 마이크의 빔 방향을 고정/해제한다."""

    def __init__(self):
        # .env에 적힌 설정값들을 읽어온다.
        self.enabled = os.getenv("BEAM_FIX_ENABLED", "0") == "1"
        self.host_path = os.getenv("XVF_HOST_PATH", "").strip()
        self.protocol = os.getenv("XVF_HOST_PROTOCOL", "").strip()
        self.front_deg = float(os.getenv("BEAM_FRONT_AZIMUTH_DEG", "90"))
        self.gating = os.getenv("BEAM_GATING", "0") == "1"
        # 방향 판별용 고정 빔 두 개의 각도(장치 좌표계). 공장 초기값은
        # 둘 다 0도라 방향이 갈리지 않는다 — 좌우로 벌려 놓는다.
        self.direction_beam_left_deg = float(
            os.getenv("BEAM_DIRECTION_LEFT_DEG", "90"))
        self.direction_beam_right_deg = float(
            os.getenv("BEAM_DIRECTION_RIGHT_DEG", "270"))
        # 간섭 제거기 문턱값. 비워두면(미설정) 장치 기본값을 그대로 둔다.
        raw_noise = os.getenv("BEAM_NOISE_THRESHOLD", "").strip()
        self.noise_threshold = float(raw_noise) if raw_noise else None

    def _available(self) -> bool:
        """xvf_host 프로그램 파일이 실제로 그 위치에 있는지 확인한다."""
        return bool(self.host_path) and os.path.exists(self.host_path)

    def _run(self, *args) -> str:
        """xvf_host에 명령어 하나를 보내고, 화면에 출력된 결과 글자를 돌려준다."""
        # 예: xvf_host.exe AEC_FIXEDBEAMSONOFF 1  <- 이런 형태의 명령을 만든다.
        cmd = [self.host_path]
        if self.protocol:
            cmd += ["--use", self.protocol]
        cmd += [str(a) for a in args]

        result = subprocess.run(
            cmd,
            # xvf_host는 같은 폴더에 있는 command_map.dll 파일이 필요해서,
            # 그 프로그램이 있는 폴더 안에서 실행되도록 위치를 맞춰준다.
            cwd=os.path.dirname(self.host_path) or None,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # 명령이 실패하면(0이 아닌 코드로 끝나면) 이유를 담아 에러를 낸다.
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"xvf_host 실행 실패 ({' '.join(map(str, args))}): {detail}")
        return result.stdout.strip()

    def apply_fixed_beam(self) -> bool:
        """마이크 빔을 설정된 '앞쪽 방향'에 고정한다.

        실제로 고정했으면 True, 안 하고 넘어갔으면 False를 돌려준다.
        노트북에서 개발할 때처럼 마이크가 없거나 BEAM_FIX_ENABLED가 꺼져
        있으면, 에러 없이 그냥 넘어가서 나머지 대화 기능은 정상 동작하게 한다.
        """
        # 기능이 꺼져 있으면 아무것도 안 하고 넘어간다.
        if not self.enabled:
            print("[BeamController] BEAM_FIX_ENABLED != 1 -> 빔 고정 건너뜀")
            return False
        # xvf_host 프로그램을 못 찾으면(경로 잘못됨/장치 없음) 넘어간다.
        if not self._available():
            print(f"[BeamController] xvf_host를 찾을 수 없음({self.host_path!r}) -> 빔 고정 건너뜀")
            return False

        # 사람이 이해하기 쉬운 '도(90도)' 단위를 마이크가 쓰는 '라디안'으로 바꾼다.
        rad = math.radians(self.front_deg)
        rad_str = f"{rad:.5f}"

        # 위 설명의 명령 3개를 순서대로 보낸다.
        self._run("AEC_FIXEDBEAMSAZIMUTH_VALUES", rad_str, rad_str)  # 1) 방향 정하기
        self._run("AEC_FIXEDBEAMSONOFF", "1")                        # 2) 고정 모드 켜기
        self._run("AUDIO_MGR_OP_L", "6", "0")                       # 3) 녹음 소리를 고정 빔으로

        # 4) 다른 방향(특히 정반대) 목소리를 더 억제하는 튜닝.
        # 이 값들은 USB 재연결/재부팅 시 초기화되므로, 대화 시작마다 여기서 다시
        # 걸어줘야 튜닝이 유지된다. 게이팅은 항상 명시적으로 0/1을 지정한다.
        self._run("AEC_FIXEDBEAMSGATING", "1" if self.gating else "0")
        if self.noise_threshold is not None:
            thr = f"{self.noise_threshold:.3f}"
            self._run("AEC_FIXEDBEAMNOISETHR", thr, thr)

        noise_msg = f", noise={self.noise_threshold}" if self.noise_threshold is not None else ""
        print(f"[BeamController] 빔 고정 완료: {self.front_deg:.1f}도 ({rad_str} 라디안)"
              f"{', gating 켬' if self.gating else ''}{noise_msg}")
        return True

    def apply_direction_beams(self) -> bool:
        """방향 판별용으로 고정 빔 두 개를 좌/우에 벌려 놓는다.

        왜 필요한가 (2026-08-09 실기)
            AUDIO_MGR_SELECTED_AZIMUTHS 의 "화자 방향"은 문서대로 *각 고정
            빔의 DoA 중에서* 고른다. 공장 초기값은 두 빔이 모두 0도라 고를
            것이 없어, 방향이 물리적 위치와 무관하게 흩어졌다. 좌/우로
            벌려 놓으면 값이 그 두 각도로 스냅되어 좌우 판별이 안정된다
            (실측: 왼쪽 270.0, 오른쪽 90.0, 표본 8/8 일치).

        apply_fixed_beam 과 달리 **녹음 경로(AUDIO_MGR_OP_L)는 건드리지
        않는다.** 우리는 방향 판별만 원하지, 마이크가 한 방향만 듣게 만들
        생각은 없다.

        주의: 이 설정은 USB 재연결·재부팅으로 초기화된다. 그래서 기동할
        때마다 다시 걸어야 한다.

        Returns:
            실제로 걸었으면 True, 장치가 없어 건너뛰었으면 False.
        """
        if not self._available():
            print(f"[BeamController] xvf_host 없음({self.host_path!r}) "
                  "-> 방향 빔 설정 건너뜀")
            return False

        left = math.radians(self.direction_beam_left_deg)
        right = math.radians(self.direction_beam_right_deg)
        self._run(
            "AEC_FIXEDBEAMSAZIMUTH_VALUES", f"{left:.5f}", f"{right:.5f}")
        self._run("AEC_FIXEDBEAMSONOFF", "1")
        print(
            "[BeamController] 방향 판별용 빔 설정: "
            f"{self.direction_beam_left_deg:.0f}도 / "
            f"{self.direction_beam_right_deg:.0f}도")
        return True

    def reset(self) -> None:
        """빔 고정을 풀고 원래 상태(방향 자동 추적)로 되돌린다."""
        if not self._available():
            return
        self._run("AUDIO_MGR_OP_L", "8", "0")   # 녹음 소리를 기본으로
        self._run("AEC_FIXEDBEAMSONOFF", "0")   # 고정 모드 끄기
        print("[BeamController] 빔 고정 해제(자동 추적으로 복귀)")

    def read_direction_deg(self, samples: int = 1) -> float:
        """지금 마이크가 소리를 잡고 있는 방향을 '도(0~360)' 단위로 읽어온다.

        로봇 정면 각도를 측정할 때 사용한다(calibrate_beam.py에서 호출).

        마이크에 AEC_AZIMUTH_VALUES 명령을 보내면 방향 4개가 돌아온다:
            [빔1, 빔2, 자동추적 빔, 최종 선택된 빔]
        이 중 마지막 값(최종 선택된 빔)이 '지금 말하는 사람 방향'이라서
        그 값을 사용한다.

        돌아오는 글자 예시:
            AEC_AZIMUTH_VALUES 1.57080 (90.00 deg) 1.57080 (90.00 deg) \
                1.20925 (69.28 deg) 1.20925 (69.28 deg)
        여기서 라디안 숫자 4개(1.57080, 1.57080, 1.20925, 1.20925)만 뽑는다.

        ⚠️ 반드시 AEC_AZIMUTH_VALUES 로 시작하는 줄에서만 숫자를 뽑는다.
        xvf_host 는 그 앞에 장치 배너를 함께 찍을 때가 있는데,
            Device (USB)::device_init() -- Found device VID: 10374 PID: 26 ...
        여기 섞인 10374·26 이 숫자로 잡히면 인덱스가 밀려 4번째 값 대신
        고정 빔 각도를 읽는다. 그러면 사람이 어디서 부르든 늘 같은 각도가
        나와 로봇이 엉뚱한 방향으로 돈다(2026-08-09 실기에서 세 번의 호출이
        소수점까지 같은 값이라 발견).

        마이크(xvf_host)를 못 찾으면 방향을 읽을 수 없으므로 에러를 낸다.
        (호출하는 쪽에서 이 에러를 잡아 '방향 모름'으로 처리하면 된다.)
        """
        direction = self.read_speaker_direction_deg(samples=samples)
        if direction is None:
            raise RuntimeError("화자 방향을 얻지 못했습니다(장치가 NaN 을 반환).")
        return direction

    def read_speaker_direction_deg(self, samples: int = 1) -> float | None:
        """화자 방향을 읽되, 장치가 방향을 못 정하면 None 을 돌려준다.

        말소리가 없으면 장치는 NaN 을 준다 — 흔한 정상 상태다. 이걸 예외로
        던지면 방향을 계속 샘플링하는 쪽에서 초당 몇 번씩 트레이스백이 쌓여
        정작 봐야 할 로그가 묻힌다(2026-08-09 실기에서 실제로 그랬다).
        """
        if not self._available():
            return None

        readings: list[float] = []
        for _ in range(max(1, samples)):
            degrees = parse_speaker_direction_deg(
                self._run(SPEAKER_DIRECTION_COMMAND))
            if degrees is not None:
                readings.append(degrees)
        return robust_azimuth_deg(readings)
