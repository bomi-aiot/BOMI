"""안전 분류와 보호자 에스컬레이션.

어디에 위치하는가
    반응형 경로에서 note_interaction 다음 노드. 즉 인텐트 라우터와 모든 핸들러보다
    '위'다. 이 순서는 의도적이다. T1 턴은 인텐트 분류와 검색을 전부 건너뛰고 곧바로
    에스컬레이션으로 간다.

왜 판단이 생성보다 위인가
    어르신이 "가슴이 아파"라고 말했을 때 중요한 결정은 어느 핸들러가 문장을 쓸지가
    아니다. 사람에게 연락해야 한다는 것이다. 트리아지를 라우터 뒤에 두면 검색 실패나
    핸들러 버그가 응급 상황을 삼켜버릴 수 있다.

이 모듈이 절대 하지 않는 일
    진단. 로봇은 '심각도'를 판단하고 '연결'한다. 병명을 말하지 않고, 용량을 계산하지
    않고, 의학적 결정을 하지 않는다. 제품 규칙이자 DB 계약 규칙이다.

읽는 값   user_input, escalation(침묵 사다리가 미리 세팅한 경우), occupancy
쓰는 값   safety_level, escalation, response

참고
    CLAUDE.md §9 (티어와 동의 모델), §10 (약한 신호로 하는 안전 판단)
"""

from __future__ import annotations

import logging

from bomi_ai_chat import policy
from bomi_ai_chat.clock import clock
from bomi_ai_chat.localstore import outbox
from bomi_ai_chat.localstore import runtime as runtime_store
from bomi_ai_chat.state import ConvState

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 판별기
#
# 둘 다 키워드 + 규칙이며, 그것은 의도된 선택이다. 트리아지는 모든 반응형 턴의
# 임계 경로에 있고 턴 전체 예산이 약 2초이므로, LLM 왕복 없이 로컬에서 돌아야 한다
# (CLAUDE.md §16).
#
# 표현 목록은 전부 policy.py 에 있다. 여기는 판정 순서만 있다 — 목록을 넓히는 것과
# 판정 규칙을 바꾸는 것은 다른 종류의 변경이고, 전자가 훨씬 자주 일어난다.
# ─────────────────────────────────────────────────────────────────────────────

_REVIEW_WARNED = False


def _warn_self_harm_list_unreviewed() -> None:
    """자해 표현 목록이 아직 사람의 검토를 받지 않았음을 프로세스당 한 번 알린다.

    ★ '미구현' 경고와 다르다. 판별기는 동작한다.

        이 목록을 즉흥적으로 만들지 말고 사람이 검토해야 한다는 요구다(유래는
        docs/carebot/PROGRESS.md §8.3). 지금 목록은 보수적인 출발점이고, 실기 배포
        전에 검토를 받아야 한다. 검토 여부를 코드 밖에서만 관리하면 잊히므로, 상태를
        런타임으로 끌어낸다.

        검토가 끝나면 policy.SELF_HARM_MARKERS_REVIEWED 를 True 로 바꾼다.
    """
    global _REVIEW_WARNED
    if _REVIEW_WARNED or policy.SELF_HARM_MARKERS_REVIEWED:
        return
    _REVIEW_WARNED = True
    logger.warning(
        "self-harm marker list has not been human-reviewed yet "
        "(docs/carebot/PROGRESS.md §2.2). "
        "Detection is active but conservative; review the list in policy.py before "
        "deploying to a real senior.")


def _is_self_harm(text: str) -> bool:
    """자해나 자살 의도를 암시하는 발화인가?

    왜 _is_emergency 와 분리되어 있는가
        동의 규칙이 다르기 때문이다. 의료 응급은 '급해서' 에스컬레이션한다.
        자해는 어르신이 명시적으로 아무에게도 말하지 말라고 해도 에스컬레이션한다.
        T3 의 동의 요건을 의도적으로 무시하는 유일한 지점이다 (CLAUDE.md §9).

    ★ 확인 턴을 넣지 않는다
        응급 증상과 다른 점이다. "정말 그런 뜻이세요?"라고 되묻는 것은 어르신에게
        자기 말을 취소할 기회를 주는 것이고, 그 기회는 여기서 도움이 되지 않는다.
        곧바로 사람에게 넘긴다.

    누가 호출하는가
        safety_triage. 다른 무엇보다 먼저.

    반환값
        True -> 즉시 T1, 이유는 "self_harm_override".

    주의사항
        - 로봇이 상담을 시도해서는 안 된다. 따뜻하게, 짧게 반응하고 사람에게 넘긴다.
          자살 관련 대화를 챗봇이 붙잡고 있는 것은, 챗봇이 도움을 불러오는 것보다
          나쁜 결과다. 응답 문구는 여기가 아니라 escalation() 에 둔다.
        - 부정을 검사하지 '않는다'. "죽고 싶지 않아"까지 잡히지만, 그 문장을 말하는
          사람에 대해서도 사람이 한 번 들여다보는 편이 낫다. 여기서는 오탐을 받아들인다.
    """
    _warn_self_harm_list_unreviewed()
    normalized = (text or "").strip()
    return any(marker in normalized for marker in policy.SELF_HARM_MARKERS)


def _is_emergency(text: str) -> bool:
    """급성 신체 응급을 서술하는 발화인가?

    무엇을 하는가
        세 단계로 판정한다.
          1. 명시적 요청("아들한테 전화해줘", "119") -> 즉시 True.
             증상 서술이 아니라 지시이므로 부정·시제 검사를 하지 않는다.
          2. 증상 표현을 찾는다. 없으면 False.
          3. **부정을 먼저**, 그다음 시각 표현을 본다. 하나라도 걸리면 False.

    ★ 왜 부정이 긍정보다 먼저인가
        "안 아파"에는 "아파"가 그대로 들어 있다. 순서를 뒤집으면 정반대로 판정하고,
        괜찮다고 말한 어르신 때문에 보호자가 호출된다. 206 의 `_is_completion_report`
        ("약 안 먹었어")가 만난 것과 같은 함정이다.

    ★ 왜 시제 어미가 아니라 '시각 표현'으로 판정하는가  — 이 함수의 핵심 판단
        한국어는 완료된 사건이 지금 중요할 때에도 과거형을 쓴다.

            "넘어졌어요"   과거형이지만 방금 넘어진 것이다. 명백한 응급
            "어제 아팠어"  같은 과거형이지만 응급이 아니다

        둘을 가르는 것은 어미가 아니라 시각 표현이다. 어미(ㅆ 받침)로 판정하면
        "넘어졌어"를 억제하게 되고, 그것은 되돌릴 수 없는 미탐이다.

        그래서 "어제/지난주/예전"만 억제한다. 단 "어제부터"는 지금까지 이어진다는
        뜻이므로 억제하지 않는다.

    누가 호출하는가
        safety_triage.

    반환값
        True -> 확인 턴으로 간다. 곧바로 T1 이 아니다 (safety_triage 참고).

    주의사항
        위험한 쪽으로 recall 을 높인다. 미탐이 오탐보다 훨씬 나쁘다. 단 그 전제는
        "알림이 값싸게 무시될 수 있어야 한다"이다 — 119 직통이었다면 이 판정은
        전부 반대로 잡아야 한다 (CLAUDE.md §9).
    """
    normalized = (text or "").strip()
    if not normalized:
        return False

    # 1. 명시적 요청. 어르신이 연락해 달라고 말했으면 그것으로 끝이다.
    if any(request in normalized for request in policy.EMERGENCY_EXPLICIT_REQUESTS):
        return True

    # 2. 위험 신호가 있는가. 통증은 부위를 함께 본다.
    if not _has_risk_signal(normalized):
        return False

    # 3. 부정을 먼저. 위 docstring 참고.
    if any(negation in normalized for negation in policy.SYMPTOM_NEGATIONS):
        return False

    if _refers_to_the_past(normalized):
        return False

    return True


def _has_risk_signal(text: str) -> bool:
    """확인 질문을 던질 만한 신호인가.

    ★ 통증은 부위로 갈린다  — 이 함수의 핵심

        "무릎이 아파"는 독거노인에게 가장 흔한 말 중 하나이고 응급이 아니다.
        그것마다 "아드님께 연락드릴까요?"를 묻는 로봇은 무섭고, 보호자는 곧 알림을
        읽지 않게 된다. **그리고 그때부터 "가슴이 아파"를 놓친다.**

        시끄러운 감지기는 짜증이 아니라 안전 실패다 (CLAUDE.md §10).

    세 갈래
        고위험 부위       -> True (가슴, 머리, 배…)
        만성 통증 부위     -> False (무릎, 허리, 어깨…)
        부위를 말하지 않음  -> True. 애매하므로 물어서 확정한다

    주의사항
        고위험과 만성이 함께 나오면 고위험이 이긴다. "무릎도 아프고 가슴도 아파"를
        만성으로 처리하면 안 된다.
    """
    if any(symptom in text for symptom in policy.EMERGENCY_SYMPTOMS):
        return True

    if not any(word in text for word in policy.PAIN_WORDS):
        return False

    if any(part in text for part in policy.HIGH_RISK_BODY_PARTS):
        return True

    # 만성 부위만 언급됐다. 안부의 영역이다.
    if any(part in text for part in policy.CHRONIC_PAIN_PARTS):
        return False

    # 부위를 말하지 않았다. 물어본다.
    return True


def _refers_to_the_past(text: str) -> bool:
    """'지금이 아니다'를 뜻하는 시각 표현이 있는가.

    "어제부터 아파"는 어제 일이 아니라 지금도 아픈 것이다. 시각 표현 바로 뒤에
    이어짐 표지가 붙으면 억제하지 않는다 — 이것을 놓치면 이틀째 아픈 어르신이
    조용히 걸러진다.
    """
    for word in policy.PAST_TIME_WORDS:
        index = text.find(word)
        if index < 0:
            continue
        tail = text[index + len(word):]
        if any(tail.startswith(marker) for marker in policy.ONGOING_MARKERS):
            continue
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 트리아지 노드
# ─────────────────────────────────────────────────────────────────────────────


def safety_triage(state: ConvState) -> dict:
    """내용 작업이 시작되기 전에 이 턴의 안전 티어를 분류한다.

    무엇을 하는가
        자해를 먼저 확인하고, 그다음 응급, 없으면 "none" 으로 떨어진다.
        또한 미리 세팅된 escalation 을 그대로 통과시킨다. 침묵 사다리가 소진되면
        safety_level 을 이미 T1 으로 세팅한 채 그래프를 호출하는데, 이때는 분류할
        발화가 없다. 발화의 '부재'가 곧 신호이기 때문이다.

    누가 호출하는가
        build.py, note_interaction 다음. jobs.ticks.silence_tick 에서 T1 이 미리
        세팅된 상태로도 도달한다.

    무엇을 호출하는가
        _is_self_harm, _is_emergency (로컬, I/O 없음, LLM 없음).

    반환값
        {"safety_level": "T1", "escalation": {...}}
            -> route_triage 가 escalation 으로 보내며 인텐트 분류를 완전히 건너뛴다
        {"safety_level": "none"}
            -> 일반 파이프라인

    주의사항
        T2, T3, T4 는 여기서 결정하지 '않는다'. 이 노드는 "지금 응급인가?"에만 답한다.
        T2 는 일간 배치, T3 는 정서 핸들러가 큐에 넣고 나중에 묻고, T4 는 로봇을
        떠나지 않는다. 네 티어를 한 노드에서 분류하려 하면 '긴급도'와 '사생활'을
        뒤섞게 되는데, 그 둘은 티어 체계가 세워진 서로 독립적인 두 축이다
        (CLAUDE.md §9).
    """
    # 침묵 사다리가 이미 결정했다. 말한 것이 없으니 분류할 것도 없다. 그대로 통과시킨다.
    if state.get("safety_level") == "T1" and state.get("escalation"):
        return {}

    text = state.get("user_input", "")
    senior_id = state.get("senior_id") or ""

    # 자해가 먼저다. 확인 턴 없이 곧바로 넘긴다.
    if _is_self_harm(text):
        _clear_pending_check(senior_id)
        return {
            "safety_level": "T1",
            "escalation": {"reason": "self_harm_override", "ts": clock.now()},
            "pending_safety_check": None,
        }

    # 확인 질문을 던져둔 상태라면, 이 발화가 그 답이다.
    if state.get("pending_safety_check"):
        return _resolve_pending_check(state, text, senior_id)

    if _is_emergency(text):
        return _open_or_escalate(state, text, senior_id)

    return {"safety_level": "none"}


def _open_or_escalate(state: ConvState, text: str, senior_id: str) -> dict:
    """증상을 들었다. 확인 질문을 던지거나, 곧바로 부른다.

    ★ 왜 키워드 한 번에 부르지 않는가
        증상 표현은 애매하다. "아파"는 무릎일 수도 가슴일 수도 있고, 어제 이야기를
        하는 중일 수도 있다. 질문 하나가 그 애매함을 명확한 응답으로 바꾼다 —
        침묵 사다리가 프로브로 하는 것과 같은 기법이다 (CLAUDE.md §10).

    왜 명시적 요청은 예외인가
        어르신이 "아들한테 전화해줘"라고 말했는데 "정말요?"라고 되묻는 로봇은
        도움이 되지 않는다. 이미 확인한 것을 또 묻는 셈이다.
    """
    explicit = any(request in text for request in policy.EMERGENCY_EXPLICIT_REQUESTS)
    if explicit:
        _clear_pending_check(senior_id)
        return {
            "safety_level": "T1",
            "escalation": {"reason": "explicit_request", "ts": clock.now(),
                           "utterance_marker": "explicit"},
            "pending_safety_check": None,
        }

    deadline = clock.now() + policy.SAFETY_CONFIRMATION_TIMEOUT_SEC
    if senior_id:
        # 틱이 읽어야 한다. 어르신이 아예 대답하지 않으면 이 확인은 그래프로 다시
        # 돌아오지 않으므로, 내구 저장소에 남겨 silence_tick 이 마감을 본다.
        runtime_store.save(senior_id, safety_check_until=deadline)

    logger.info("emergency wording heard; asking one confirming question before escalating")
    return {
        # "confirm" 은 T1 도 아니고 평범한 턴도 아니다. route_triage 가 이 값을 보고
        # 문맥 조회와 LLM 을 건너뛰어 확인 질문만 말하게 한다.
        "safety_level": "confirm",
        "pending_safety_check": {"reason": "emergency", "asked_at": clock.now(),
                                 "expires_at": deadline},
    }


def _resolve_pending_check(state: ConvState, text: str, senior_id: str) -> dict:
    """확인 질문에 대한 답을 판정한다.

    ★ 애매하면 '부른다'. 계약 대화와 정반대다.

        contract_dialogue 에서는 애매한 답을 확인으로 인정하지 않는다 — 동의를
        잘못 기록하면 신뢰를 잃기 때문이다. 여기서는 반대로, 애매하면 에스컬레이션한다.
        놓치면 사람을 잃기 때문이다.

        같은 '애매함'이 한쪽에서는 '하지 않음'이고 다른 쪽에서는 '함'이다.
        비용이 반대 방향이라 규칙도 반대다.

    무엇이 취소하는가
        명확한 부정뿐이다 — "괜찮아", "아니야". 그 외에는 전부 부른다.
    """
    from bomi_ai_chat.graph import contract_dialogue

    cancelled = (
        any(negation in text for negation in policy.SYMPTOM_NEGATIONS)
        or contract_dialogue.read_affirmation(text) is False
    )

    _clear_pending_check(senior_id)

    if cancelled:
        logger.info("the senior said they are fine; not escalating")
        return {"safety_level": "none", "pending_safety_check": None}

    pending = state.get("pending_safety_check") or {}
    return {
        "safety_level": "T1",
        "escalation": {
            "reason": pending.get("reason", "emergency"),
            "ts": clock.now(),
            # 판단 근거를 남긴다. 보호자 화면과 사후 튜닝이 함께 본다.
            "confirmed_by": "senior_reply",
        },
        "pending_safety_check": None,
    }


def _clear_pending_check(senior_id: str) -> None:
    if senior_id:
        runtime_store.save(senior_id, safety_check_until=0.0)


# 확인 질문. 진단하지 않고, 티어를 말하지 않고, 겁을 주지 않는다.
_CONFIRM_QUESTION = "많이 불편하세요? 아드님께 연락드릴까요?"


def safety_confirm(state: ConvState) -> dict:
    """확인 질문 하나만 말한다. 문맥 조회도 LLM 도 거치지 않는다.

    왜 별도 노드인가
        이 발화는 대화가 아니라 안전 절차의 일부다. 일반 파이프라인으로 보내면
        인텐트 분류와 생성 호출이 붙어서, 어르신이 "가슴이 아파"라고 말한 직후에
        LLM 이 무슨 말을 지어낼지가 네트워크 상태에 달리게 된다.

        문구는 고정이다. 진단하지 않고, 티어를 말하지 않고, 겁을 주지 않는다.

    누가 호출하는가
        build.py. safety_level == "confirm" 일 때만.
    """
    return {"response": _CONFIRM_QUESTION}


def route_triage(state: ConvState) -> str:
    """조건부 엣지: T1 은 인텐트 라우터를 건너뛰고, 확인 질문도 마찬가지다.

    왜 존재하는가
        응급 상황이 백엔드 컨텍스트 호출이나 LLM 을 기다려서는 안 된다.
        그 둘의 성공에 의존해서도 안 된다.

    누가 호출하는가
        build.py, safety_triage 다음.

    반환값
        "escalation"     T1. 보호자를 부른다
        "safety_confirm" 확인 질문 하나를 말한다
        "context_read"   평범한 턴
    """
    level = state.get("safety_level")
    if level == "T1":
        return "escalation"
    if level == "confirm":
        return "safety_confirm"
    return "context_read"


def escalation(state: ConvState) -> dict:
    """보호자 알림을 큐에 넣고, 어르신에게는 차분한 응답을 준다.

    무엇을 하는가
        알림을 로컬 발신 큐에 쓰고, 전송을 시도하고, 짧은 안심 발화를 반환한다.
        그 발화는 다른 출력과 똑같이 response_shaper 를 거친다.

    왜 큐가 먼저인가
        네트워크는 언젠가 끊기고, 끊긴 연결로 발사된 알림은 그냥 사라진다.
        안전 기기에서 그것은 용납이 안 되므로, 전송보다 저장이 먼저다.
        쓰고, 시도하고, 실패하면 jobs.ticks 가 재시도한다. Outbox 가 "있으면 좋은 것"
        에서 "필수"로 승격된 이유다 (CLAUDE.md §18, §19).

    누가 호출하는가
        build.py. T1 분기에서만.

    무엇을 호출하는가
        localstore.enqueue_outbound, notify.notify_guardian.

    반환값
        {"response": ...} — 차분하고 짧게. 전문 용어 없이, 티어 이름 없이.

    주의사항
        - T1 은 guardian_sharing_consent_status 와 무관하게 전송된다. 이것은 의도된
          제품 결정(생명 안전)이며, 놀라지 않도록 동의 안내 문구에 명시해야 한다.
          T2 와 T3 는 동의를 확인한다.
        - 이 응답에 진단성 표현을 넣지 않고, 어떤 티어가 발동했는지도 절대 말하지
          않는다. 어르신에게는 감시 시스템이 아니라 말벗으로 들려야 한다.
    """
    # 보호자에게 무엇을 보내는지가 이 딕셔너리에 전부 적혀 있다.
    # ts 는 Jetson 시각이 권위다(§11) — clock 으로만 읽는다.
    reason = (state.get("escalation") or {}).get("reason", "emergency")
    payload = {
        **(state.get("escalation") or {}),
        # 약한 신호들을 함께 싣는다. 에스컬레이션 판정은 단일 임계치가 아니라 조합이고,
        # 판단 근거가 있어야 보호자와 사후 튜닝이 볼 수 있다 (CLAUDE.md §10).
        "occupancy": state.get("occupancy"),
        "rest_state": state.get("rest_state"),
        "ts": clock.now(),
    }
    # 어르신이 한 말은 보내지 않는다.
    #
    # 왜인가: 보호자에게 필요한 것은 "가서 봐 주세요"이지 발화 원문이 아니다.
    # 원문을 실으면 T4("우리끼리 얘기")가 T1 알림에 묻어 나가는 경로가 생기고,
    # 그 경로는 한 번 생기면 되돌리기 어렵다 (CLAUDE.md §9).

    # 전송보다 저장이 먼저다.
    #
    # 네트워크는 언젠가 끊기고, 끊긴 연결로 발사된 알림은 그냥 사라진다. 하필 그
    # 순간이 알림이 가장 중요한 순간이다. 이 쓰기는 동기이며(db.py 의
    # synchronous=FULL), 이 줄이 반환됐다면 전원이 끊겨도 알림은 살아 있다.
    #
    # 실제 전송은 jobs.ticks.outbox_flush 가 한다. 여기서 직접 보내지 않는 이유는
    # 전송 지연이 어르신에게 돌아갈 응답을 붙잡아서는 안 되기 때문이다.
    # 같은 사유의 알림이 방금 나갔으면 큐에 넣지 않는다.
    #
    # ★ 억제되는 것은 '보호자 알림'뿐이고, 아래의 어르신 응답은 그대로 나간다.
    #   두 번째로 "가슴이 아파"라고 하신 분에게 로봇이 침묵하면 그건 다른 종류의
    #   실패다. 보호자는 이미 알고 있고, 어르신은 여전히 대답을 기다린다.
    #
    #   사유가 다르면 억제하지 않는다 — emergency 뒤의 self_harm_override 는
    #   중복이 아니라 악화다 (policy.T1_DUPLICATE_SUPPRESSION_SEC 의 주석 참고).
    senior_id = state.get("senior_id")
    suppressed = False
    if senior_id:
        try:
            stored = runtime_store.load(senior_id)
            elapsed = clock.now() - (stored.get("last_escalation_at") or 0.0)
            same_reason = stored.get("last_escalation_reason") == reason
            suppressed = (
                same_reason and elapsed < policy.T1_DUPLICATE_SUPPRESSION_SEC
            )
        except Exception:  # noqa: BLE001 - 억제 판정 실패가 알림을 막으면 안 된다
            # 읽지 못했으면 '중복이 아니다'로 본다. 안전 기기에서 모르는 쪽의
            # 기본값은 '보낸다'여야 한다.
            logger.exception("could not read the last escalation; sending anyway")
            suppressed = False

    if suppressed:
        # 조용히 버리지 않는다. 억제도 하나의 판단이므로 근거가 로그에 남아야
        # 사후에 "왜 알림이 한 번만 갔나"를 답할 수 있다 (CLAUDE.md §26).
        logger.warning(
            "T1 alert suppressed as a duplicate: reason=%s within %.0fs; "
            "the senior still gets a response",
            reason, policy.T1_DUPLICATE_SUPPRESSION_SEC,
        )
    else:
        try:
            outbox.enqueue("T1", payload)
        except Exception:  # noqa: BLE001 - 큐 쓰기 실패가 응답까지 막으면 안 된다
            # 여기까지 오면 로컬 저장소가 망가진 것이다. 어르신에게는 여전히
            # 대답하되, 이 실패는 조용히 지나가서는 안 된다.
            logger.exception("FAILED to queue a T1 guardian alert (reason=%s); "
                             "the guardian may never be notified", reason)

        logger.warning("T1 escalation queued: reason=%s occupancy=%s",
                       reason, state.get("occupancy"))

        # 큐에 넣은 뒤에 기록한다. 넣지 못했는데 '보냈다'고 적으면 다음 진짜
        # 알림까지 억제된다 — 억제 로직이 알림을 삼키는 최악의 형태다.
        if senior_id:
            try:
                runtime_store.save(
                    senior_id,
                    last_escalation_at=clock.now(),
                    last_escalation_reason=reason,
                )
            except Exception:  # noqa: BLE001 - 기록 실패가 응답을 막으면 안 된다
                logger.exception("could not record the escalation timestamp; "
                                 "duplicates may not be suppressed")

    return {"response": _RESPONSES.get(reason, _RESPONSES["emergency"])}


# 어르신에게 돌아가는 말.
#
# 세 가지를 지킨다.
#   진단하지 않는다        "심장마비 같아요"는 절대 안 된다. 로봇은 판단하고 연결할 뿐이다
#   티어를 말하지 않는다   "T1 로 분류했어요"는 감시 시스템의 말이다
#   겁을 주지 않는다      이미 무서운 상황이다. 로봇까지 놀라면 안 된다
#
# 자해는 문구가 다르다. 상담을 시도하지 않고, 혼자가 아니라는 말만 하고 넘긴다.
# 챗봇이 자살 대화를 붙잡고 있는 것은 도움을 부르는 것보다 나쁜 결과다 (CLAUDE.md §9).
_RESPONSES = {
    "emergency": "제가 아드님께 연락드릴게요. 잠깐만 이대로 계세요.",
    "explicit_request": "네, 지금 바로 연락드릴게요.",
    "self_harm_override": "그런 마음이 드셨군요. 혼자 두고 싶지 않아요. "
                          "제가 지금 가족분께 연락드릴게요.",
    "no_response": "한참 대답이 없으셔서 걱정됐어요. 아드님께 연락드릴게요.",
}
