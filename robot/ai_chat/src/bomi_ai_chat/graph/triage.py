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

from bomi_ai_chat.clock import clock
from bomi_ai_chat.state import ConvState

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 판별기
#
# 둘 다 지금은 키워드 + 규칙이며, 그것은 의도된 선택이다. 트리아지는 모든 반응형 턴의
# 임계 경로에 있고 턴 전체 예산이 약 2초이므로, LLM 왕복 없이 로컬에서 돌아야 한다
# (CLAUDE.md §16).
#
# ★ 현재 상태: 둘 다 미구현이며 항상 False 를 돌려준다 (S15P11E102-210).
#   즉 이 기기는 지금 안전 판정을 하지 못한다. 실기 배포 전에 반드시 210 이 끝나야 한다.
#   호출될 때마다 경고를 남겨서 그 상태가 조용히 지나가지 않게 한다.
# ─────────────────────────────────────────────────────────────────────────────

# 프로세스당 한 번만 경고한다. 매 턴 찍으면 로그가 묻히고, 묻힌 경고는 없는 경고다.
_WARNED: set[str] = set()


def _warn_triage_not_implemented(detector: str) -> None:
    if detector in _WARNED:
        return
    _WARNED.add(detector)
    logger.warning(
        "safety triage detector '%s' is NOT IMPLEMENTED (S15P11E102-210); "
        "this device cannot detect that condition. Do not deploy to a real senior.",
        detector,
    )


def _is_self_harm(text: str) -> bool:
    """자해나 자살 의도를 암시하는 발화인가?

    왜 _is_emergency 와 분리되어 있는가
        동의 규칙이 다르기 때문이다. 의료 응급은 '급해서' 에스컬레이션한다.
        자해는 어르신이 명시적으로 아무에게도 말하지 말라고 해도 에스컬레이션한다.
        T3 의 동의 요건을 의도적으로 무시하는 유일한 지점이다 (CLAUDE.md §9).

    누가 호출하는가
        safety_triage. 다른 무엇보다 먼저.

    반환값
        True -> 즉시 T1, 이유는 "self_harm_override".

    주의사항
        로봇이 상담을 시도해서는 안 된다. 따뜻하게, 짧게 반응하고 사람에게 넘긴다.
        자살 관련 대화를 챗봇이 붙잡고 있는 것은, 챗봇이 도움을 불러오는 것보다
        나쁜 결과다. 응답 문구는 여기가 아니라 escalation() 에 둔다.
    """
    # 아직 구현되지 않았다. S15P11E102-210 에서 채운다.
    #
    # 왜 여기서 표현 목록을 만들지 않는가
    #   자해 판별 어휘는 사람이 검토해야 한다. 즉흥적으로 만든 목록은 미탐(놓침)과
    #   오탐(엉뚱한 사람에게 자해 알림)을 동시에 만들고, 둘 다 사람에게 해를 끼친다.
    #   이 판단은 코드 리뷰가 아니라 사람의 검토를 거쳐야 한다 (HANDOFF §7).
    #
    # 왜 예외가 아니라 False 인가
    #   예외를 올리면 반응형 대화 자체가 성립하지 않는다. 트리아지는 모든 턴의
    #   임계 경로에 있어서, 여기서 죽으면 로봇이 한 마디도 못 한다. 설계된 구축
    #   순서(반응형 -> 에코 -> 능동 -> 안전)를 따르려면 그 앞 단계들이 돌아가야 한다.
    #
    #   대신 조용히 넘어가지 않는다. 아래 경고가 "이 기기의 안전 판정이 꺼져 있다"를
    #   운영자에게 알린다. 실기 배포 전에 반드시 210 이 끝나야 한다.
    _warn_triage_not_implemented("self_harm")
    return False


def _is_emergency(text: str) -> bool:
    """급성 신체 응급을 서술하는 발화인가?

    무엇을 하는가
        급성 증상 표현("가슴이 아파", "숨이 안 쉬어져", "넘어졌어")과 명시적 요청
        ("아들한테 전화해줘", "119")을 찾는다.

    누가 호출하는가
        safety_triage.

    반환값
        True -> T1.

    주의사항
        부정과 시제가 여기서는 문제의 전부다.
          "안 아파"      -> 응급 아님
          "어제 아팠어"  -> 응급 아님
          "아파"        -> 응급
        단순 부분 문자열 매칭은 셋 다 틀리고, ASR 노이즈와 노인 발음이 더 악화시킨다.
        완화책은 두 개이며 둘 다 필요하다.
          1. 위험한 쪽으로 recall 을 높인다. 미탐이 오탐보다 훨씬 나쁘다. 단 그 알림이
             값싸게 무시될 수 있어야 한다는 전제하에.
          2. 키워드 한 번에 에스컬레이션하지 않는다. 확인 턴 하나를 넣는다
             ("괜찮으세요? 아드님께 연락할까요?"). 애매한 신호를 명확한 응답으로
             바꾸는 것이며, 침묵 사다리가 쓰는 것과 같은 기법이다 (CLAUDE.md §10).
    """
    # 아직 구현되지 않았다. S15P11E102-210 에서 채운다.
    # 부정·시제 처리가 이 판별의 본체이고, 그것 없이 키워드만 넣으면 "안 아파"와
    # "어제 아팠어"를 응급으로 올린다. 반쪽짜리 구현이 없느니만 못한 드문 경우다.
    # False 로 두는 이유는 _is_self_harm 과 같다.
    _warn_triage_not_implemented("emergency")
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

    if _is_self_harm(text):
        return {
            "safety_level": "T1",
            "escalation": {"reason": "self_harm_override", "ts": clock.now()},
        }

    if _is_emergency(text):
        return {
            "safety_level": "T1",
            "escalation": {"reason": "emergency", "ts": clock.now()},
        }

    return {"safety_level": "none"}


def route_triage(state: ConvState) -> str:
    """조건부 엣지: T1 은 인텐트 라우터를 건너뛴다.

    왜 존재하는가
        응급 상황이 백엔드 컨텍스트 호출이나 LLM 을 기다려서는 안 된다.
        그 둘의 성공에 의존해서도 안 된다.

    누가 호출하는가
        build.py, safety_triage 다음.
    """
    return "escalation" if state.get("safety_level") == "T1" else "context_read"


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
    # 아래 TODO(localstore)/TODO(notify) 두 호출이 그대로 소비할 payload 다. 지금은
    # 호출이 없어서 미사용이지만, 보호자에게 무엇을 보내는지가 이 딕셔너리에 적혀 있다.
    # ts 는 Jetson 시각이 권위다(§11) — clock 으로만 읽는다.
    payload = {  # noqa: F841
        **(state.get("escalation") or {}),
        "occupancy": state.get("occupancy"),
        "rest_state": state.get("rest_state"),
        "ts": clock.now(),
    }

    # TODO(localstore): enqueue_outbound(tier="T1", payload=payload) — 동기 쓰기.
    #   내구성을 완화하지 '않는' 유일한 지점이다(policy.py 주석 참고).
    # TODO(notify): notify_guardian("T1", payload). 실패해도 괜찮다. 재시도는 큐가
    #   책임진다. 전송 예외가 전파되어 턴을 중단시키게 두어서는 안 된다.

    return {"response": "괜찮으세요? 제가 아드님께 연락드릴게요."}
