"""시연 영상용 지정 대본 응답기 (demo/video-scripted-dialogue 브랜치 전용).

왜 존재하는가
    발표 영상은 "지연 없는 대화"를 보여주는 것이 목적이다. LLM 왕복과 문맥
    조회가 만드는 턴당 수 초의 지연을 없애기 위해, 이 브랜치에서는 반응형
    턴의 판단·생성(그래프)을 통째로 우회하고 미리 구성한 답변을 TTS 로 읽는다.
    웨이크워드·현관 치어·이동·MQTT 계약 등 나머지 배선은 실제 코드 그대로다.

무엇이 아닌가
    감독관이 참관하는 시연 테스트는 기존 코드(그래프 경로)로 한다. 이 모듈은
    영상 촬영 환경에서 `SCRIPTED_DIALOGUE_ENABLED=true` 일 때만 켜지며,
    main/hotfix 라인으로 환류하지 않는다.

답변 충실성 (2026-08-12 로직 검증표 기준)
    각 답변은 "실제 그래프가 낼 수 있는 답변"에 맞춰 작성했다.
    - 응급은 실제 안전 절차(graph/triage.py)와 같은 2단이다: 고정 확인 질문
      -> (명확한 부정 외 전부) 에스컬레이션. 문구도 triage 의 상수와 같다.
    - "근처" 장소 검색은 실제 로직(llm/medical_flow.py)이 상대 위치어를 쓰지
      못해 지역을 되묻는다. 대본도 같은 2단(재질의 -> 결과)이다.
    - 복약 답변은 실제 로직이 "오늘 완료된 알림 슬롯의 시각"만 알 수 있는
      한계에 맞춰(graph/context.py `_medication_reported_times`) 시각만 말한다.
    `[촬영 전 교체]` 로 표시된 값(복용 시각, 병원 이름, 회상 기억)은 시연
    계정의 실제 값으로 바꾼 뒤 촬영한다.

환경 변수
    SCRIPTED_DIALOGUE_ENABLED  대본 모드 스위치. 기본 false — 켜지 않으면
                               이 모듈은 아무 데도 관여하지 않는다.
    SCRIPTED_IDLE_TIMEOUT_SEC  대본 모드에서만 쓰는 무응답 종료 초.
                               미설정이면 policy.CONVERSATION_IDLE_TIMEOUT_SEC.
                               "3초 무응답 -> 조용히 종료" 장면은 3 으로 촬영.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScriptEntry:
    """대본 한 항목. keywords 가 비어 있으면 체인(force_next)으로만 도달한다."""

    id: str
    response: str
    # 공백 제거한 발화에 대한 부분일치 검사어. 검사어 자체도 공백 없이 쓴다.
    keywords: tuple[str, ...] = ()
    # 이 답변 뒤의 다음 발화에서 '먼저' 검사할 항목들 — 일상대화 맥락 잇기용.
    next_ids: tuple[str, ...] = ()
    # 다음 발화를 내용과 무관하게 이 항목으로 보낸다 — 응급 에스컬레이션처럼
    # "어떤 대답이든 정해진 다음 문장"이 실제 로직인 경우에 쓴다.
    force_next: str | None = None
    # True 면 전역 매칭에서 제외하고 next_ids 로만 도달한다. "분"처럼 짧아서
    # 전역으로 풀면 오탐하는 검사어를 체인 안에 가두는 장치다.
    chain_only: bool = False


_STORY_SALT_MILL = (
    "네, 옛날이야기 하나 들려드릴게요. 옛날에 무엇이든 나오는 신기한 맷돌이 있었어요. "
    "욕심 많은 사람이 그 맷돌을 훔쳐서 배에 싣고 도망가다가, 소금 나와라, 하고 외쳤대요. "
    "그런데 멈추는 말을 몰라서 배가 소금으로 가득 차 그만 가라앉고 말았죠. "
    "그래서 지금도 바닷물이 짜다고 한답니다. 재미있으셨어요?"
)

# 대본. 나열 순서가 곧 전역 매칭 우선순위다 — 응급이 항상 맨 앞이어야
# "가슴이 답답하고 허리도 아파" 같은 발화가 통증 잡담으로 새지 않는다.
SCRIPT: tuple[ScriptEntry, ...] = (
    ScriptEntry(
        id="emergency_confirm",
        keywords=("숨이안", "숨을못", "숨쉬기가", "숨쉬기힘", "가슴이답답",
                  "가슴이너무답답", "가슴이꽉"),
        # graph/triage.py _CONFIRM_QUESTION 과 동일 문구.
        response="많이 불편하세요? 가족분께 연락드릴까요?",
        force_next="emergency_escalate",
    ),
    ScriptEntry(
        id="emergency_escalate",
        # triage._RESPONSES["emergency"] 와 동일. 실제 규칙이 "명확한 부정 외
        # 전부 에스컬레이션"이므로 촬영 대본에서도 어떤 대답이든 이 문장이 나간다.
        response="제가 가족분께 연락드릴게요. 잠깐만 이대로 계세요.",
    ),
    ScriptEntry(
        id="memory_forget",
        keywords=("기억하지마", "기억하지말", "잊어버려", "잊어줘", "말안한걸로",
                  "비밀이야", "비밀인데"),
        response=("네, 알겠어요. 지금 나눈 이야기는 저만 듣고, 따로 기억해 두지 "
                  "않을게요. 편하게 말씀하세요."),
    ),
    ScriptEntry(
        id="clinic_ask_region",
        keywords=("정형외과", "병원찾아", "병원좀찾아", "병원어디"),
        # 실제 로직은 "근처/여기"를 위치로 쓰지 못해 지역을 되묻는다(2단).
        response="어느 지역에 계신지 말씀해 주시면 가까운 정형외과를 찾아드릴게요.",
        force_next="clinic_result",
    ),
    ScriptEntry(
        id="clinic_result",
        # [촬영 전 교체] 병원 이름·동네·거리: 시연 지역 hospital 테이블의 실제 행으로.
        response=("네, 찾아봤어요. 진평동에는 튼튼정형외과의원이 있어요. 걸어서 "
                  "십 분 정도 거리예요. 필요하시면 보호자분께도 알려드릴게요."),
    ),
    ScriptEntry(
        id="medication_recall",
        keywords=("약먹었", "약을먹었", "약안먹", "약먹는걸", "복약"),
        # 실제 로직은 오늘 완료된 알림 슬롯의 '시각'만 안다(약 종류는 모른다).
        # [촬영 전 교체] 시각: 촬영일에 시드한 복약 슬롯 시각으로.
        response=("오늘 아침 여덟 시 반쯤에 약 드셨다고 저한테 말씀해 주셨어요. "
                  "그러니 걱정 안 하셔도 돼요."),
    ),
    ScriptEntry(
        id="appointment",
        keywords=("예약", "일정잡아", "일정등록", "스케줄"),
        response=("네, 내일 오후 한 시 병원 예약이요. 제가 일정에 등록해 둘게요. "
                  "시간이 가까워지면 미리 알려드릴게요."),
    ),
    ScriptEntry(
        id="reminiscence",
        keywords=("젊었을때", "젊을때", "옛날에", "예전에", "그시절", "고향"),
        # [촬영 전 교체] 기억 소재: 시연 어르신 계정의 memory 내용으로.
        response=("젊었을 때 시장에서 과일 가게 하셨다고 하셨죠? 새벽마다 장 보러 "
                  "다니셨다는 이야기, 저는 들을 때마다 참 좋아요. 그때 이야기 더 "
                  "들려주세요."),
    ),
    ScriptEntry(
        id="chronic_pain",
        keywords=("허리", "무릎", "어깨"),
        response=("허리가 많이 아프시군요. 갑자기 움직이지 마시고, 편한 자세로 "
                  "잠깐 쉬어 보세요. 계속 아프시면 꼭 다시 말씀해 주세요."),
    ),
    ScriptEntry(
        id="story",
        keywords=("재미있는이야기", "재밌는이야기", "이야기해줘", "이야기하나",
                  "옛날이야기", "심심"),
        response=_STORY_SALT_MILL,
    ),
    ScriptEntry(
        id="walk",
        keywords=("산책", "공원"),
        response=("공원 산책 다녀오셨어요? 요즘 날씨에 걷기 참 좋죠. 오늘은 "
                  "얼마나 걸으셨어요?"),
        next_ids=("walk_duration",),
    ),
    ScriptEntry(
        id="walk_duration",
        keywords=("분", "시간", "한바퀴", "조금", "많이"),
        response=("와, 그 정도면 아주 잘 걸으신 거예요. 다녀오셨으니 물 한 잔 "
                  "드시고 편하게 쉬세요. 다리는 안 아프세요?"),
        next_ids=("walk_condition",),
        chain_only=True,
    ),
    ScriptEntry(
        id="walk_condition",
        keywords=("괜찮", "안아파", "멀쩡", "좋아"),
        response=("다행이에요. 이렇게 꾸준히 걸으시는 게 제일 좋은 보약이래요. "
                  "내일도 같이 날씨 보고 산책 이야기해요."),
        chain_only=True,
    ),
    ScriptEntry(
        id="farewell",
        keywords=("알겠어", "고마워", "고맙다", "그만", "됐어", "잘자", "쉴게"),
        response=("네, 오늘도 이야기 나눠 주셔서 고마워요. 필요하실 때 언제든지 "
                  "보미야, 하고 불러 주세요."),
    ),
)

# 아무 항목에도 걸리지 않은 발화의 응답. STT 오인식으로 촬영이 끊기지 않게
# "대화를 이어가는" 중립 문장으로 둔다.
FALLBACK_RESPONSE = "네, 그러셨군요. 말씀 더 편하게 해 주세요. 제가 듣고 있을게요."

# 루프의 is_farewell 은 걸렸는데(예: "여기까지 하자") 대본 farewell 항목에는
# 안 걸린 발화의 마무리 응답.
FAREWELL_FALLBACK_RESPONSE = (
    "네, 편히 쉬세요. 필요하실 때 언제든지 보미야, 하고 불러 주세요."
)


def _normalize(text: str) -> str:
    return "".join(text.split())


class ScriptedResponder:
    """발화 -> 대본 답변. 한 세션 안의 체인 상태(force/next)만 들고 있다."""

    def __init__(
        self,
        entries: tuple[ScriptEntry, ...] = SCRIPT,
        *,
        fallback: str = FALLBACK_RESPONSE,
        farewell_fallback: str = FAREWELL_FALLBACK_RESPONSE,
        idle_timeout_sec: float | None = None,
    ) -> None:
        self._entries = entries
        self._by_id = {entry.id: entry for entry in entries}
        self._fallback = fallback
        self._farewell_fallback = farewell_fallback
        # None 이면 호출부가 policy.CONVERSATION_IDLE_TIMEOUT_SEC 를 그대로 쓴다.
        self.idle_timeout_sec = idle_timeout_sec
        self._forced_id: str | None = None
        self._next_ids: tuple[str, ...] = ()
        self._audio_cache: dict[str, bytes] = {}

    def reset(self) -> None:
        """세션 시작 시 체인 상태를 비운다. 캐시(합성 오디오)는 유지한다."""
        self._forced_id = None
        self._next_ids = ()

    def respond(self, text: str, *, farewell: bool = False) -> str:
        normalized = _normalize(text)
        entry = self._match(normalized)
        if entry is None:
            self._forced_id = None
            self._next_ids = ()
            return self._farewell_fallback if farewell else self._fallback
        self._forced_id = entry.force_next
        self._next_ids = entry.next_ids
        return entry.response

    def _match(self, normalized: str) -> ScriptEntry | None:
        if self._forced_id is not None:
            forced = self._by_id.get(self._forced_id)
            if forced is not None:
                return forced
        # 직전 답변이 지목한 후속 항목을 먼저 — 일상대화 맥락이 이어져 보이는 이유.
        for next_id in self._next_ids:
            candidate = self._by_id.get(next_id)
            if candidate is not None and _hit(candidate, normalized):
                return candidate
        for candidate in self._entries:
            if candidate.chain_only:
                continue
            if _hit(candidate, normalized):
                return candidate
        return None

    # ── TTS 사전 합성 ────────────────────────────────────────────────────
    # 대본 모드의 존재 이유가 지연 제거라서, 답변마다 Typecast 왕복이 남으면
    # 반쪽이다. 기동 시 전부 합성해 두고 재생은 캐시에서 바로 꺼낸다.

    def all_responses(self) -> list[str]:
        seen: dict[str, None] = {}
        for entry in self._entries:
            seen.setdefault(entry.response)
        seen.setdefault(self._fallback)
        seen.setdefault(self._farewell_fallback)
        return list(seen)

    def audio_for(self, tts: Any, text: str) -> bytes:
        audio = self._audio_cache.get(text)
        if audio is None:
            audio = tts.synthesize(text)
            self._audio_cache[text] = audio
        return audio

    def warm(self, tts: Any) -> int:
        """모든 대본 답변을 미리 합성한다. 실패 항목은 재생 시점에 재시도한다."""
        warmed = 0
        for text in self.all_responses():
            try:
                self.audio_for(tts, text)
                warmed += 1
            except Exception:  # noqa: BLE001 - 사전 합성 실패가 기동을 막으면 안 된다
                logger.warning("could not pre-synthesize a scripted response",
                               exc_info=True)
        return warmed


def _hit(entry: ScriptEntry, normalized: str) -> bool:
    return any(keyword in normalized for keyword in entry.keywords)


def build_scripted_responder() -> ScriptedResponder | None:
    """env 스위치가 켜져 있을 때만 응답기를 만든다. 꺼져 있으면 None."""
    enabled = os.environ.get("SCRIPTED_DIALOGUE_ENABLED", "false").lower()
    if enabled not in ("1", "true", "yes"):
        return None
    idle_raw = os.environ.get("SCRIPTED_IDLE_TIMEOUT_SEC", "").strip()
    idle_timeout: float | None = None
    if idle_raw:
        try:
            idle_timeout = float(idle_raw)
        except ValueError:
            logger.warning("ignoring invalid SCRIPTED_IDLE_TIMEOUT_SEC=%r", idle_raw)
    return ScriptedResponder(idle_timeout_sec=idle_timeout)
