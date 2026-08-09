"""LCD 화면 — 상태 문구와 진행 표시만 그린다.

표정(눈·입)을 쓰지 않는 이유
    작은 LCD 에서는 표정보다 글자가 훨씬 빨리 읽힌다. 시연에서 사람이 알고
    싶은 것은 "로봇이 지금 무엇을 하는가" 한 가지이고, 그 답은 문장이 가장
    정확하다.

진행 표시를 함께 두는 이유
    듣는 중·생각하는 중·이동 중은 '끝을 기다리는' 상태다. 글자만 있으면
    멈춘 것인지 진행 중인지 구분되지 않는다(2026-08-09 실기에서 실제로
    "로봇이 멈춘 것 같다"는 오해가 있었다). 움직이는 점이 그 구분을 만든다.
"""

import math

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from bomi_display.state import DisplaySnapshot, FaceState


class FaceWidget(QWidget):
    """상태 문구와 진행 표시를 LCD 크기에 맞춰 그린다."""

    COLORS = {
        FaceState.IDLE: QColor("#63E6BE"),
        FaceState.DRIVING: QColor("#74C0FC"),
        FaceState.FOLLOWING: QColor("#4DABF7"),
        FaceState.LISTENING: QColor("#B197FC"),
        FaceState.THINKING: QColor("#F783AC"),
        FaceState.SPEAKING: QColor("#FFD43B"),
        FaceState.ERROR: QColor("#FF6B6B"),
    }

    # 끝을 기다리는 상태들. 여기에만 진행 표시를 붙인다. 대기·오류는 기다리는
    # 상태가 아니므로 붙이면 오히려 "무언가 돌고 있다"는 잘못된 인상을 준다.
    PROGRESS_STATES = frozenset({
        FaceState.LISTENING,
        FaceState.THINKING,
        FaceState.SPEAKING,
        FaceState.DRIVING,
        FaceState.FOLLOWING,
    })

    def __init__(self) -> None:
        """기본 문구와 약 30 FPS 애니메이션 타이머를 준비한다."""
        super().__init__()
        self.snapshot = DisplaySnapshot(FaceState.IDLE, "기다리고 있어요")
        self.phase = 0.0
        self.setMinimumSize(480, 320)
        self.setCursor(Qt.BlankCursor)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(33)

    def set_snapshot(self, snapshot: DisplaySnapshot) -> None:
        """표시할 상태를 갈아끼운다."""
        self.snapshot = snapshot
        self.update()

    def _animate(self) -> None:
        self.phase += 0.12
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#08111F"))
        color = self.COLORS[self.snapshot.state]

        self._draw_title(painter, color)
        self._draw_detail(painter)
        if self.snapshot.state in self.PROGRESS_STATES:
            self._draw_progress(painter, color)

    def _draw_title(self, painter: QPainter, color: QColor) -> None:
        """상태 문구. 화면에서 가장 큰 요소다."""
        painter.setPen(color)
        font = QFont()
        # 화면 높이에 맞춰 키운다. LCD 해상도가 바뀌어도 비율이 유지된다.
        font.setPixelSize(max(28, int(self.height() * 0.20)))
        font.setBold(True)
        painter.setFont(font)
        area = self.rect().adjusted(0, 0, 0, -int(self.height() * 0.22))
        painter.drawText(area, Qt.AlignCenter, self.snapshot.title)

    def _draw_detail(self, painter: QPainter) -> None:
        """부가 설명(오류 사유 등). 없으면 그리지 않는다."""
        if not self.snapshot.detail:
            return
        painter.setPen(QColor("#9AA7B8"))
        font = QFont()
        font.setPixelSize(max(14, int(self.height() * 0.07)))
        painter.setFont(font)
        area = self.rect().adjusted(0, int(self.height() * 0.30), 0, -int(self.height() * 0.10))
        painter.drawText(area, Qt.AlignHCenter | Qt.AlignBottom, self.snapshot.detail)

    def _draw_progress(self, painter: QPainter, color: QColor) -> None:
        """점 다섯 개가 차례로 밝아지는 진행 표시.

        점을 쓰는 이유: 진행률을 모르는 상태들이라 막대(0~100%)로 표현할 수
        없다. 남은 시간을 약속하지 않으면서 '돌고 있음'만 보여준다.
        """
        count = 5
        gap = max(18, int(self.width() * 0.045))
        radius = max(5, int(self.height() * 0.022))
        y = int(self.height() * 0.80)
        start_x = self.width() / 2 - (count - 1) * gap / 2

        for index in range(count):
            # 위상을 점마다 어긋나게 줘서 물결처럼 흐르게 한다.
            wave = math.sin(self.phase * 2.2 - index * 0.8)
            alpha = int(70 + (wave + 1) * 92)          # 70~254
            size = radius + int((wave + 1) * radius * 0.45)
            dot = QColor(color)
            dot.setAlpha(max(0, min(255, alpha)))
            painter.setPen(QPen(dot, 0))
            painter.setBrush(dot)
            cx = int(start_x + index * gap)
            painter.drawEllipse(cx - size, y - size, size * 2, size * 2)
