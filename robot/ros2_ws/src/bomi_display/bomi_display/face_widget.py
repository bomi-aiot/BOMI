"""PySide6로 BOMI 얼굴과 상태 애니메이션을 그린다."""

import math

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from bomi_display.state import DisplaySnapshot, FaceState


class FaceWidget(QWidget):
    """LCD 크기에 맞춰 눈, 입, 상태 문구를 직접 그리는 위젯."""

    COLORS = {
        FaceState.IDLE: QColor("#63E6BE"),
        FaceState.DRIVING: QColor("#74C0FC"),
        FaceState.LISTENING: QColor("#B197FC"),
        FaceState.THINKING: QColor("#F783AC"),
        FaceState.SPEAKING: QColor("#FFD43B"),
        FaceState.ERROR: QColor("#FF6B6B"),
    }

    def __init__(self) -> None:
        """기본 표정과 약 30 FPS 애니메이션 타이머를 준비한다."""
        super().__init__()
        self.snapshot = DisplaySnapshot(FaceState.IDLE, "기다리고 있어요")
        self.phase = 0.0
        self.setMinimumSize(480, 320)
        self.setCursor(Qt.BlankCursor)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(33)

    def set_snapshot(self, snapshot: DisplaySnapshot) -> None:
        """표시할 상태를 바꾸고 즉시 다시 그린다."""
        self.snapshot = snapshot
        self.update()

    def _animate(self) -> None:
        """애니메이션 위상을 진행시킨다."""
        self.phase = (self.phase + 0.08) % (2.0 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:
        """현재 상태에 맞는 얼굴을 화면 중앙에 그린다."""
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#08111F"))
        color = self.COLORS[self.snapshot.state]
        center_x = self.width() / 2
        eye_y = self.height() * 0.35
        bounce = math.sin(self.phase) * 4 if self.snapshot.state == FaceState.DRIVING else 0
        self._draw_eyes(painter, center_x, eye_y + bounce, color)
        self._draw_mouth(painter, center_x, self.height() * 0.58 + bounce, color)
        self._draw_text(painter, color)

    def _draw_eyes(self, painter: QPainter, center_x: float, y: float, color: QColor) -> None:
        """상태에 따라 열린 눈, 웃는 눈 또는 오류 눈을 그린다."""
        painter.setPen(QPen(color, 12, Qt.SolidLine, Qt.RoundCap))
        gap = min(self.width() * 0.18, 150)
        if self.snapshot.state == FaceState.ERROR:
            for x in (center_x - gap, center_x + gap):
                painter.drawLine(int(x - 24), int(y - 24), int(x + 24), int(y + 24))
                painter.drawLine(int(x + 24), int(y - 24), int(x - 24), int(y + 24))
            return
        blink = self.snapshot.state == FaceState.IDLE and math.sin(self.phase * 0.35) > 0.985
        height = 3 if blink else 55
        for x in (center_x - gap, center_x + gap):
            painter.drawRoundedRect(int(x - 22), int(y - height / 2), 44, height, 20, 20)

    def _draw_mouth(self, painter: QPainter, x: float, y: float, color: QColor) -> None:
        """발화 파형과 나머지 상태의 입 모양을 그린다."""
        painter.setPen(QPen(color, 10, Qt.SolidLine, Qt.RoundCap))
        if self.snapshot.state == FaceState.SPEAKING:
            for index in range(-2, 3):
                height = 18 + abs(math.sin(self.phase + index)) * 45
                px = x + index * 28
                painter.drawLine(int(px), int(y - height / 2), int(px), int(y + height / 2))
        elif self.snapshot.state == FaceState.LISTENING:
            radius = 24 + int((math.sin(self.phase) + 1) * 8)
            painter.drawEllipse(int(x - radius), int(y - radius), radius * 2, radius * 2)
        elif self.snapshot.state == FaceState.THINKING:
            for index, radius in enumerate((8, 12, 16)):
                px = x - 38 + index * 38
                offset = math.sin(self.phase + index * 0.8) * 8
                painter.drawEllipse(
                    int(px - radius), int(y + offset - radius), radius * 2, radius * 2
                )
        elif self.snapshot.state == FaceState.ERROR:
            painter.drawArc(int(x - 55), int(y), 110, 55, 0, 180 * 16)
        else:
            painter.drawArc(int(x - 55), int(y - 35), 110, 70, 180 * 16, 180 * 16)

    def _draw_text(self, painter: QPainter, color: QColor) -> None:
        """화면 아래에 상태 제목과 오류 상세를 표시한다."""
        painter.setPen(color)
        painter.setFont(QFont("Sans Serif", max(18, self.height() // 22), QFont.Bold))
        painter.drawText(0, int(self.height() * 0.74), self.width(), 50, Qt.AlignCenter, self.snapshot.title)
        if self.snapshot.detail:
            painter.setPen(QColor("#D0D7E2"))
            painter.setFont(QFont("Sans Serif", max(12, self.height() // 34)))
            painter.drawText(0, int(self.height() * 0.84), self.width(), 40, Qt.AlignCenter, self.snapshot.detail)
