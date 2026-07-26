"""Ultralytics YOLO 결과를 프로젝트의 사람 탐지 결과로 변환한다.

외부 모델 객체의 접근과 해석을 이 모듈에 한정하고 application 계층에는
``PersonDetection`` 목록만 반환한다.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from bomi_vision.domain import PersonDetection

# COCO 사전 학습 모델에서 person 클래스에 할당된 식별자다.
PERSON_CLASS_ID = 0


@dataclass(frozen=True)
class DetectionCandidate:
    """외부 모델에서 추출한 하나의 원시 탐지 후보를 표현한다."""

    class_id: int
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


class _ListConvertible(Protocol):
    """Ultralytics 텐서에서 일반 목록을 얻기 위한 최소 계약이다."""

    def tolist(self) -> list[list[float]]:
        """텐서 값을 중첩 목록으로 반환한다."""


class _Boxes(Protocol):
    """Ultralytics Boxes 중 변환에 필요한 속성만 정의한다."""

    data: _ListConvertible


class _Result(Protocol):
    """Ultralytics Results 중 변환에 필요한 속성만 정의한다."""

    boxes: _Boxes | None


class _Model(Protocol):
    """Ultralytics 모델 호출에 필요한 최소 계약이다."""

    def predict(
        self,
        source: object,
        *,
        conf: float,
        verbose: bool,
    ) -> Sequence[_Result]:
        """프레임에 대한 모델 추론 결과를 반환한다."""


def convert_person_detections(
    candidates: Iterable[DetectionCandidate],
    confidence_threshold: float,
) -> list[PersonDetection]:
    """원시 탐지 후보에서 신뢰도 기준을 만족하는 사람만 변환한다.

    Args:
        candidates: 외부 모델에서 단순 값으로 추출한 탐지 후보.
        confidence_threshold: 포함할 최소 신뢰도이며 0.0 이상 1.0 이하다.

    Returns:
        입력 순서를 유지한 사람 탐지 결과 목록.

    Raises:
        ValueError: 임계값이나 포함 대상 사람의 좌표가 유효하지 않은 경우.
    """
    validate_confidence(confidence_threshold)
    return [
        PersonDetection(
            confidence=candidate.confidence,
            x1=candidate.x1,
            y1=candidate.y1,
            x2=candidate.x2,
            y2=candidate.y2,
        )
        for candidate in candidates
        if candidate.class_id == PERSON_CLASS_ID and candidate.confidence >= confidence_threshold
    ]


def validate_confidence(value: float) -> float:
    """명령행과 탐지기에 공통으로 사용하는 신뢰도 범위를 검증한다.

    Args:
        value: 검사할 신뢰도 값.

    Returns:
        유효한 입력값.

    Raises:
        ValueError: 값이 0.0 이상 1.0 이하가 아닌 경우.
    """
    if not 0.0 <= value <= 1.0:
        raise ValueError("Confidence must be between 0.0 and 1.0.")
    return value


class UltralyticsPersonDetector:
    """YOLO 모델을 로드하고 현재 프레임의 모든 사람을 탐지한다.

    모델 경로와 신뢰도 임계값을 생성 시 주입받으며, 외부 결과 객체를
    단순 값으로 추출한 뒤 도메인 결과로 변환한다.
    """

    def __init__(self, model_path: str, confidence_threshold: float) -> None:
        """YOLO 모델을 준비한다.

        Args:
            model_path: Ultralytics가 로드할 모델 이름 또는 파일 경로.
            confidence_threshold: 사람 탐지에 사용할 최소 신뢰도.

        Raises:
            ValueError: 신뢰도 범위가 유효하지 않은 경우.
            RuntimeError: 모델을 불러올 수 없는 경우.
        """
        validate_confidence(confidence_threshold)
        try:
            from ultralytics import YOLO

            self._model = cast(_Model, YOLO(model_path))
        except Exception as error:
            raise RuntimeError(f"Failed to load YOLO model '{model_path}'.") from error
        self._confidence_threshold = confidence_threshold

    def detect(self, frame: object) -> list[PersonDetection]:
        """OpenCV 프레임에서 유효한 모든 사람 탐지 결과를 반환한다.

        Args:
            frame: OpenCV에서 읽은 비어 있지 않은 이미지 프레임.

        Returns:
            신뢰도 기준을 만족한 모든 사람의 탐지 결과.

        Raises:
            ValueError: 입력 프레임이 비어 있거나 유효하지 않은 경우.
            RuntimeError: 모델 출력 형식이 유효하지 않거나 추론에 실패한 경우.
        """
        if frame is None or getattr(frame, "size", 0) == 0:
            raise ValueError("Input frame must be a non-empty image.")
        try:
            results = self._model.predict(
                frame,
                conf=self._confidence_threshold,
                verbose=False,
            )
            candidates = self._extract_candidates(results)
            return convert_person_detections(candidates, self._confidence_threshold)
        except (ValueError, RuntimeError):
            raise
        except Exception as error:
            raise RuntimeError("Failed to run YOLO inference.") from error

    @staticmethod
    def _extract_candidates(results: Sequence[_Result]) -> list[DetectionCandidate]:
        """Ultralytics 결과에서 필터링에 필요한 스칼라 값만 추출한다."""
        candidates: list[DetectionCandidate] = []
        for result in results:
            if result.boxes is None:
                continue
            for row in result.boxes.data.tolist():
                if len(row) < 6:
                    raise RuntimeError("YOLO returned an invalid detection row.")
                x1, y1, x2, y2, confidence, class_id = row[:6]
                candidates.append(
                    DetectionCandidate(
                        class_id=int(class_id),
                        confidence=float(confidence),
                        x1=float(x1),
                        y1=float(y1),
                        x2=float(x2),
                        y2=float(y2),
                    )
                )
        return candidates
