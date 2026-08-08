"""응답 정제와 음성 출력 — 마지막 두 노드이며, 의도된 병목이다.

어디에 위치하는가
    '모든' 경로가 여기로 수렴한다. 여덟 개 핸들러와 escalation 전부.
    response_shaper 를 거치지 않고 스피커에 도달하는 것은 없다.

왜 그 병목이 의도적인가
    출력이 음성이기 때문이다. 듣는 사람은 훑어 읽을 수 없고, 다시 읽을 수 없고,
    우리 사용자의 경우 청력이 떨어져 있을 수 있다. 사실은 완벽한 세 문단짜리 답변은
    제품으로서 실패다. 여덟 개 핸들러가 각자 그걸 기억하길 기대하는 대신,
    모두가 반드시 지나가는 한 곳에서 강제한다.

    유용한 부수 효과: 속도 조절을 위해 문장으로 쪼개면 그것이 곧 안전한 중단 지점이
    되므로 barge-in 복구가 거의 공짜로 따라온다 (CLAUDE.md §13).

읽는 값   response, terse, sentences, spoken_prefix
쓰는 값   sentences, final_utterance, speaking, spoken_prefix

pipeline.py 와의 역할 분담  ★ 205번 티켓에서 반드시 확인할 것
    pipeline.py = 입력 루프 드라이버. 오디오 캡처 -> STT -> app.invoke() 호출.
    emit()      = 재생 시작. tts/client.py 와 audio_io/ 를 호출하고 즉시 반환한다.

    pipeline 이 재생 완료를 기다리는 구조면 barge-in 이 원리적으로 불가능하다.
    말하는 중에도 계속 듣고 있어야 어르신이 끼어드는 것을 관찰할 수 있기 때문이다.
    입력 루프와 재생은 서로 독립적으로 돌아야 한다.

참고
    CLAUDE.md §14 (발화 규칙), §13 (barge-in), §16 (지연)
"""

from __future__ import annotations

import logging
import re

from bomi_ai_chat import policy
from bomi_ai_chat.state import ConvState
from bomi_ai_chat.turn_timer import current_stage

logger = logging.getLogger(__name__)

# 문장 끝 뒤에서 자른다. 종결 부호를 잘린 조각에 남기려고 lookbehind 를 쓴다.
#
# 한국어에서 ".!?" 만 보면 부족하다. 종결어미 뒤에 부호가 빠지는 경우가 흔해서
# "괜찮으세요 오늘 날씨가" 처럼 한 덩어리가 된다. 그래서 종결어미 + 공백도 경계로 본다.
_SENTENCE_END = re.compile(
    r"(?<=[.!?。！？])\s+"
    r"|(?<=[다요])\s+(?=[가-힣A-Za-z])"
)

# 소수점 보호용 자리표시자. 본문에 나올 일이 없는 제어문자를 쓴다.
_DECIMAL_MARK = "\x00"
_DECIMAL = re.compile(r"\d+\.\d+")

# 어르신 id 별 재생 핸들.
#
# 왜 state 밖에 두는가
#   취소 가능한 오디오 핸들은 살아있는 객체다. checkpointer 는 state 를 직렬화하므로
#   그런 객체를 담을 수 없다. 그 결과 재생 진행 상황의 주인이 둘이 된다.
#   이 레지스트리와, checkpoint 된 speaking / spoken_prefix. 시스템에서 동기화 버그가
#   가장 나기 쉬운 지점이다. 진행 상황의 권위는 재생 스레드에 있고 state 는 스냅샷으로
#   취급한다 (CLAUDE.md §13).
TTS_HANDLES: dict[str, object] = {}


def split_sentences(text: str) -> list[str]:
    """정제된 텍스트를 발화 크기 조각으로 나눈다.

    왜 존재하는가
        한 번에 세 가지 일을 한다.
          1. 속도 조절. 짧은 조각은 청력이 떨어진 분을 위해 천천히 말할 수 있게 한다.
          2. 지연 은닉. 나머지가 아직 생성되는 중에 1번 문장부터 말하기 시작할 수 있어서,
             약 2초 예산의 큰 몫을 되찾는다.
          3. barge-in 복구. 문장 경계는 잘려도 안전한 지점이다. 문장 중간은 아니다
             ("약 두 알 드시고, 인슐린은—").

    누가 호출하는가
        response_shaper.

    주의사항
        한국어 문장 경계는 ".!?" 만이 아니다. "요.", "다.", 인용문, 그리고 나눠서는
        안 되는 소수점 숫자를 함께 봐야 한다.
    """
    if not text or not text.strip():
        return []

    # 소수점을 먼저 가려낸다. "3.5도"를 "3." 과 "5도"로 쪼개면 로봇이 이상하게 말한다.
    # 자리표시자로 바꿔두고 분할이 끝난 뒤 되돌린다.
    guarded = _DECIMAL.sub(lambda m: m.group(0).replace(".", _DECIMAL_MARK), text)

    parts = _SENTENCE_END.split(guarded)
    return [
        part.replace(_DECIMAL_MARK, ".").strip()
        for part in parts
        if part and part.strip()
    ]


# 프롬프트가 모델에게 건네는 '뼈대' 표시들.
#
# 이것들은 모델이 읽으라고 넣은 것이지 말하라고 넣은 것이 아니다. 그런데 입력이
# 어수선하면 모델이 그대로 베껴 출력한다 — 233 실기 점검에서 로봇이
# "[현재 정보] 오늘은 2026년 08월 05일 수요일... 어르신: 밖에 니가 오나 바로."
# 를 소리 내어 말했다. 대괄호와 내부 라벨을 읽는 로봇은 말벗이 아니라 서식이다
# (CLAUDE.md §17.9 "기계를 설명하지 않는다").
_SCAFFOLD_LABEL = re.compile(r"\[[^\]\n]{1,20}\]\s*")

# 화자 표시. 모델이 어르신의 말을 그대로 되읽는 형태다. 라벨만 떼면 어르신의 말이
# 로봇의 말로 둔갑하므로, 이 표시가 붙은 문장은 통째로 버린다.
_ECHOED_SPEAKER = re.compile(r"^(어르신|사용자)\s*[:：]")

# 모델이 자기 답변에 붙이는 접두사. 이건 내용이 뒤에 있으므로 접두사만 뗀다.
_ANSWER_PREFIX = re.compile(r"^(답변|응답)\s*[:：]\s*")

# 모델에는 상대 날짜 계산을 위해 현재 시각을 항상 제공하지만, 그 참고값을 일반
# 대화에서 먼저 읽어서는 안 된다. 프롬프트만으로는 드물게 새므로 응답 단계에서도
# 명시적인 날짜·시각 질문인지 확인해 안내 문장을 제거한다.
_TIME_QUERY = re.compile(
    r"몇\s*(?:시|분|일)|몇시|며칠|무슨\s*요일|오늘\s*날짜|현재\s*시각|지금\s*몇"
)
_CURRENT_TIME_ANSWER = re.compile(
    r"^(?:오늘은\s*)?(?:\d{4}년\s*)?\d{1,2}월\s*\d{1,2}일"
    r"|^(?:현재\s*시각|지금\s*시각)(?:은|이)?\s*\d{1,2}시"
)


def strip_prompt_scaffolding(text: str) -> str:
    """프롬프트 뼈대가 음성으로 새어 나가는 것을 결정적으로 막는다.

    무엇을 하는가
        세 가지를 순서대로 처리한다.
          1. `[현재 정보]` 같은 대괄호 라벨은 '떼기만' 한다. 그 뒤 문장은 대개
             진짜 내용이라("오늘은 ... 수요일입니다") 통째로 버리면 답을 잃는다.
          2. `어르신:` / `사용자:` 로 시작하는 문장은 '버린다'. 어르신의 말을
             되읽은 것이므로 라벨만 떼면 그 말이 로봇의 말이 된다.
          3. `답변:` 접두사는 뗀다. 뒤에 진짜 답이 있다.

    왜 프롬프트가 아니라 여기서도 막는가
        프롬프트는 확률적이다. 같은 지시를 넣어도 입력이 어수선하면 다시 샌다.
        §17.9 는 취향이 아니라 검증 대상 항목이므로, 확률에 맡기지 않고 결정적인
        보증을 하나 둔다. 프롬프트 쪽 금지 문구도 함께 넣었다(llm/client.py) —
        이 함수는 그것이 실패했을 때의 안전망이다.

    누가 호출하는가
        response_shaper. 모든 출력 경로가 그곳을 지나므로 여기 한 곳이면 된다.

    인자
        text: 핸들러가 만든 응답 원문.

    반환값
        말해도 되는 텍스트. 전부 버려졌으면 빈 문자열.

    주의사항
        - 라벨 폭을 20자로 제한한다. 어르신이 실제로 대괄호를 쓸 일은 없지만,
          제한이 없으면 긴 문장을 통째로 삼킬 수 있다.
        - 이 함수가 무언가를 지웠다면 프롬프트가 제 일을 못 한 것이다.
          호출부가 그 사실을 로그로 남긴다.
    """
    kept: list[str] = []
    for sentence in split_sentences(text):
        cleaned = _SCAFFOLD_LABEL.sub("", sentence).strip()
        if not cleaned:
            continue
        if _ECHOED_SPEAKER.match(cleaned):
            continue
        cleaned = _ANSWER_PREFIX.sub("", cleaned).strip()
        if cleaned:
            kept.append(cleaned)
    return " ".join(kept)


def strip_unasked_current_time(text: str, user_input: str) -> str:
    """날짜·시각 질문이 아닌 턴에서 모델이 먼저 읽은 현재 정보를 제거한다."""
    if _TIME_QUERY.search(user_input or ""):
        return text
    return " ".join(
        sentence for sentence in split_sentences(text)
        if not _CURRENT_TIME_ANSWER.match(sentence.strip())
    )


def response_shaper(state: ConvState) -> dict:
    """발화 규칙을 강제하고 재생용 문장을 준비한다.

    무엇을 하는가
        핸들러가 만든 것을 '말할 수 있게' 만든다.
          - policy.MAX_SENTENCES(terse 면 MAX_SENTENCES_TERSE)로 줄인다
          - 데이터보다 행동을 앞세운다("추워요, 내복 입으세요" / "3도입니다" 아님)
          - 문장으로 쪼갠다

    왜 terse 가 있는가
        quiet hours 에 현관 인사가 통과할 때 게이트가 세팅한다. 새벽 2시 귀가에는
        낮처럼 긴 인사가 아니라 몇 마디가 맞다. 게이트가 허락이 아니라 '문구'에
        영향을 주는 유일한 경우다 (policy.QUIET_TERSE).

    누가 호출하는가
        build.py. 일곱 핸들러 전부와 escalation 에서.

    무엇을 호출하는가
        split_sentences.

    반환값
        {"sentences": [...], "final_utterance": str}

    주의사항
        - 여기서의 절단은 안전망이고, 핸들러가 길게 써도 된다는 허가가 아니다.
          어떤 핸들러가 습관적으로 다섯 문장을 만든다면 프롬프트를 고쳐야 한다.
          절단은 중요한 절반을 잘라낼 수 있다. 복약 안내에서는 특히 위험하다.
        - final_utterance 가 None 인 것은 침묵을 선택한 경우뿐이고, 그때는 이 노드에
          아예 도달하지 않는다(게이트가 END 로 보낸다).
    """
    text = state.get("response", "")
    limit = policy.MAX_SENTENCES_TERSE if state.get("terse") else policy.MAX_SENTENCES

    # 프롬프트 뼈대를 먼저 걷어낸다. 절단보다 앞에 두는 이유는, 라벨이 한 문장을
    # 통째로 차지하면 그것이 MAX_SENTENCES 자리를 잡아먹어 진짜 할 말이 잘리기
    # 때문이다.
    stripped = strip_prompt_scaffolding(text)
    if stripped != text.strip():
        # 절단 경고와 같은 이유로 조용히 넘기지 않는다. 이 로그가 쌓이면 고칠 곳은
        # 이 함수가 아니라 프롬프트다 (llm/client.py 의 SYSTEM_PROMPT).
        logger.warning(
            "prompt scaffolding leaked into the response and was stripped "
            "(intent=%s). fix the prompt, not the shaper",
            state.get("intent"))
    text = stripped

    without_unasked_time = strip_unasked_current_time(
        text, state.get("user_input", "") or "")
    if without_unasked_time != text:
        logger.warning(
            "unasked current date/time leaked into the response and was stripped "
            "(intent=%s)", state.get("intent"))
    text = without_unasked_time

    all_sentences = split_sentences(text)
    sentences = all_sentences[:limit]

    if len(all_sentences) > limit:
        # 정제는 대부분 프롬프트에서 이뤄져야 한다(CLAUDE.md §16 9단계). 여기서
        # 실제로 잘렸다는 것은 프롬프트가 제 일을 못 했다는 뜻이고, 절단은 중요한
        # 절반을 날릴 수 있다("약 두 알 드시고, 인슐린은—"). 그래서 조용히 자르지 않고
        # 남긴다. 이 로그가 쌓이면 고칠 곳은 이 함수가 아니라 프롬프트다.
        logger.warning(
            "response truncated: %d sentences -> %d (intent=%s, terse=%s). "
            "fix the prompt, not the shaper",
            len(all_sentences), limit, state.get("intent"), bool(state.get("terse")))

    return {"sentences": sentences, "final_utterance": " ".join(sentences)}


def emit(state: ConvState) -> dict:
    """말하기를 시작한다. 재생이 끝날 때까지 기다리지 '않는다'.

    무엇을 하는가
        문장 목록을 TTS 계층에 넘기고, 취소 가능한 핸들을 저장하고, 로봇을 '말하는 중'
        으로 표시한다.

    왜 블로킹하면 안 되는가
        이유가 두 개다. 첫째 barge-in: 이 노드가 재생이 끝날 때까지 블로킹하면
        어르신이 끼어드는 것을 아무도 관찰할 수 없고 양보 우선 정책이 불가능해진다.
        둘째, 그래프 실행이 발화 길이만큼 열려 있게 되어 이후의 모든 타임스탬프가
        왜곡된다.

    누가 호출하는가
        build.py. END 직전의 마지막 노드.

    무엇을 호출하는가
        논블로킹 래퍼를 통해 audio/tts (외부 API).

    반환값
        {"speaking": True, "spoken_prefix": ""}

    주의사항
        - 문장을 '하나씩' 투입한다. 전체 텍스트를 한 덩어리로 TTS 에 넘기면 barge-in
          이 어디서 끊었는지 알 수 없고, 나머지를 정확히 재큐할 수 없다.
        - state 의 spoken_prefix 는 여기서 "" 로 초기화만 한다. 진행 상황(몇 문장까지
          말했나)의 권위는 재생 핸들(SpeechPlayback.spoken_prefix)이다 — 재생 스레드는
          checkpoint 를 쓸 수 없으므로 state 쪽 값을 문장마다 갱신하는 것은 애초에
          불가능하고, 재큐가 필요할 때는 ingress._yield_playback 이 핸들에게 직접
          묻는다 (CLAUDE.md §13).
        - 재생 시작 후 policy.ECHO_GUARD_SEC 동안 VAD 를 무시한다. 그러지 않으면 로봇이
          자기 목소리를 듣고 문장 중간에 멈춘다. 능동 발화를 테스트하기 '전에' 이걸
          해결해야 한다. 안 그러면 모든 게이트 버그 리포트가 실제로는 echo 다
          (CLAUDE.md §22 3단계).
        - critical 생존 확인 프로브는 미리 만들어둔 로컬 오디오를 우선 사용한다.
          네트워크 없이 동작하며, 그것이 바로 프로브가 가장 중요한 상황이다
          (CLAUDE.md §18).
    """
    sentences = state.get("sentences") or []

    # 실제 재생기가 붙어 있을 때도(로봇/노트북 실행) 분류·응답이 콘솔에 보이도록
    # 남긴다. '모든' 발화 경로가 emit 으로 수렴하므로, 여기 한 줄이면
    # 인텐트별로 흩어진 로그를 각각 안 찾아도 된다. main.py 에서
    # logging.basicConfig 를 켜야 실제로 보인다(기본은 꺼져 있다).
    logger.info(
        "intent=%s response=%s",
        state.get("intent"), " ".join(sentences) if sentences else "(no speech)",
    )

    if not sentences:
        # 할 말이 없으면 말하는 중으로 표시하지 않는다. speaking=True 로 두면
        # barge-in 로직이 존재하지 않는 재생을 끊으려 든다.
        return {"speaking": False, "spoken_prefix": ""}

    senior_id = state.get("senior_id") or "unknown"
    player = _player()
    if player is None:
        # 재생기가 없는 환경(테스트, 오디오 장치 없는 개발 PC)에서는 조용히 넘어간다.
        # 다만 무엇을 말하려 했는지는 남긴다.
        logger.info("no speech player configured; would speak: %s", " ".join(sentences))
        return {"speaking": False, "spoken_prefix": ""}

    # 문장을 '하나씩' 넘긴다. 전체를 한 덩어리로 주면 barge-in 이 어디서 끊었는지
    # 알 수 없고 나머지를 정확히 재큐할 수 없다 (CLAUDE.md §13).
    #
    # 이 호출은 즉시 반환해야 한다. 여기서 블로킹하면 말하는 동안 아무도 어르신의
    # 끼어들기를 관찰하지 못해서 양보 우선 정책이 원리적으로 불가능해진다.
    #
    # 핸들을 여기 보관하는 것이 barge-in 복구의 전제다. note_interaction 이
    # 이 핸들에게 "어디까지 말했나"를 묻는다 — state 가 아니라. state 는 그래프
    # 실행 시점의 스냅샷이라 재생이 진행된 만큼 이미 낡아 있다.
    with current_stage("tts_dispatch"):
        TTS_HANDLES[senior_id] = player.speak_async(sentences)

    # 이번 발화가 무엇이었는지 남긴다. 잘렸을 때 나머지를 원래 우선순위로 되돌리려면
    # 우선순위와 origin 을 알아야 하는데, 재생 핸들은 그것을 모른다.
    SPEECH_CONTEXT[senior_id] = {
        "sentences": list(sentences),
        "intent": state.get("intent"),
        "priority": state.get("speech_priority"),
        "origin": state.get("speech_origin", ""),
    }
    return {"speaking": True, "spoken_prefix": ""}


# 재생 중인 발화의 '무엇을 왜 말하고 있었는가'.
#
# 왜 TTS_HANDLES 와 따로인가
#   핸들은 진행 상황(몇 문장 말했나)의 권위이고, 이쪽은 재큐에 필요한 메타데이터다.
#   핸들에 우선순위를 들려주면 오디오 계층이 게이트 정책을 알게 된다.
SPEECH_CONTEXT: dict[str, dict] = {}


def clear_speech_state(senior_id: str) -> None:
    """재생이 끝났거나 취소된 뒤 정리한다."""
    TTS_HANDLES.pop(senior_id, None)
    SPEECH_CONTEXT.pop(senior_id, None)


# 재생기를 주입받는다.
#
# 왜 tts/client.py 를 직접 부르지 않는가
#   TTSClient.synthesize 는 바이트를 '동기'로 만들어 돌려준다. 그걸 여기서 그대로
#   부르면 emit 이 블로킹되고, 위에 적은 이유로 barge-in 이 불가능해진다. 합성과
#   재생을 백그라운드로 돌리는 책임은 오디오 계층에 있고(205번), 그때 이 자리에
#   실제 재생기가 꽂힌다.
_PLAYER = None


def _player():
    return _PLAYER


def set_player(player) -> None:
    """비블로킹 재생기를 설치한다. speak_async(list[str]) -> handle 을 만족해야 한다."""
    global _PLAYER
    _PLAYER = player
