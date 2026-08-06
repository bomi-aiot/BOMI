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


class BeamController:
    """xvf_host 프로그램을 실행해서 마이크의 빔 방향을 고정/해제한다."""

    def __init__(self):
        # .env에 적힌 설정값들을 읽어온다.
        self.enabled = os.getenv("BEAM_FIX_ENABLED", "0") == "1"
        self.host_path = os.getenv("XVF_HOST_PATH", "").strip()
        self.protocol = os.getenv("XVF_HOST_PROTOCOL", "").strip()
        self.front_deg = float(os.getenv("BEAM_FRONT_AZIMUTH_DEG", "90"))
        self.gating = os.getenv("BEAM_GATING", "0") == "1"
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

    def reset(self) -> None:
        """빔 고정을 풀고 원래 상태(방향 자동 추적)로 되돌린다."""
        if not self._available():
            return
        self._run("AUDIO_MGR_OP_L", "8", "0")   # 녹음 소리를 기본으로
        self._run("AEC_FIXEDBEAMSONOFF", "0")   # 고정 모드 끄기
        print("[BeamController] 빔 고정 해제(자동 추적으로 복귀)")

    def read_direction_deg(self) -> float:
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

        마이크(xvf_host)를 못 찾으면 방향을 읽을 수 없으므로 에러를 낸다.
        (호출하는 쪽에서 이 에러를 잡아 '방향 모름'으로 처리하면 된다.)
        """
        if not self._available():
            raise RuntimeError(f"xvf_host를 찾을 수 없어 방향을 읽을 수 없음: {self.host_path!r}")

        out = self._run("AEC_AZIMUTH_VALUES")

        # 결과 글자를 공백으로 쪼갠 뒤, 숫자로 바꿀 수 있는 것만 모은다.
        # 괄호가 붙은 "(90.00" 이나 "deg)" 같은 조각은 숫자로 못 바꿔서 자동으로 걸러진다.
        # 그래서 순수한 라디안 값 4개만 남는다.
        rads = []
        for token in out.split():
            try:
                rads.append(float(token))
            except ValueError:
                continue

        if len(rads) < 4:
            raise RuntimeError(f"AEC_AZIMUTH_VALUES 결과 해석 실패: {out!r}")

        # 4번째 값(라디안)을 사람이 보기 쉬운 '도'로 바꿔서 돌려준다.
        return math.degrees(rads[3]) % 360.0
