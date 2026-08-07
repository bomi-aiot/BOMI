"""카메라 입력, 사람 추적, 상태 판단과 화면 표시를 순서대로 조합한다."""

from bomi_vision.adapters.opencv import OpenCVCamera, OpenCVDebugView
from bomi_vision.adapters.tracking import UltralyticsByteTracker
from bomi_vision.follow import FollowCommandGenerator
from bomi_vision.primary_person import PrimaryPersonSelector
from bomi_vision.tracking import UserTrackingService


def run_person_tracking(
    tracker: UltralyticsByteTracker,
    tracking_service: UserTrackingService,
    follow_command_generator: FollowCommandGenerator,
    camera: OpenCVCamera,
    view: OpenCVDebugView,
    primary_selector: PrimaryPersonSelector | None = None,
) -> None:
    """사용자가 종료할 때까지 실시간 사람 추적 파이프라인을 실행한다.

    Args:
        tracker: 프레임에서 ByteTrack으로 모든 사람을 추적하는 어댑터.
        tracking_service: 사람 수와 누락 상태를 판단하는 서비스.
        follow_command_generator: 현재 위치로 추종 희망 명령을 만드는 서비스.
        camera: 실시간 프레임을 제공하는 카메라.
        view: 탐지 결과를 표시하고 종료 입력을 확인하는 화면.
        primary_selector: 여러 사람이 보일 때 대표 한 명만 남기는 전처리기.
            None 이거나 꺼져 있으면 목록을 그대로 넘긴다(기본 동작).

    Raises:
        RuntimeError: 카메라 읽기나 모델 추론에 실패한 경우.

    Side Effects:
        카메라를 읽고 화면을 표시하며, 종료 시 모든 자원을 정리한다.

    Note:
        카메라에서 읽은 원본 프레임을 좌우 반전하지 않고 탐지, 위치 계산,
        디버그 표시에 동일하게 사용한다.

        대표 인물 선택은 상태 기계 **앞**에서 후보 목록을 줄이는 방식이다
        (primary_person.py 모듈 docstring 참고). 그래서 하류의 안전 불변식
        ("여러 명이면 대상을 정하지 않는다")을 하나도 고치지 않는다.
        화면에는 걸러지기 전 목록을 그대로 넘겨, 누가 후보에서 빠졌는지
        사람이 눈으로 확인할 수 있게 한다.
    """
    try:
        while True:
            frame = camera.read()
            tracked_people = tracker.track(frame)
            frame_height, frame_width = frame.shape[:2]
            selected_people = tracked_people
            if primary_selector is not None:
                selected_people = primary_selector.select(
                    tracked_people,
                    frame_width=frame_width,
                    frame_height=frame_height,
                )
            result = tracking_service.update(
                selected_people,
                frame_width=frame_width,
                frame_height=frame_height,
            )
            follow_result = follow_command_generator.generate(result)
            if not view.show(frame, tracked_people, result, follow_result):
                break
    finally:
        camera.release()
        view.close()
