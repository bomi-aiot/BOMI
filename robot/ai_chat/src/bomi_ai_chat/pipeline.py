"""STT -> LLM/API -> TTS 대화 파이프라인."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from bomi_ai_chat import policy
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
# "보미야" 로 대화가 시작될 때 녹음 전에 먼저 말하는 호출 응답. 사용자에게 '지금
# 들을 준비가 됐다'는 신호를 주고, 잘못 깨웠을 때도 바로 알아챌 수 있게 한다.
WAKE_ACK_MESSAGE = "저를 부르셨나요?"
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

    def run_once(
        self, *, onset_timeout_seconds: float | None = None
    ) -> ConversationResult:
        """빔을 대화 턴 동안 고정한 채 한 번의 대화를 처리한다.

        빔 고정은 대화가 시작될 때만 걸리고, 정상/오류 어느 쪽으로 끝나든
        finally에서 반드시 해제된다. beam이 없으면(노트북 개발 등) 건너뛴다.

        onset_timeout_seconds
            값을 주면 '단일 리슨' 모드: 발화 시작을 이 시간(초)까지 기다린다. 그 안에
            아무 말도 없으면 로봇은 아무 말도 하지 않고 '무응답'으로 조용히 반환한다
            (failure_stages=("no_speech",)). 대화 세션의 '무응답 15초 종료'가 이걸 쓴다.
            None 이면 예전처럼 첫 순간부터 녹음한다.
        """
        if self.beam is not None:
            self.beam.apply_fixed_beam()
        try:
            return self._run_once_inner(
                onset_timeout_seconds=onset_timeout_seconds
            )
        finally:
            if self.beam is not None:
                self.beam.reset()

    def _run_once_inner(
        self, *, onset_timeout_seconds: float | None = None
    ) -> ConversationResult:
        """한 번의 대화를 처리하고 실패 단계와 보존된 텍스트를 반환한다."""

        started_at = self._monotonic()
        user_text: str | None = None

        try:
            audio = self.audio_in.capture(
                onset_timeout_seconds=onset_timeout_seconds
            )
        except Exception:
            return self._failed_stage(
                "capture",
                CAPTURE_ERROR_MESSAGE,
                started_at=started_at,
                user_text=None,
            )

        # 단일 리슨 모드에서 발화가 없으면 capture 가 빈 바이트를 준다. 이는 '오류'가
        # 아니라 '무응답'이다. 로봇은 아무 말도 하지 않고 no_speech 로 조용히 반환한다
        # (대화 세션이 이 신호를 보고 대화를 끝낸다). 이게 없으면 무응답이 capture
        # 오류로 처리되어 "음성을 듣는 중 문제가..." 를 말하게 된다.
        if isinstance(audio, bytes) and audio == b"":
            LOGGER.info("no speech detected within onset timeout")
            return self._finish(
                started_at=started_at,
                user_text="",
                response_text=None,
                audio_played=False,
                failure_stages=("no_speech",),
            )
        if not isinstance(audio, bytes) or not audio:
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
            # 발화는 감지됐으나(무응답과 다름) STT 가 알아듣지 못한 경우다. 진짜
            # '무응답'(발화 자체가 없음)은 위 no_speech 에서 이미 조용히 처리됐다.
            # 여기서는 한 번 되묻고(EMPTY_STT_MESSAGE) 대화는 계속 이어간다.
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
        """웨이크워드로 '대화'를 시작하고, 그 대화 안에서는 여러 발화를 이어서 처리한다.

        용어
            발화(utterance) = 사용자가 말하는 한 문장.
            대화(conversation) = "보미야"로 시작해 여러 발화가 오가는 하나의 의사소통.

        무엇이 바뀌었나 (S15P11E102-222)
            이전에는 '발화마다' "보미야"를 불러야 했다(대기 → 발화 1개 → 다시 대기).
            이제는 "보미야" 한 번으로 '대화'가 시작되고, 그 대화 안에서는 부르지 않아도
            발화가 계속 이어진다. 즉 웨이크워드는 '발화 단위'가 아니라 '대화 단위'다.

        대화의 끝 (임시)
            아직 종료 로직(마무리 멘트 인식 / 무응답 n분 타임아웃)이 없다. 그때까지는
            Ctrl+C 가 '대화의 끝'을 대신한다. 대화 중 Ctrl+C → 그 대화만 끝나고 다시
            "보미야" 대기로 돌아간다. '대기 중' Ctrl+C → 프로그램이 끝난다.

        웨이크워드가 없을 때 (레거시/노트북)
            self.wake 가 None 이면 대화 개념 없이 예전처럼 매 발화를 바로 처리하고,
            Ctrl+C 로 전체를 종료한다.
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
                if self.wake is not None:
                    # "보미야" 대기. 대기 중에는 빔을 고정하지 않는다(사방 어디서 불러도
                    # 듣기 위함). 여기서의 Ctrl+C 는 '프로그램 종료'를 의미한다.
                    self.wake.wait_for_wake()
                    # 웨이크가 걸리면 '대화'를 시작한다. 대화 안에서는 다시 부르지 않아도
                    # Ctrl+C 로 끝날 때까지 여러 발화를 이어서 처리한다.
                    turns = self._run_conversation(turns, max_turns)
                else:
                    # 웨이크워드 없음(레거시): 예전 동작 그대로 매 발화를 즉시 처리한다.
                    result = self.run_once()
                    turns += 1
                    if (
                        result.failure_stages
                        and (max_turns is None or turns < max_turns)
                    ):
                        self._sleep(LOOP_FAILURE_DELAY_SECONDS)
            except KeyboardInterrupt:
                # 대기 중(또는 레거시 실행 중) Ctrl+C -> 전체 종료.
                LOGGER.info(
                    "conversation loop stopped by user turns=%s",
                    turns,
                )
                break
        return turns

    def _say(self, text: str) -> None:
        """짧은 고정 안내 문구를 TTS로 말한다(STT/LLM 응답 경로와 별개).

        무엇을 하는가
            "저를 부르셨나요?" 같은 고정 문구를 합성해 재생한다. 재생은 블로킹이라
            이 함수가 끝난 뒤에 녹음이 시작된다(안내가 끝나고 나서 듣기 시작).

        왜 예외를 삼키나
            안내 문구는 대화의 곁가지다. TTS/재생이 실패해도 대화 자체를 막으면 안 되므로
            경고만 남기고 넘어간다(그다음 녹음은 그대로 진행).
        """
        print(f"[응답 텍스트] {text}")
        try:
            audio = self.tts.synthesize(text)
            self.audio_out.play(audio)
        except Exception:
            LOGGER.exception("failed to speak prompt text=%s", text)

    @staticmethod
    def _is_farewell(user_text: str) -> bool:
        """사용자 발화가 '대화를 그만하겠다'는 뜻인지 부분일치로 판단한다.

        무엇을 하는가
            발화에서 공백을 없앤 뒤, policy.CONVERSATION_FAREWELL_CUES 의 큐가 하나라도
            들어 있으면 True. "대화는 여기까지만 하자" -> "여기까지" 포함 -> True.

        왜 LLM 을 안 쓰나
            종료 판정에 생성 LLM 을 또 부르면 턴마다 왕복이 늘어 2초 예산이 무너진다
            (CLAUDE.md §16). 값싼 키워드 매칭으로 시작한다. 큐 목록은 policy 에 있다.
        """
        text = user_text.replace(" ", "")
        return any(cue in text for cue in policy.CONVERSATION_FAREWELL_CUES)

    def _run_conversation(self, turns: int, max_turns: int | None) -> int:
        """'보미야'로 시작된 하나의 대화를 여러 발화로 이어간다.

        무엇을 하는가
            대화가 끝날 때까지 run_once() 를 반복한다. 각 발화는 run_once 안에서
            빔 고정 → STT → 응답 → 빔 해제를 거친다. 대화 중에는 "보미야"를 다시
            부를 필요가 없다.

        대화를 어떻게 끝내는가 (세 가지)
            1) 무응답: 각 턴은 '단일 리슨'이다. run_once 에 onset_timeout 을 줘서 발화
               시작을 policy.CONVERSATION_IDLE_TIMEOUT_SEC 초까지 기다린다. 그 안에 아무
               말도 없으면 run_once 가 no_speech 로 조용히 반환하고(로봇 발화 없음),
               여기서 대화를 끝낸다. 예전처럼 3초 캡처를 반복하며 STT 를 헛호출하지
               않는다 — 한 번의 리슨으로 15초를 기다린다.
            2) 마무리 언급: 사용자가 그만하겠다고 말하면(_is_farewell) 끝낸다. 그 발화에
               대한 응답은 run_once 가 이미 말했으므로 여기서는 조용히 끝낸다.
            3) Ctrl+C: 수동으로 끝내는 안전장치. 여전히 유효하다.
            어느 경우든 '대화만' 끝나고 바깥 루프(run)가 다시 "보미야"를 기다린다
            (프로그램 종료가 아니다).

        무엇을 호출하는가
            run_once(onset_timeout_seconds=...), _is_farewell.

        누가 호출하는가
            run(). self.wake 가 있을 때만, 웨이크가 걸린 직후.

        반환값
            갱신된 누적 발화 수(turns). 바깥 루프가 max_turns 판정에 이어서 쓴다.

        주의사항
            - 무응답(no_speech)과 '못 알아들음'(stt_empty)은 다르다. 전자는 발화 자체가
              없어 대화를 끝내고, 후자는 발화가 있었으나 STT 가 실패한 것이라 한 번 되묻고
              대화를 이어간다(run_once 안에서 처리).
        """
        print("[대화 시작] 말씀하세요. ('보미야' 다시 부를 필요 없음)")
        # 녹음을 시작하기 '전에' 먼저 호출 응답을 말한다("저를 부르셨나요?"). 사용자에게
        # 응답 타이밍 신호가 되고, 잘못 깨웠을 때도 바로 알아챌 수 있다. 재생은 블로킹이라
        # 이 말이 끝난 뒤에 아래 run_once 의 녹음이 시작된다.
        self._say(WAKE_ACK_MESSAGE)
        try:
            while max_turns is None or turns < max_turns:
                # 단일 리슨: 발화 시작을 최대 IDLE_TIMEOUT 초 기다린다. 그 안에 아무
                # 말도 없으면 run_once 가 no_speech 로 조용히 반환한다(로봇 발화 없음).
                result = self.run_once(
                    onset_timeout_seconds=policy.CONVERSATION_IDLE_TIMEOUT_SEC
                )
                turns += 1

                # 종료 1) 무응답: 15초 안에 발화 시작이 없었다. 조용히 끝낸다.
                if "no_speech" in result.failure_stages:
                    LOGGER.info(
                        "conversation ended: no speech within %ss",
                        policy.CONVERSATION_IDLE_TIMEOUT_SEC,
                    )
                    print("[대화 종료] 무응답으로 종료. 다시 '보미야'로 부르면 새 대화.")
                    break

                # 종료 2) 마무리 언급. run_once 가 그 발화에 이미 응답했으니 조용히 끝낸다.
                if result.user_text and self._is_farewell(result.user_text):
                    LOGGER.info("conversation ended: farewell detected")
                    print("[대화 종료] 마무리 언급 감지. 다시 '보미야'로 부르면 새 대화.")
                    break

                if (
                    result.failure_stages
                    and (max_turns is None or turns < max_turns)
                ):
                    self._sleep(LOOP_FAILURE_DELAY_SECONDS)
        except KeyboardInterrupt:
            # 수동 종료(안전장치). 바깥 run() 루프가 다시 "보미야"를 기다린다.
            LOGGER.info("conversation ended by user turns=%s", turns)
            print("[대화 종료] 다시 '보미야'로 부르면 새 대화를 시작합니다.")
        return turns
