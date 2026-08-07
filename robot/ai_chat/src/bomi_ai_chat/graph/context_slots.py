# robot/ai_chat/src/bomi_ai_chat/graph/context_slots.py
"""현재 대화 문맥 — "거기", "그럼"이 무엇을 가리키는지 결정론으로 정한다.

어디에 위치하는가
    note_interaction 이 매 반응형 턴에 이 모듈로 문맥 후보를 갱신하고,
    context_read 가 날씨·의료 조회의 '지역'을 정할 때 이 모듈에게 묻는다.
    순수 함수만 있다 — I/O 도, 시계 직접 호출도, LLM 도 없다(now 를 인자로 받는다).

왜 존재하는가
    이전에는 조회 지역을 정하는 유일한 지점이 weather.extract_city(text) 였다.
    즉 '이번 발화 한 문장'에 도시명이 없으면 끝이었다. 어르신이 "이번 주말에
    제주도 가"라고 말한 다음 "날씨 어때?"라고 물으면 제주는 사라졌고, "거기
    음식은?"의 '거기'는 아무 데도 가리키지 못했다. 의료 조회는 한술 더 떠
    "근처"·"주변" 같은 상대 표현을 명시적으로 버리고 되물었다
    (docs/natural-conversation/current-state-audit.md A1·A2·D1).

    문장 수준의 이어짐은 프롬프트의 "## 최근 대화" 블록으로 LLM 이 해낼 수 있다.
    그러나 '조회 파라미터'는 프롬프트를 읽지 못한다. 기상청 API 는 격자 좌표를
    받지 문맥을 받지 않는다. 그래서 이 계층이 필요하다.

왜 LLM 이 아니라 규칙인가
    문맥 해석을 생성 호출에 얹으면 턴당 LLM 예산(§16)을 깨거나, 같은 질문이
    날마다 다르게 해석된다. 그리고 무엇보다 **틀렸을 때 설명할 수 없다.**
    "왜 부산 날씨를 알려줬는가"에 답하려면 근거(source)와 신뢰도(confidence)가
    자료로 남아야 한다. 그래서 값만 저장하지 않고 근거를 함께 저장한다.

무엇이 여기 없는가
    전면 코레퍼런스(그 사람=누구, 그때=언제)는 하지 않는다. 조회 파라미터로
    쓰이는 것 — 지금은 지역 — 만 결정론으로 풀고, 나머지 문장 해석은 계속
    LLM 과 최근 대화 블록의 몫이다. 필요 없는 추론을 늘리면 틀릴 자리만 는다.

참고
    CLAUDE.md §17.2(이어짐), §16(LLM 예산), §30(문맥 선택 우선순위)
    docs/natural-conversation/target-architecture.md §3
"""

from __future__ import annotations

from bomi_ai_chat import policy
from bomi_ai_chat.state import ContextCandidate
from bomi_ai_chat.weather.client import extract_city

# 문맥 후보의 종류. 지금은 지역 하나뿐이다 — 조회 파라미터로 실제 쓰이는 것만
# 만든다. 인물·사건은 쓰는 곳이 생길 때 추가한다(쓰지 않는 슬롯은 유지 비용만
# 든다).
LOCATION = "LOCATION"

# 근거(source). "왜 이 지역으로 조회했는가"의 답이 된다.
USER_EXPLICIT = "USER_EXPLICIT"        # 어르신이 도시명을 직접 말했다
PROFILE_DEFAULT = "PROFILE_DEFAULT"    # 프로필 기본 주소 (백엔드 계약 확장 후)

# 유효 범위(scope). 세션이 끝날 때 무엇을 지울지 정한다.
SESSION = "SESSION"
STANDING = "STANDING"                  # 프로필 기본값처럼 늘 바닥에 깔린 것


def new_candidate(
    *,
    type: str,
    value: str,
    source: str,
    now: float,
    confidence: float = 1.0,
    related_topic: str = "",
    scope: str = SESSION,
    ttl_sec: float | None = None,
) -> ContextCandidate:
    """문맥 후보 하나를 만든다. 값과 '근거'를 함께 담는다."""
    ttl = policy.CONTEXT_CANDIDATE_TTL_SEC if ttl_sec is None else ttl_sec
    return {
        "type": type,
        "value": value,
        "source": source,
        "related_topic": related_topic,
        "confidence": confidence,
        "scope": scope,
        "created_at": now,
        "expires_at": now + ttl if ttl > 0 else 0.0,
        "last_used_at": now,
    }


def _is_alive(candidate: ContextCandidate, now: float) -> bool:
    """만료되지 않았고 신뢰도가 쓸 만한가."""
    expires_at = float(candidate.get("expires_at") or 0.0)
    if expires_at and now > expires_at:
        return False
    return float(candidate.get("confidence") or 0.0) >= policy.CONTEXT_MIN_CONFIDENCE


def mentions_reference(text: str) -> bool:
    """"거기", "그쪽", "근처"처럼 앞선 문맥을 가리키는 표현이 있는가."""
    return any(term in text for term in policy.CONTEXT_REFERENCE_TERMS)


def _is_topic_shift(text: str) -> bool:
    """화제를 바꾸는 담화 표지("그런데", "근데")로 시작하는가.

    왜 이것이 필요한가  ★ 필수 시나리오 E
        제주 여행 이야기를 하다가 "그런데 오늘 분리수거 날이야?"라고 물으면
        그것은 제주도의 분리수거가 아니다. 한국어에서 '그런데/근데'는 화제
        전환의 가장 흔한 신호이고, 규칙으로 잡을 수 있는 몇 안 되는 신호다.

    왜 문장 '앞'만 보는가
        "비가 오는데 그런데 말이야" 처럼 문장 중간의 '-는데'는 전환이 아니다.
        앞 몇 글자로 제한하면 오탐이 크게 준다.
    """
    head = text.lstrip()[:4]
    return any(head.startswith(marker) for marker in policy.CONTEXT_TOPIC_SHIFT_MARKERS)


def _correction_target(text: str) -> str | None:
    """"대전 말고 대구"처럼 정정하는 발화에서 '새' 지역을 찾는다.

    무엇을 하는가
        정정 표지("말고", "아니라", "아니고")를 기준으로 문장을 자르고, 표지
        '뒤쪽'에서 도시를 찾는다. 뒤쪽에 없으면 정정이 아니라고 본다.

    왜 필요한가  ★ 필수 시나리오 H
        STT 가 "대구"를 "대전"으로 잘못 들었을 때 어르신은 "대전 말고 대구"라고
        고친다. 이때 앞부분에도 도시명(대전)이 있으므로, 단순히 첫 매치를 쓰는
        extract_city 는 틀린 쪽을 집는다. 정정은 지역 문맥이 바뀌는 가장 중요한
        순간이라 여기서 명시적으로 다룬다.
    """
    for marker in policy.CONTEXT_CORRECTION_MARKERS:
        _, sep, tail = text.partition(marker)
        if sep:
            corrected = extract_city(tail)
            if corrected:
                return corrected
    return None


def update(
    candidates: list[ContextCandidate] | None, text: str, now: float
) -> list[ContextCandidate]:
    """한 턴이 문맥 후보 목록에 미치는 영향을 전부 계산한다. (순수 함수)

    무엇을 하는가
        이 순서로 처리한다.
          1. 만료·저신뢰 후보를 버린다.
          2. 정정 발화면("대전 말고 대구") 같은 종류의 기존 후보를 통째로 교체한다.
          3. 발화에 도시명이 있으면 새 후보로 올린다(신뢰도 1.0).
          4. 아무 언급도 없으면 감쇠시킨다. 화제 전환 표지가 있으면 크게,
             그냥 다른 이야기면 조금.

    왜 감쇠인가 (지우거나 유지하는 대신)
        "이전 지역명을 모든 후속 질문에 무조건 적용"하는 것과 "한 턴만 쓰고
        버리는 것"은 둘 다 틀린다. 전자는 시나리오 E 를 깨고 후자는 시나리오 D 를
        깬다. 감쇠는 '최근에 말할수록 강하게 남는다'는 실제 대화의 성질을 숫자
        하나로 옮긴 것이고, 임계값 아래로 내려가면 자연히 기본값으로 돌아간다.

    반환값
        새 후보 목록. 입력 목록은 변경하지 않는다(순수 함수).
    """
    alive = [dict(c) for c in (candidates or []) if _is_alive(c, now)]

    corrected = _correction_target(text)
    if corrected:
        # 정정은 교체다. 잘못 잡힌 지역을 남겨 두면 다음 "거기"가 다시 그쪽을
        # 가리킨다 (시나리오 H: "이후 대전 문맥 제거").
        alive = [c for c in alive if c.get("type") != LOCATION]
        alive.append(new_candidate(
            type=LOCATION, value=corrected, source=USER_EXPLICIT, now=now))
        return alive

    city = extract_city(text)
    if city:
        alive = [c for c in alive if not (
            c.get("type") == LOCATION and c.get("scope") == SESSION)]
        alive.append(new_candidate(
            type=LOCATION, value=city, source=USER_EXPLICIT, now=now))
        return alive

    # 이번 발화가 지역을 언급하지 않았다. 얼마나 빨리 잊을지만 남는다.
    #
    # 지시 표현("거기")이 있으면 오히려 살아난다 — 어르신이 그 문맥을 지금
    # 쓰고 있다는 뜻이므로 감쇠시키면 안 된다.
    if mentions_reference(text):
        for candidate in alive:
            if candidate.get("type") == LOCATION:
                candidate["last_used_at"] = now
        return alive

    factor = (policy.CONTEXT_TOPIC_SHIFT_DECAY if _is_topic_shift(text)
              else policy.CONTEXT_DECAY_PER_TURN)
    decayed = []
    for candidate in alive:
        if candidate.get("scope") == STANDING:
            # 프로필 기본값은 감쇠하지 않는다. 늘 바닥에 깔려 있는 것이 역할이다.
            decayed.append(candidate)
            continue
        candidate["confidence"] = float(candidate.get("confidence") or 0.0) * factor
        if _is_alive(candidate, now):
            decayed.append(candidate)
    return decayed


def active(
    candidates: list[ContextCandidate] | None, type: str, now: float
) -> ContextCandidate | None:
    """살아 있는 후보 중 가장 믿을 만한 것 하나.

    동점이면 더 최근 것이 이긴다 — 같은 신뢰도라면 방금 한 말이 옳다.
    """
    alive = [c for c in (candidates or [])
             if c.get("type") == type and _is_alive(c, now)]
    if not alive:
        return None
    return max(alive, key=lambda c: (float(c.get("confidence") or 0.0),
                                     float(c.get("created_at") or 0.0)))


def resolve_location(
    state_candidates: list[ContextCandidate] | None, text: str, now: float
) -> tuple[str | None, str]:
    """이 발화의 조회 지역과 그 '근거'를 정한다.

    우선순위 (CLAUDE.md §30)
        1. 이번 발화에 직접 나온 도시명   — 어르신이 방금 말한 것이 항상 최우선
        2. 살아 있는 지역 문맥 후보        — "거기", 혹은 같은 화제의 이어지는 질문
        3. (없음) -> 호출부가 되묻는다      — 지어내지 않는다

    반환값
        (도시명 또는 None, 근거 문자열). 근거는 로그와 관측에 쓴다 — "왜 부산으로
        조회했는가"에 답할 수 있어야 한다.
    """
    explicit = extract_city(text)
    if explicit:
        return explicit, "utterance"

    candidate = active(state_candidates, LOCATION, now)
    if candidate is None:
        return None, "none"
    return str(candidate.get("value") or "") or None, str(
        candidate.get("source") or "context")
