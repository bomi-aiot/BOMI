"""표현 다양화 키 — "같은 종류의 알림"이 무엇인지 정의하는 순수 함수 하나.

어디에 위치하는가
    localstore/phrasings.py(기록·조회)와 graph/build.py(memory_write) 사이의
    이음새. 이 함수가 만든 키로 저장하고, 같은 키로 조회한다. 저장소는 이 키가
    무엇을 뜻하는지 몰라도 된다 — 그냥 문자열이다.

왜 별도 모듈인가
    이 판단(무엇을 "같은 알림"으로 볼지, 무엇을 다양화 대상에서 뺄지)은 정책이고,
    정책은 테스트가 그래프 없이 직접 물어볼 수 있어야 한다. build.py 나 context.py
    안에 묻으면 그때마다 그래프를 띄워야 확인할 수 있다.

참고
    CLAUDE.md §17.8, §19(정책 상수는 policy.py) / S15P11E102-256
"""

from __future__ import annotations

from bomi_ai_chat import policy


def phrasing_key(origin: str, intent: str) -> str:
    """origin 과 intent 로 "같은 종류의 알림" 키를 만든다.

    무엇을 하는가
        빈 값이거나, policy.RECENT_PHRASING_EXCLUDED_ORIGIN_PREFIXES 에 걸리는
        origin 이면 빈 문자열을 돌려준다 — "다양화 대상이 아니다"라는 뜻이다.
        그 외에는 "{intent}:{origin}" 을 그대로 키로 쓴다.

    왜 origin 을 그대로 쓰는가 (날짜를 넣지 않는 이유)
        jobs/ticks.schedule_tick 이 만드는 origin(예: "schedule:meal:0800")에는
        애초에 날짜가 없다 — 매일 같은 시각의 식사 권유는 항상 같은 origin 이다.
        그래서 이 함수가 따로 날짜를 지우지 않아도 "같은 끼니는 같은 키"가
        저절로 성립한다. 반대로 "schedule:meal:*" 과 "schedule:water:*" 는
        origin 의 kind 부분이 다르므로 자동으로 분리된다.

    누가 호출하는가
        graph/build.py 의 memory_write(기록), graph/context.py 의 context_read(조회).
        둘이 같은 함수를 써야 기록할 때와 찾을 때의 키가 어긋나지 않는다.

    인자
        origin: SpeechProposal["origin"](state.py 참고). 능동/명령 턴에서만 의미가
            있다. 반응형 턴은 이 함수를 부르기 전에 이미 걸러진다(context.py 참고).
        intent: 이 턴에서 실제로 쓴(또는 쓸) 핸들러. 같은 origin 이라도 다른
            핸들러가 쓰면 다른 종류의 발화이므로 키에 포함한다.

    반환값
        비지 않은 문자열, 또는 다양화 대상이 아니면 "".

    주의사항
        - 침묵 프로브(origin "silence_ladder:*")와 T3 동의 질문(origin
          "t3_consent:*")은 의도적으로 제외한다. 이유는
          policy.RECENT_PHRASING_EXCLUDED_ORIGIN_PREFIXES 주석 참고.
        - greeting/onboarding/clarification 인텐트는 build_prompt 를 쓰지 않고
          고정된 문구(백엔드가 내려준 text, 또는 계약 질문 템플릿)로 말하므로
          여기서 키를 만들어도 실제로 프롬프트에 쓰이지 않는다. 이 함수가 그런
          intent 를 특별히 걸러내지 않는 이유는, 걸러내는 지식(어느 핸들러가
          build_prompt 를 쓰는지)을 이 순수 함수에 두면 핸들러 목록이 바뀔 때마다
          같이 고쳐야 하기 때문이다 — 여기서는 "같은 알림을 구분하는 방법"만
          책임진다.
    """
    origin = (origin or "").strip()
    intent = (intent or "").strip()
    if not origin or not intent:
        return ""
    if any(origin.startswith(prefix) for prefix in policy.RECENT_PHRASING_EXCLUDED_ORIGIN_PREFIXES):
        return ""
    return f"{intent}:{origin}"
