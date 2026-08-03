"""STT -> LLM/API -> TTS 대화 파이프라인."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from bomi_ai_chat.audio_io.base import AudioInput, AudioOutput
from bomi_ai_chat.config import Settings, get_settings
from bomi_ai_chat.llm.client import LLMClient
from bomi_ai_chat.llm.medical_flow import handle_medical_query
from bomi_ai_chat.stt.client import STTClient
from bomi_ai_chat.tts.client import TTSClient
from bomi_ai_chat.weather.client import CITY_GRID, WeatherClient

LOGGER = logging.getLogger(__name__)

CAPTURE_ERROR_MESSAGE = (
    "음성을 듣는 중 문제가 생겼어요. 잠시 후 다시 말씀해주세요."
)
STT_ERROR_MESSAGE = (
    "말씀을 확인하는 중 문제가 생겼어요. 잠시 후 다시 말씀해주세요."
)
EMPTY_STT_MESSAGE = "말씀을 인식하지 못했어요. 다시 한번 말씀해주세요."
WEATHER_ERROR_MESSAGE = (
    "지금 날씨 정보를 확인하기 어려워요. 잠시 후 다시 물어봐주세요."
)
RESPONSE_ERROR_MESSAGE = (
    "답변을 준비하는 중 문제가 생겼어요. 잠시 후 다시 말씀해주세요."
)
LOOP_FAILURE_DELAY_SECONDS = 1.0


def _default_medical_query_detector(text: str) -> bool:
    """무거운 임베딩 라우터를 실제 판별 시점까지 지연 로딩한다."""

    from bomi_ai_chat.llm.router import is_medical_query

    return is_medical_query(text)


@dataclass(frozen=True, slots=True)
class ConversationResult:
    """한 번의 대화 처리 결과와 복구에 필요한 관측 정보."""

    user_text: str | None
    response_text: str | None
    audio_played: bool
    failure_stages: tuple[str, ...]
    duration_seconds: float

    @property
    def succeeded(self) -> bool:
        return not self.failure_stages


class ConversationPipeline:
    """마이크 입력을 받아 응답 텍스트와 음성을 만드는 파이프라인."""

    def __init__(
        self,
        audio_in: AudioInput,
        audio_out: AudioOutput,
        settings: Settings | None = None,
        *,
        medical_query_detector: Callable[[str], bool] | None = None,
        weather_query_detector: Callable[[str], bool] | None = None,
        beam=None,
        wake=None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        settings = settings or get_settings()
        self.audio_in = audio_in
        self.audio_out = audio_out
        self.stt = STTClient(settings)
        self.llm = LLMClient(settings)
        self.tts = TTSClient(settings)
        self.weather = WeatherClient(settings)
        self._is_medical_query = (
            medical_query_detector or _default_medical_query_detector
        )
        # 날씨 의도 판정기. 기본은 가벼운 키워드 검사(테스트 격리 유지).
        # 실제 실행(main)에서는 임베딩 기반 is_weather_query를 주입한다.
        self._detect_weather = (
            weather_query_detector or (lambda text: "날씨" in text)
        )
        # 대화 턴 동안 마이크 빔을 앞쪽으로 고정하는 컨트롤러(없으면 미사용).
        self.beam = beam
        # 웨이크워드('보미야') 감지기. 있으면 매 턴 대화 시작 전에 '깨우기'를 기다린다.
        # None 이면(노트북 개발 등) 상시 청취 없이 곧바로 대화 턴을 돈다.
        self.wake = wake
        self._monotonic = monotonic
        self._sleep = sleep

    def _extract_city(self, text: str) -> str | None:
        """텍스트 안에서 지원하는 도시명을 찾는다."""

        for city in CITY_GRID:
            if city in text:
                return city
        return None

    def _finish(
        self,
        *,
        started_at: float,
        user_text: str | None,
        response_text: str | None,
        audio_played: bool,
        failure_stages: tuple[str, ...],
    ) -> ConversationResult:
        duration_seconds = max(0.0, self._monotonic() - started_at)
        result = ConversationResult(
            user_text=user_text,
            response_text=response_text,
            audio_played=audio_played,
            failure_stages=failure_stages,
            duration_seconds=duration_seconds,
        )
        LOGGER.info(
            "conversation turn finished failures=%s audio_played=%s "
            "duration_seconds=%.3f",
            ",".join(failure_stages) or "none",
            audio_played,
            duration_seconds,
        )
        return result

    def _deliver(
        self,
        response_text: str,
        *,
        started_at: float,
        user_text: str | None,
        failure_stages: tuple[str, ...] = (),
    ) -> ConversationResult:
        """텍스트를 먼저 보존한 뒤 TTS와 재생 실패를 별도로 기록한다."""

        print(f"[응답 텍스트] {response_text}")
        delivery_failures = list(failure_stages)

        try:
            audio_out = self.tts.synthesize(response_text)
        except Exception:
            LOGGER.exception("conversation stage failed stage=tts")
            delivery_failures.append("tts")
            return self._finish(
                started_at=started_at,
                user_text=user_text,
                response_text=response_text,
                audio_played=False,
                failure_stages=tuple(delivery_failures),
            )

        try:
            self.audio_out.play(audio_out)
        except Exception:
            LOGGER.exception("conversation stage failed stage=playback")
            delivery_failures.append("playback")
            return self._finish(
                started_at=started_at,
                user_text=user_text,
                response_text=response_text,
                audio_played=False,
                failure_stages=tuple(delivery_failures),
            )

        return self._finish(
            started_at=started_at,
            user_text=user_text,
            response_text=response_text,
            audio_played=True,
            failure_stages=tuple(delivery_failures),
        )

    def _failed_stage(
        self,
        stage: str,
        response_text: str,
        *,
        started_at: float,
        user_text: str | None,
    ) -> ConversationResult:
        LOGGER.exception("conversation stage failed stage=%s", stage)
        return self._deliver(
            response_text,
            started_at=started_at,
            user_text=user_text,
            failure_stages=(stage,),
        )

    @staticmethod
    def _validated_text(value: object, *, source: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{source} 결과는 비어 있지 않은 문자열이어야 합니다.")
        return value.strip()

    def run_once(self) -> ConversationResult:
        """빔을 대화 턴 동안 고정한 채 한 번의 대화를 처리한다.

        빔 고정은 대화가 시작될 때만 걸리고, 정상/오류 어느 쪽으로 끝나든
        finally에서 반드시 해제된다. beam이 없으면(노트북 개발 등) 건너뛴다.
        """

        if self.beam is not None:
            self.beam.apply_fixed_beam()
        try:
            return self._run_once_inner()
        finally:
            if self.beam is not None:
                self.beam.reset()

    def _run_once_inner(self) -> ConversationResult:
        """한 번의 대화를 처리하고 실패 단계와 보존된 텍스트를 반환한다."""

        started_at = self._monotonic()
        user_text: str | None = None

        try:
            audio = self.audio_in.capture()
            if not isinstance(audio, bytes) or not audio:
                raise ValueError(
                    "오디오 입력은 비어 있지 않은 bytes여야 합니다."
                )
        except Exception:
            return self._failed_stage(
                "capture",
                CAPTURE_ERROR_MESSAGE,
                started_at=started_at,
                user_text=None,
            )

        try:
            transcribed = self.stt.transcribe(audio)
            if not isinstance(transcribed, str):
                raise ValueError("STT 결과는 문자열이어야 합니다.")
        except Exception:
            return self._failed_stage(
                "stt",
                STT_ERROR_MESSAGE,
                started_at=started_at,
                user_text=None,
            )

        user_text = transcribed.strip()
        print(f"[STT] 인식된 텍스트: {user_text}")
        if not user_text:
            LOGGER.info("conversation input was empty after STT")
            return self._deliver(
                EMPTY_STT_MESSAGE,
                started_at=started_at,
                user_text=user_text,
                failure_stages=("stt_empty",),
            )

        try:
            medical_query = self._is_medical_query(user_text)
            if not isinstance(medical_query, bool):
                raise ValueError("의료 라우터 결과는 bool이어야 합니다.")
        except Exception:
            return self._failed_stage(
                "routing",
                RESPONSE_ERROR_MESSAGE,
                started_at=started_at,
                user_text=user_text,
            )

        if medical_query:
            try:
                response = self._validated_text(
                    handle_medical_query(user_text),
                    source="의료 응답",
                )
            except Exception:
                return self._failed_stage(
                    "medical",
                    RESPONSE_ERROR_MESSAGE,
                    started_at=started_at,
                    user_text=user_text,
                )
            print(f"[의료 API] 응답: {response}")
        else:
            weather_data = None
            if self._detect_weather(user_text):
                city = self._extract_city(user_text)
                if city:
                    try:
                        weather_data = self.weather.get_forecast(city)
                    except Exception:
                        return self._failed_stage(
                            "weather",
                            WEATHER_ERROR_MESSAGE,
                            started_at=started_at,
                            user_text=user_text,
                        )
                    print(f"[날씨] {city}: {weather_data}")

            try:
                response = self._validated_text(
                    self.llm.generate(
                        user_text,
                        weather_data=weather_data,
                    ),
                    source="LLM 응답",
                )
            except Exception:
                return self._failed_stage(
                    "llm",
                    RESPONSE_ERROR_MESSAGE,
                    started_at=started_at,
                    user_text=user_text,
                )
            print(f"[LLM] 응답: {response}")

        return self._deliver(
            response,
            started_at=started_at,
            user_text=user_text,
        )

    def run(self, *, max_turns: int | None = None) -> int:
        """Ctrl+C까지 반복 실행하고, 실패한 차례 뒤에도 다음 입력을 받는다.

        웨이크워드(self.wake)가 있으면 매 턴 run_once() '직전에' "보미야"를 기다린다.
        즉 한 턴의 흐름은: 웨이크 대기 → (감지) → run_once(빔 고정 → STT → LLM →
        TTS → 빔 해제) → 다시 웨이크 대기. 종료 조건은 아직 없다(추후 run_once 뒤에
        다회전/타임아웃을 붙일 자리다). wake 가 None 이면 대기 없이 곧바로 대화한다.
        """

        if max_turns is not None and (
            not isinstance(max_turns, int)
            or isinstance(max_turns, bool)
            or max_turns <= 0
        ):
            raise ValueError("max_turns는 0보다 큰 정수 또는 None이어야 합니다.")

        turns = 0
        LOGGER.info("conversation loop started")
        while max_turns is None or turns < max_turns:
            try:
                # 웨이크워드가 붙어 있으면 "보미야"가 들릴 때까지 여기서 대기한다.
                # 대기 중에는 빔을 고정하지 않는다(사방 어디서 불러도 듣기 위함).
                # 빔 고정은 감지 뒤 run_once() 안에서만 걸린다.
                if self.wake is not None:
                    self.wake.wait_for_wake()
                result = self.run_once()
                turns += 1
                if (
                    result.failure_stages
                    and (max_turns is None or turns < max_turns)
                ):
                    self._sleep(LOOP_FAILURE_DELAY_SECONDS)
            except KeyboardInterrupt:
                LOGGER.info(
                    "conversation loop stopped by user turns=%s",
                    turns,
                )
                break
        return turns
