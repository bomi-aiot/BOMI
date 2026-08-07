"""문장 단위 비블로킹 재생과 취소 — 시스템에서 동기화 버그가 가장 나기 쉬운 곳.

왜 문장을 하나씩 넣는가
    세 가지를 동시에 얻는다.
      1. barge-in 복구. 어디까지 말했는지 알아야 나머지를 정확히 재큐할 수 있다.
         전체를 한 덩어리로 TTS 에 넘기면 끊긴 지점을 알 방법이 없다.
      2. 지연 은닉. 첫 문장부터 말하기 시작하면 나머지 합성 시간이 가려진다.
      3. 안전한 중단 지점. 문장 경계는 잘려도 되지만 문장 중간은 아니다
         ("약 두 알 드시고, 인슐린은—").

진행 상황의 권위는 여기다  ★ 반드시 읽을 것
    speaking 과 spoken_prefix 는 주인이 둘이다. 이 재생 스레드와, checkpoint 된
    ConvState. 둘이 어긋나면 로봇은 이미 말한 문장을 다시 말하거나, 말하지 않은
    문장을 말한 것으로 친다.

    그래서 경계를 이렇게 고정한다.
        재생 핸들(SpeechPlayback) = 진행 상황의 '권위'
        ConvState                 = 그 순간의 '스냅샷'

    barge-in 이 나면 note_interaction 은 state 가 아니라 핸들에게 물어본다.
    state 는 그래프 실행 시점에 찍힌 값이라 이미 낡았을 수 있기 때문이다.

참고
    CLAUDE.md §13 (barge-in), §14 (발화 규칙), §22 3단계
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence

from bomi_ai_chat.audio.echo_guard import EchoGuard

logger = logging.getLogger(__name__)


class SpeechPlayback:
    """재생 중인 한 발화의 핸들. 진행 상황의 권위를 갖는다.

    무엇을 하는가
        문장 목록을 순서대로 합성·재생하고, 몇 문장까지 실제로 말했는지 센다.
        cancel() 이 불리면 현재 문장을 끝으로 멈춘다.

    왜 '현재 문장을 끝으로' 인가
        재생 중인 오디오를 프레임 단위로 자르는 것은 백엔드마다 다르고 딸깍 소리가
        난다. 문장 경계에서 멈추는 편이 단순하고, response_shaper 가 이미 문장을
        짧게 만들어 두었으므로 지연도 크지 않다. 실기에서 이 지연이 거슬리면
        그때 프레임 단위 중단을 검토한다(실기 확인 항목).
    """

    def __init__(
        self,
        sentences: Sequence[str],
        synthesize: Callable[[str], bytes],
        play: Callable[[bytes], None],
        echo_guard: EchoGuard | None = None,
    ):
        self._sentences = list(sentences)
        self._synthesize = synthesize
        self._play = play
        self._echo_guard = echo_guard

        self._lock = threading.Lock()
        self._spoken_count = 0
        self._cancelled = False
        self._finished = threading.Event()
        self._thread = threading.Thread(target=self._run, name="tts-playback", daemon=True)

    def start(self) -> SpeechPlayback:
        """재생을 시작하고 즉시 반환한다.

        블로킹하면 안 되는 이유가 두 개다. 말하는 동안 어르신의 끼어들기를 아무도
        관찰하지 못하게 되고, 그래프 실행이 발화 길이만큼 열려 있어서 이후의 모든
        타임스탬프가 왜곡된다 (CLAUDE.md §13).
        """
        if self._echo_guard is not None:
            # 스레드를 띄우기 '전에' 표시한다. 첫 문장이 스피커로 나가기 시작하는
            # 순간부터 가드가 걸려 있어야 한다.
            self._echo_guard.mark_playback_started()
        self._thread.start()
        return self

    def _run(self) -> None:
        try:
            for sentence in self._sentences:
                with self._lock:
                    if self._cancelled:
                        break
                try:
                    audio = self._synthesize(sentence)
                    self._play(audio)
                except Exception:  # noqa: BLE001 - 한 문장 실패가 전체를 죽이지 않는다
                    logger.warning("sentence playback failed; stopping", exc_info=True)
                    break
                with self._lock:
                    # 실제로 말한 뒤에 센다. 합성이 실패한 문장을 '말했다'고 세면
                    # 재큐에서 그 문장이 조용히 사라진다.
                    self._spoken_count += 1
        finally:
            if self._echo_guard is not None:
                self._echo_guard.mark_playback_stopped()
            self._finished.set()

    def cancel(self) -> None:
        """양보한다. 현재 문장을 끝으로 멈춘다.

        누가 호출하는가
            ingress.note_interaction, 진짜 끼어들기로 판정했을 때.
        """
        with self._lock:
            self._cancelled = True

    @property
    def spoken_count(self) -> int:
        """지금까지 실제로 말한 문장 수. 이 값이 권위다."""
        with self._lock:
            return self._spoken_count

    @property
    def spoken_prefix(self) -> str:
        """지금까지 말한 부분의 텍스트."""
        with self._lock:
            return " ".join(self._sentences[: self._spoken_count])

    def remaining_sentences(self) -> list[str]:
        """아직 말하지 못한 문장들.

        이것이 barge-in 복구의 재료다. 원래 우선순위로 다시 제안되어, 어르신의
        턴이 처리된 뒤 이어서 나간다.
        """
        with self._lock:
            return self._sentences[self._spoken_count :]

    @property
    def is_done(self) -> bool:
        return self._finished.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        """재생이 끝날 때까지 기다린다. 테스트 전용.

        운영 코드에서 이걸 부르면 안 된다. 부르는 순간 비블로킹의 의미가 사라지고
        barge-in 이 불가능해진다.
        """
        return self._finished.wait(timeout)


class SentencePlayer:
    """emit 이 쓰는 재생기. 문장 목록을 받아 SpeechPlayback 을 만든다.

    누가 호출하는가
        graph.output.emit. set_player() 로 주입된다.

    무엇을 호출하는가
        TTS 합성 함수와 오디오 출력 함수. 둘 다 주입받는다 — 기존 tts/client.py 와
        audio_io/ 를 재구현하지 않기 위해서다.
    """

    def __init__(
        self,
        synthesize: Callable[[str], bytes],
        play: Callable[[bytes], None],
        echo_guard: EchoGuard | None = None,
    ):
        self._synthesize = synthesize
        self._play = play
        self._echo_guard = echo_guard

    def speak_async(self, sentences: Sequence[str]) -> SpeechPlayback:
        """재생을 시작하고 핸들을 돌려준다. 블로킹하지 않는다."""
        return SpeechPlayback(
            sentences, self._synthesize, self._play, self._echo_guard
        ).start()
