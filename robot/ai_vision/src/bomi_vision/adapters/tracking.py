"""Ultralytics 공식 ByteTrack 결과를 프로젝트 추적 계약으로 변환한다.

모델과 외부 결과 객체 접근은 이 어댑터에 한정하며 application 계층에는
``TrackedPerson`` 목록만 반환한다.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, cast

from bomi_vision.adapters.detection import PERSON_CLASS_ID, validate_confidence
from bomi_vision.domain import TrackedPerson


@dataclass(frozen=True)
class TrackingCandidate:
    """외부 추적 결과에서 추출한 하나의 원시 후보를 표현한다."""

    track_id: int | None
    class_id: int
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


class _ListConvertible(Protocol):
    """Ultralytics 텐서에서 일반 목록을 얻기 위한 최소 계약이다."""

    def tolist(self) -> list[object]:
        """텐서 값을 일반 목록으로 반환한다."""


class _Boxes(Protocol):
    """Ultralytics Boxes 중 추적 변환에 필요한 속성만 정의한다."""

    xyxy: _ListConvertible
    conf: _ListConvertible
    cls: _ListConvertible
    id: _ListConvertible | None


class _Result(Protocol):
    """Ultralytics Results 중 변환에 필요한 속성만 정의한다."""

    boxes: _Boxes | None


class _Model(Protocol):
    """Ultralytics 추적 호출에 필요한 최소 계약이다."""

    def track(
        self,
        source: object,
        *,
        conf: float,
        tracker: str,
        persist: bool,
        verbose: bool,
    ) -> Sequence[_Result]:
        """프레임의 ByteTrack 결과를 반환한다."""


def convert_tracked_people(
    candidates: Iterable[TrackingCandidate],
    confidence_threshold: float,
) -> list[TrackedPerson]:
    """유효한 Track ID가 있는 사람 후보만 도메인 결과로 변환한다."""
    validate_confidence(confidence_threshold)
    tracked_people: list[TrackedPerson] = []
    for candidate in candidates:
        if (
            candidate.class_id != PERSON_CLASS_ID
            or candidate.confidence < confidence_threshold
            or candidate.track_id is None
        ):
            continue
        tracked_people.append(
            TrackedPerson(
                track_id=candidate.track_id,
                confidence=candidate.confidence,
                x1=candidate.x1,
                y1=candidate.y1,
                x2=candidate.x2,
                y2=candidate.y2,
            )
        )
    return tracked_people


class UltralyticsByteTracker:
    """YOLO 모델의 공식 ByteTrack 통합으로 프레임 간 사람을 추적한다."""

    def __init__(
        self,
        model_path: str,
        confidence_threshold: float,
        tracker_name: str,
    ) -> None:
        """모델과 추적 설정을 준비한다."""
        validate_confidence(confidence_threshold)
        if not tracker_name:
            raise ValueError("Tracker name must not be empty.")
        try:
            from ultralytics import YOLO

            self._model = cast(_Model, YOLO(model_path))
        except Exception as error:
            raise RuntimeError(f"Failed to load YOLO model '{model_path}'.") from error
        self._confidence_threshold = confidence_threshold
        self._tracker_name = tracker_name

    def track(self, frame: object) -> list[TrackedPerson]:
        """현재 프레임을 추적하고 내부 도메인 결과만 반환한다."""
        if frame is None or getattr(frame, "size", 0) == 0:
            raise ValueError("Input frame must be a non-empty image.")
        try:
            results = self._model.track(
                frame,
                conf=self._confidence_threshold,
                tracker=self._tracker_name,
                persist=True,
                verbose=False,
            )
            return convert_tracked_people(
                self._extract_candidates(results),
                self._confidence_threshold,
            )
        except (ValueError, RuntimeError):
            raise
        except Exception as error:
            raise RuntimeError("Failed to run ByteTrack inference.") from error

    @staticmethod
    def _extract_candidates(results: Sequence[_Result]) -> list[TrackingCandidate]:
        """Ultralytics 결과의 병렬 텐서를 단순 스칼라 후보로 변환한다."""
        candidates: list[TrackingCandidate] = []
        for result in results:
            boxes = result.boxes
            if boxes is None or boxes.id is None:
                continue
            coordinates = boxes.xyxy.tolist()
            confidences = boxes.conf.tolist()
            class_ids = boxes.cls.tolist()
            track_ids = boxes.id.tolist()
            if not (len(coordinates) == len(confidences) == len(class_ids) == len(track_ids)):
                raise RuntimeError("ByteTrack returned inconsistent result lengths.")
            for coords, confidence, class_id, track_id in zip(
                coordinates,
                confidences,
                class_ids,
                track_ids,
                strict=True,
            ):
                if not isinstance(coords, list) or len(coords) < 4:
                    raise RuntimeError("ByteTrack returned invalid coordinates.")
                candidates.append(
                    TrackingCandidate(
                        track_id=int(cast(float, track_id)),
                        class_id=int(cast(float, class_id)),
                        confidence=float(cast(float, confidence)),
                        x1=float(cast(float, coords[0])),
                        y1=float(cast(float, coords[1])),
                        x2=float(cast(float, coords[2])),
                        y2=float(cast(float, coords[3])),
                    )
                )
        return candidates
