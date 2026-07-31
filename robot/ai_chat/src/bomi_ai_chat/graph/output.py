"""응답 정제와 음성 출력 — 마지막 두 노드이며, 의도된 병목이다.

어디에 위치하는가
    '모든' 경로가 여기로 수렴한다. 일곱 개 핸들러와 escalation 전부.
    response_shaper 를 거치지 않고 스피커에 도달하는 것은 없다.

왜 그 병목이 의도적인가
    출력이 음성이기 때문이다. 듣는 사람은 훑어 읽을 수 없고, 다시 읽을 수 없고,
    우리 사용자의 경우 청력이 떨어져 있을 수 있다. 사실은 완벽한 세 문단짜리 답변은
    제품으로서 실패다. 일곱 개 핸들러가 각자 그걸 기억하길 기대하는 대신,
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

from bomi_ai_chat import policy
from bomi_ai_chat.state import ConvState

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
    # TODO: 한국어를 제대로 인식하는 분할.
    return [t.strip() for t in text.split(". ") if t.strip()]


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

    # TODO(프롬프트 우선): 정제는 대부분 프롬프트에서 이뤄져야 한다(CLAUDE.md §16 9단계).
    #   여기는 강제 안전망으로 남기고, 실제로 절단이 일어나면 로그를 남긴다.
    #   그 로그가 곧 "프롬프트를 고쳐야 한다"는 신호다.
    sentences = split_sentences(text)[:limit]

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
        - 문장을 '하나씩' 투입하고 완료될 때마다 spoken_prefix 를 갱신한다. 전체
          텍스트를 한 덩어리로 TTS 에 넘기면 barge-in 이 어디서 끊었는지 알 수 없고,
          나머지를 정확히 재큐할 수 없다.
        - 재생 시작 후 policy.ECHO_GUARD_SEC 동안 VAD 를 무시한다. 그러지 않으면 로봇이
          자기 목소리를 듣고 문장 중간에 멈춘다. 능동 발화를 테스트하기 '전에' 이걸
          해결해야 한다. 안 그러면 모든 게이트 버그 리포트가 실제로는 echo 다
          (CLAUDE.md §22 3단계).
        - critical 생존 확인 프로브는 미리 만들어둔 로컬 오디오를 우선 사용한다.
          네트워크 없이 동작하며, 그것이 바로 프로브가 가장 중요한 상황이다
          (CLAUDE.md §18).
    """
    # TODO(audio): TTS_HANDLES[senior_id] = tts.speak_async(state["sentences"], ...)
    return {"speaking": True, "spoken_prefix": ""}
