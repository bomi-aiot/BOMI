# robot/ai_chat/tests/test_beam_manual.py
"""빔 고정이 실제로 되는지 눈으로 확인하는 수동 테스트.

마이크(ReSpeaker)가 USB로 연결된 '실제 컴퓨터'에서 실행해야 한다.
전체 대화(STT/LLM/TTS) 없이 BeamController만 따로 돌려서,
빔 고정 명령을 걸기 전/후/해제 후 상태를 되읽어 비교한다.

실행:  (ai_chat 폴더에서)  python tests/beam_manual_check.py

이 테스트는 확인을 위해 BEAM_FIX_ENABLED 값을 강제로 "1"로 켜고 시작한다.
(.env 파일은 건드리지 않는다.)
"""

import os

# .env를 읽기 전에 먼저 켜둔다. python-dotenv는 이미 설정된 값을 덮어쓰지 않으므로
# .env의 BEAM_FIX_ENABLED=0 이어도 이 테스트에서는 1로 동작한다.
os.environ["BEAM_FIX_ENABLED"] = "1"

from dotenv import load_dotenv

load_dotenv()

from bomi_ai_chat.audio_io.beam_control import BeamController


def show(bc: BeamController, label: str):
    """현재 마이크의 빔 관련 상태 3가지를 읽어서 출력한다."""
    print(f"\n[{label}]")
    print("  고정 모드 ON/OFF :", bc._run("AEC_FIXEDBEAMSONOFF"))
    print("  고정 빔 방향     :", bc._run("AEC_FIXEDBEAMSAZIMUTH_VALUES"))
    print("  좌채널 출력 경로 :", bc._run("AUDIO_MGR_OP_L"))


def main():
    bc = BeamController()

    print("=== 설정 확인 ===")
    print("  BEAM_FIX_ENABLED :", bc.enabled)
    print("  XVF_HOST_PATH    :", bc.host_path)
    print("  앞각(도)         :", bc.front_deg)

    if not bc._available():
        raise SystemExit(f"\nxvf_host를 찾을 수 없습니다: {bc.host_path!r}\n"
                         ".env의 XVF_HOST_PATH가 맞는지, 마이크가 연결됐는지 확인하세요.")

    # 1) 고정 전 상태
    show(bc, "고정 전 (지금 상태)")

    # 2) 빔 고정 적용
    print("\n>>> apply_fixed_beam() 실행")
    applied = bc.apply_fixed_beam()
    show(bc, "고정 후")

    # 간단 자동 판정: 고정 모드가 켜졌고(ON=1), 출력 경로가 6번(고정 빔)인지
    onoff_ok = bc._run("AEC_FIXEDBEAMSONOFF").split()[-1] == "1"
    route_ok = "[6]" in bc._run("AUDIO_MGR_OP_L")
    print("\n  -> 고정 모드 켜짐?      :", "OK" if onoff_ok else "실패")
    print("  -> 출력이 고정 빔으로?  :", "OK" if route_ok else "실패")

    # 3) 원상 복구
    print("\n>>> reset() 실행 (원래 자동 추적 상태로)")
    bc.reset()
    show(bc, "해제 후")

    if applied and onoff_ok and route_ok:
        print("\n결과: 빔 고정 정상 동작 확인")
    else:
        print("\n결과: 뭔가 예상과 다름 (위 출력값 확인 필요)")


if __name__ == "__main__":
    main()
