"""OpenCV 카메라 입력과 사람 탐지 결과 표시를 담당한다."""

from collections.abc import Sequence
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from bomi_vision.domain import PersonDetection

Frame = NDArray[np.uint8]


class OpenCVCamera:
    """하나의 OpenCV 카메라 연결과 프레임 수명 주기를 관리한다."""

    def __init__(self, camera_index: int) -> None:
        """카메라를 열고 사용 가능 여부를 확인한다.

        Args:
            camera_index: 운영체제에 등록된 0 이상의 카메라 번호.

        Raises:
            RuntimeError: 카메라를 열 수 없는 경우.
        """
        self._capture = cv2.VideoCapture(camera_index)
        if not self._capture.isOpened():
            self._capture.release()
            raise RuntimeError(f"Failed to open camera index {camera_index}.")

    def read(self) -> Frame:
        """다음 카메라 프레임을 읽는다.

        Returns:
            OpenCV BGR 이미지 프레임.

        Raises:
            RuntimeError: 프레임을 읽지 못한 경우.
        """
        success, frame = self._capture.read()
        if not success or frame is None:
            raise RuntimeError("Failed to read a frame from the camera.")
        return cast(Frame, frame)

    def release(self) -> None:
        """카메라 장치를 다른 프로그램이 사용할 수 있도록 해제한다."""
        self._capture.release()


class OpenCVDebugView:
    """사람 탐지 결과를 OpenCV 창에 표시하고 종료 입력을 확인한다."""

    def __init__(self, window_name: str = "BOMI Person Detection") -> None:
        """디버그 창 이름을 설정한다.

        Args:
            window_name: OpenCV 창 제목.
        """
        self._window_name = window_name

    def show(self, frame: Frame, detections: Sequence[PersonDetection]) -> bool:
        """현재 프레임에 모든 사람의 박스와 신뢰도를 표시한다.

        Args:
            frame: 표시할 OpenCV BGR 이미지.
            detections: 화면에 그릴 모든 사람 탐지 결과.

        Returns:
            사용자가 ``q`` 키를 눌렀으면 ``False``, 아니면 ``True``.

        Side Effects:
            입력 프레임에 주석을 그리고 OpenCV 창을 갱신한다.
        """
        for detection in detections:
            top_left = (round(detection.x1), round(detection.y1))
            bottom_right = (round(detection.x2), round(detection.y2))
            cv2.rectangle(frame, top_left, bottom_right, (0, 255, 0), 2)
            label_position = (top_left[0], max(20, top_left[1] - 8))
            cv2.putText(
                frame,
                f"person {detection.confidence:.2f}",
                label_position,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
        cv2.imshow(self._window_name, frame)
        return cv2.waitKey(1) & 0xFF != ord("q")

    def close(self) -> None:
        """이 프로세스가 생성한 모든 OpenCV 창을 닫는다."""
        cv2.destroyAllWindows()
