"""프롬프트 조립 — 그래프 없이 테스트되는 순수 함수.

왜 순수 함수인가
    자연스러움은 대부분 여기서 결정된다. 그래서 반복이 값싸야 한다. 그래프를 띄우고
    LLM 을 불러야 프롬프트 한 줄을 확인할 수 있다면, 아무도 프롬프트를 다듬지 않는다.
    build_prompt 는 dict 를 받아 문자열을 돌려준다. 네트워크도, 상태도, 시계도 없다.

왜 템플릿이 파일인가
    프롬프트는 코드다. 리뷰되고, diff 로 읽히고, 누가 왜 바꿨는지 기록돼야 한다.
    함수 안의 삼중 인용 문자열은 그중 아무것도 안 된다. templates/ 아래 파일로 둔다.

조립 순서 (CLAUDE.md §16)
    각 항목이 §17 의 검증 항목 하나에 대응한다.
      1. 시스템: 페르소나, 발화 규칙, 금지, 호칭
      2. 고정 사실: 이름, 나이, 질환, 복약
      3. 선호와 회피 목록 — 회피는 '정보'가 아니라 '금지문'으로
      4. 오늘 상태: 복약 이행, 기분, 마지막 상호작용
      5. 기억: 검색된 memory 와 요약, 날짜를 붙여서
      6. 문서: info 인텐트에서만
      7. 최근 대화: Raw 6~12개
      8. 현재 입력과 '왜 말하는가'
      9. 출력 제약 재진술 — 끝에 한 번 더

왜 제약을 두 번 쓰는가
    맨 위에만 적은 제약은 긴 문맥에 묻힌다. 모델은 마지막에 읽은 것을 더 잘 따른다.
    중복이 아니라 위치가 기능이다.

참고
    CLAUDE.md §14 (발화 규칙), §16 (조립 순서), §17 (자연스러움의 조작적 정의)
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

from bomi_ai_chat import policy

_TEMPLATE_DIR = Path(__file__).parent / "templates"


@cache
def load_template(name: str) -> str:
    """templates/ 의 파일을 읽는다. 프로세스 수명 동안 캐시한다.

    왜 캐시하는가
        매 턴 디스크를 읽을 이유가 없고, 이 기기의 저장 매체는 microSD 다.
        템플릿을 고치면 프로세스를 재시작해야 하는데, 프롬프트 변경은 배포이므로
        그게 맞는 동작이다.
    """
    path = _TEMPLATE_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"프롬프트 템플릿이 없습니다: {path}")
    return path.read_text(encoding="utf-8").strip()


def _section(title: str, body: str) -> str:
    """제목이 붙은 블록. body 가 비면 아무것도 만들지 않는다.

    빈 섹션을 넣지 않는 이유는 모델이 "기억: (없음)"을 보면 기억이 없다는 사실 자체를
    화제로 삼기 때문이다. 없는 것은 말하지 않는다.
    """
    body = (body or "").strip()
    if not body:
        return ""
    return f"## {title}\n{body}"


def _format_profile(ctx: dict[str, Any]) -> str:
    profile = ctx.get("profile") or {}
    lines = []
    name = profile.get("preferredName") or profile.get("name")
    if name:
        lines.append(f"- 호칭: {name}")
    for key, label in (("age", "나이"), ("conditions", "질환")):
        value = profile.get(key)
        if value:
            lines.append(f"- {label}: {_join(value)}")

    # 대화 성향(conversationPreferences)과 오래 아픈 부위(chronicPainArea).
    #
    # 백엔드는 처음부터 이 필드들을 내려주고 있었는데 로봇이 읽지 않았다
    # (docs/natural-conversation/current-state-audit.md C1). 성향은 말투를
    # 고르는 재료이고, 만성 통증 부위는 "무릎이 또 아파" 같은 말을 응급이
    # 아니라 일상으로 알아듣는 재료다 — 트리아지의 CHRONIC_PAIN_PARTS 와
    # 별개로, 대화 자체도 이를 알고 있어야 §17.2(이어짐)가 산다.
    prefs = profile.get("conversationPreferences")
    if prefs:
        if isinstance(prefs, dict):
            prefs = ", ".join(f"{k} {v}" for k, v in sorted(prefs.items()))
        lines.append(f"- 대화 성향: {_join(prefs)}")
    chronic = profile.get("chronicPainArea")
    if chronic:
        lines.append(f"- 오래 아픈 부위: {_join(chronic)} (새 증상과 구분해서 듣기)")
    return "\n".join(lines)


def _format_care_records(ctx: dict[str, Any]) -> str:
    """복약·일정을 사실로 나열한다.

    정확 조회로 받은 값이므로 그대로 쓴다. 의미 검색을 거치지 않는 이유는
    "혈압약"과 "혈당약"이 임베딩상 거의 동일해서, 검색으로 가져오면 엉뚱한 약을
    말하게 되기 때문이다 (CLAUDE.md §8).
    """
    records = ctx.get("careRecords") or []
    lines = []
    for record in records:
        details = record.get("details") or {}
        rendered = ", ".join(f"{key} {value}" for key, value in sorted(details.items()))
        lines.append(f"- {record.get('recordType', '기록')}: {rendered}")
    return "\n".join(lines)


def _format_avoid_topics(ctx: dict[str, Any]) -> str:
    """회피 목록을 '금지'로 렌더링한다.  ★ 이 함수의 문구가 안전 장치다.

    사실로 주면("배우자가 작년에 돌아가셨습니다") 모델은 그것을 화제로 활용한다.
    돌아가신 배우자를 살아있는 것처럼 꺼내는 것은 이 시스템이 낼 수 있는 최악의
    실패 중 하나이므로, 정보가 아니라 명령으로 넣는다 (CLAUDE.md §16 3단계, §17.5).
    """
    profile = ctx.get("profile") or {}
    topics = profile.get("avoidTopics") or []
    if not topics:
        return ""
    listed = ", ".join(str(topic) for topic in topics)
    return (
        f"다음 주제는 **먼저 꺼내지 않습니다**: {listed}\n"
        "어르신이 직접 말씀하시면 조심스럽게 들어드리되, 먼저 언급하거나 질문하지 않습니다."
    )


def _format_today(ctx: dict[str, Any]) -> str:
    today = ctx.get("todayState")
    if not today:
        return ""
    lines = []
    taken, scheduled = today.get("medicationTakenCount"), today.get("medicationScheduledCount")
    if scheduled:
        lines.append(f"- 복약: 예정 {scheduled}회 중 {taken or 0}회 드셨습니다")
    for key, label, unit in (
        ("mealCount", "식사", "회"),
        ("waterIntakeCount", "물", "회"),
        ("outingCount", "외출", "회"),
    ):
        value = today.get(key)
        # 0 과 None 을 구분한다. None 은 '측정하지 못함'이고, 그걸 0 으로 말하면
        # 하지 않은 일을 했다고/안 했다고 단정하게 된다.
        if value is not None:
            lines.append(f"- {label}: {value}{unit}")
    return "\n".join(lines)


def _format_memories(ctx: dict[str, Any]) -> str:
    """기억에 날짜를 붙여 '기억하고 있는 것'으로 제시한다.

    날짜가 중요한 이유: 날짜가 없으면 모델이 여섯 달 전 사실을 오늘 일처럼 말한다.
    """
    memories = ctx.get("memories") or []
    lines = []
    for memory in memories:
        when = (memory.get("lastConfirmedAt") or "")[:10]
        prefix = f"({when}) " if when else ""
        lines.append(f"- {prefix}{memory.get('content', '')}")
    return "\n".join(lines)


def _format_summaries(ctx: dict[str, Any]) -> str:
    parts = []
    current = ctx.get("conversationSummary")
    if current:
        parts.append(f"- 지금까지의 대화: {current}")
    for summary in ctx.get("relevantSummaries") or []:
        when = (summary.get("periodEndedAt") or "")[:10]
        parts.append(f"- ({when}) {summary.get('content', '')}")
    return "\n".join(parts)


def _format_documents(ctx: dict[str, Any]) -> str:
    documents = ctx.get("documents") or []
    lines = []
    for document in documents:
        # 문서 본문만 넘기면 답변이 맞아도 어느 자료의 어느 버전을 썼는지 알 수
        # 없다. 백엔드 코퍼스가 제공하는 근거 식별자는 그대로 프롬프트까지 보존한다.
        metadata = []
        for key, label in (
            ("source", "출처"),
            ("version", "버전"),
            ("chunkId", "청크"),
            ("citation", "인용"),
            ("url", "URL"),
        ):
            value = document.get(key)
            if value not in (None, ""):
                metadata.append(f"{label}={_join(value)}")
        suffix = f" [{' | '.join(metadata)}]" if metadata else ""
        lines.append(
            f"- {document.get('title', '')}: {document.get('content', '')}{suffix}")
    return "\n".join(lines)


def _format_retrieval_warning(retrieval_status: dict[str, Any] | None) -> str:
    """검색 저하를 모델이 과거 사실이나 문서 근거로 단정하지 않게 바꾼다."""
    status = retrieval_status or {}
    warnings = []

    if status.get("semantic_available") is False:
        warnings.append(
            "의미 기반 기억 검색을 사용할 수 없습니다. 현재 제공된 기억만 근거로 "
            "말하고, 관련 기억이 없다고 단정하지 않습니다."
        )
    elif status.get("semantic_requested") is True and status.get("semantic_used") is False:
        reason = status.get("fallback_reason")
        detail = f"(사유: {reason})" if reason else ""
        warnings.append(
            "이번 요청은 의미 검색 대신 제한된 폴백 결과를 사용했습니다"
            f"{detail}. 과거 사실을 확신해서 말하지 않습니다."
        )

    if status.get("documents_requested") is True:
        if status.get("document_corpus_available") is False:
            warnings.append(
                "참고 문서 코퍼스를 확인할 수 없습니다. 복지·FAQ 내용을 지어내지 말고 "
                "확인이 필요하다고 말합니다."
            )
        elif (
            status.get("document_corpus_available") is True
            and status.get("document_hit_count") == 0
        ):
            warnings.append(
                "참고 문서 코퍼스는 조회했지만 관련 문서를 찾지 못했습니다. 검색하지 "
                "않은 것처럼 아는 내용으로 채우지 않습니다."
            )
    return "\n".join(f"- {warning}" for warning in warnings)


def _format_recent_messages(ctx: dict[str, Any]) -> str:
    messages = ctx.get("recentMessages") or []
    speaker = {"SENIOR": "어르신", "ROBOT": "나"}
    return "\n".join(
        f"{speaker.get(message.get('role'), message.get('role', ''))}: {message.get('content', '')}"
        for message in messages
    )


def _format_recent_phrasings(recent_phrasings: list[str] | None) -> str:
    """최근에 쓴 표현을 넘겨 반복을 막는다.

    한 줄 지시로 §17.8("같은 알림이 3일 연속 똑같지 않음")을 그대로 산다.
    """
    if not recent_phrasings:
        return ""
    listed = "\n".join(f"- {phrasing}" for phrasing in recent_phrasings)
    return f"최근에 이렇게 말했습니다. 이번에는 다르게 말합니다.\n{listed}"


def _join(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value)
    return str(value)


def build_prompt(
    ctx: dict[str, Any],
    intent: str,
    user_input: str,
    *,
    terse: bool = False,
    ctx_is_cached: bool = False,
    speech_origin: str = "",
    recent_phrasings: list[str] | None = None,
    is_medical: bool = False,
    retrieval_status: dict[str, Any] | None = None,
) -> str:
    """이번 턴의 프롬프트를 만든다. 순수 함수다.

    무엇을 하는가
        CLAUDE.md §16 의 9단계 순서로 섹션을 이어 붙인다. 비어 있는 섹션은 생략한다.

    누가 호출하는가
        graph/handlers.py 의 핸들러들. 그래프 없이 테스트에서도 직접 호출한다.

    인자
        ctx: 백엔드 문맥 조립 API 의 응답(또는 캐시본).
        intent: 어느 핸들러가 부르는지. 문서 섹션 포함 여부를 여기서 정한다.
        user_input: 어르신의 발화, 또는 능동 턴에서 이긴 제안의 seed.
        terse: quiet hours 에 인사가 통과할 때. 문장 수 제약이 줄어든다.
        ctx_is_cached: 백엔드에 닿지 못해 캐시를 썼다. 단정적 표현을 금지한다.
        speech_origin: 능동 턴이면 '왜 말하는가'. 로깅이 아니라 프롬프트에 들어간다.
        recent_phrasings: 같은 종류의 알림에서 최근에 쓴 표현.
        is_medical: context_read 가 이번 턴에 병원·약국·의약품을 조회했는가
            (state["is_medical_query"], S15P11E102-311). True 면 medical_stance.md
            를 덧붙인다.
        retrieval_status: 백엔드 검색 기능 가용성과 이번 요청의 실제 검색·폴백 결과.

    반환값
        LLM 에 그대로 넘길 문자열.

    주의사항
        - 문서는 intent == "info" 에서만 넣는다. 잡담에 문서가 들어가면 프롬프트가
          오염되고 지연 예산도 낭비된다.
        - 출력 제약은 맨 끝에 다시 넣는다. 위에만 있으면 긴 문맥에 묻힌다.
        - 지남력 질문의 '반복 횟수'는 절대 여기 들어오지 않는다. 어조에 새어나가
          열 번째 답변이 짜증스럽게 들린다. 그 정보는 T2 추세로만 간다 (CLAUDE.md §8).
        - ★ is_medical 이 왜 필요한가(실측 버그, S15P11E102-311 이후)
            system.md 의 "한 번에 한 가지만" 규칙과, 병원 조회 결과가 여러 건인
            상황이 부딪힌다. 실제로 참고 자료에 "남경의원, 누엘의원, 가덕한의원"
            세 곳이 정확히 담겨 있었는데도, 모델이 "한 가지만" 규칙과의 충돌을
            "아무것도 말하지 않는" 쪽으로 풀어서 "찾아드릴게요"로만 답한 사고가
            있었다. medical_stance.md 는 그 충돌의 해소 방법(2~3개까지는 나열
            가능, 그래도 확실하지 않은 건 되묻는다)을 명시해서 참고 자료가 있는데
            안 쓰는 실패를 막는다.
    """
    max_sentences = policy.MAX_SENTENCES_TERSE if terse else policy.MAX_SENTENCES

    blocks = [
        load_template("system.md"),
        _section("어르신 정보", _format_profile(ctx)),
        _section("복약과 일정", _format_care_records(ctx)),
        # 3단계. 제목에 '말하지 않을'을 넣은 것도 의도적이다. 모델이 섹션 제목만
        # 훑어도 이것이 정보가 아니라 금지라는 것을 알아야 한다.
        _section("말하지 않을 주제", _format_avoid_topics(ctx)),
        _section("오늘", _format_today(ctx)),
        _section("기억하고 있는 것", _format_memories(ctx)),
        _section("지난 대화", _format_summaries(ctx)),
    ]

    if intent == "info":
        blocks.append(_section("참고 자료", _format_documents(ctx)))
        if is_medical:
            # 왜 emotional_stance.md 처럼 조건부인가
            #   병원 조회가 아닌 날씨·복지제도 질문에도 이 지시를 넣으면 관련
            #   없는 지시가 프롬프트를 채운다("2~3개만 안내"는 병원 목록에나
            #   맞는 말이다). is_medical 이 이번 턴에 실제로 의료 조회가
            #   있었는지를 정확히 가리키므로 여기서만 붙인다.
            blocks.append(load_template("medical_stance.md"))

    if intent == "emotional":
        # 정서 턴에만 태도 지시를 넣는다 (S15P11E102-263).
        #
        # 왜 system.md 에 넣지 않는가
        #   system.md 는 모든 턴에 들어간다. "조언하지 마세요"를 늘 켜 두면 정보
        #   질문에도 조언을 못 하게 되고, "약은 식후에 드세요"를 못 말하게 된다.
        #   태도는 턴의 성격에 따라 바뀌어야 한다.
        #
        # 왜 파일인가
        #   프롬프트는 코드다 (CLAUDE.md §16, §23). 노드 함수 안의 문자열이면
        #   문구를 고칠 때마다 파이썬을 고치게 되고, 문구 이력이 코드 이력에 섞인다.
        blocks.append(load_template("emotional_stance.md"))

    blocks.append(_section("최근 대화", _format_recent_messages(ctx)))
    blocks.append(_section("표현 반복 피하기", _format_recent_phrasings(recent_phrasings)))
    blocks.append(_section("검색 상태 주의", _format_retrieval_warning(retrieval_status)))

    if ctx_is_cached:
        # 캐시는 낡았을 수 있다. 낡은 복약 정보를 단정적으로 말하는 것은 품질 문제가
        # 아니라 안전 문제다 (CLAUDE.md §18).
        blocks.append(_section(
            "주의",
            "지금 최신 정보를 확인할 수 없습니다. 복약·일정에 대해 단정적으로 말하지 말고, "
            "필요하면 어르신께 여쭤봅니다."))

    if speech_origin:
        blocks.append(_section("지금 말을 꺼내는 이유", speech_origin))

    current = f"어르신: {user_input}" if user_input else "(어르신의 말 없이 먼저 말을 꺼냅니다)"
    blocks.append(_section("지금 상황", current))

    # 9단계. 반드시 마지막이다.
    constraints = load_template("output_constraints.md").format(max_sentences=max_sentences)

    # 회피 목록이 '있을 때만' 마지막에 한 번 더 못박는다.
    #
    # 왜 조건부인가
    #   회피 주제가 없는데도 "위의 말하지 않을 주제를 언급하지 마세요"라고 쓰면,
    #   모델은 존재하지 않는 섹션을 찾는다. 없는 금지를 상기시키는 것은 도움이
    #   안 되고, 최악의 경우 모델이 그 문구 자체를 화제로 삼는다.
    #
    # 왜 굳이 끝에서 한 번 더인가
    #   이것이 이 프롬프트에서 가장 어겨서는 안 되는 제약이기 때문이다.
    #   모델은 마지막에 읽은 것을 더 잘 따른다.
    if _format_avoid_topics(ctx):
        constraints = f"{constraints}\n{load_template('avoid_reminder.md')}"

    blocks.append(constraints)

    return "\n\n".join(block for block in blocks if block)


# ─────────────────────────────────────────────────────────────────────────────
# 계약 주도형 프롬프트  (CLAUDE.md §12)
#
# 위의 build_prompt 와 성격이 정반대다. 저것은 자연스럽게 말하도록 문맥을 넉넉히
# 주고, 이것은 **자유를 뺏는다.** 수집 중인 단 하나의 필드, 허용되는 답변 형태,
# 그 외에는 아무것도 묻지 말라는 지시.
#
# 그래서 기억·요약·문서를 넣지 않는다. 넣으면 모델이 대화를 하려 들고, 계약이 깨진다.
# ─────────────────────────────────────────────────────────────────────────────


def build_field_question_prompt(field: str, *, fact_type: str = "", hint: str = "") -> str:
    """필드명 하나를 사람의 질문으로 바꾸는 프롬프트.

    왜 필요한가
        백엔드가 주는 것은 `"dose"` 라는 필드명이다. 그것을 소리내어 읽으면 돌봄
        로봇이 아니라 서식이 된다. 짧은 우리말 질문 하나로 바꾸는 것이 로봇의 몫이다
        (CLAUDE.md §12).

    인자
        field: 백엔드가 지정한 단 하나의 필드명.
        fact_type: 무엇에 대한 것인지 (예: "MEDICATION"). 문맥을 조금만 준다.
        hint: 사람이 읽을 수 있는 설명이 백엔드에서 왔으면 그것.

    반환값
        LLM 에 그대로 넘길 문자열. 순수 함수다.
    """
    parts = [f"필드 이름: {field}"]
    if fact_type:
        parts.append(f"무엇에 대한 것인지: {fact_type}")
    if hint:
        parts.append(f"참고: {hint}")
    return load_template("contract_question.md").format(field_hint="\n".join(parts))


def build_extraction_prompt(fields: list[str], utterance: str) -> str:
    """어르신의 말에서 필요한 필드만 뽑는 프롬프트.

    왜 생성 호출에 분류를 합치는가
        턴당 생성 호출 1회가 예산이다 (CLAUDE.md §16). 값 추출을 위해 왕복을 하나 더
        쓰면 음성 대화의 2초 예산이 무너진다. 그래서 이 호출이 그 턴의 유일한 호출이다.

    왜 '없으면 넣지 말라'를 강조하는가
        모델은 빈칸을 채우려는 성향이 있다. "한 알쯤 먹어요"에서 1 을 만들어내면,
        어르신이 말한 적 없는 복약 용량이 기록된다. 그것이 이 흐름 전체가 막으려는
        실패다. 애매하면 비우고, 비면 백엔드가 다시 묻게 한다.

    반환값
        LLM 에 그대로 넘길 문자열. 순수 함수다.
    """
    listed = "\n".join(f"- {field}" for field in fields) or "- (없음)"
    return load_template("contract_extract.md").format(fields=listed, utterance=utterance)


# ─────────────────────────────────────────────────────────────────────────────
# 사실 추출 프롬프트  (S15P11E102-255, CLAUDE.md §8)
#
# 위의 build_extraction_prompt(계약 주도형, 정해진 필드만 채운다)와 사촌 관계다.
# 금지 규칙("말하지 않은 것을 채우지 않는다", "복약 용량을 계산하지 않는다")을
# contract_extract.md 에서 그대로 물려받는다 — 같은 위험이 같은 형태로 온다.
#
# 다른 점: 여기는 정해진 필드가 없다. "무엇이 기억할 만한가"를 모델이 고른다.
# 그래서 factType 을 좁은 목록으로 제한하고, 한 번에 최대 2건으로 상한을 둔다
# (policy.EXTRACTION_MAX_FACTS_PER_UTTERANCE) — 상한 자체는 프롬프트 문구에
# 있고, jobs/ticks.extraction_flush 가 다시 한 번 파이썬으로 자른다(모델이
# 상한을 어겨도 조용히 넘어가지 않는다).
# ─────────────────────────────────────────────────────────────────────────────


def build_memory_extraction_prompt(
    preceding_robot_utterance: str,
    utterance: str,
) -> str:
    """어르신의 발화에서 기억할 만한 사실을 뽑는 프롬프트.

    누가 호출하는가
        jobs.ticks.extraction_flush. 턴 경로가 아니라 턴 밖 백그라운드 틱에서만
        불린다(CLAUDE.md §16) — 그래서 이 함수는 반응형 턴의 생성 호출 예산에
        포함되지 않는다.

    인자
        preceding_robot_utterance: 이 발화 '직전에' 로봇이 한 말. 없으면 빈
            문자열 — 그러면 프롬프트에 빈 절이 남지만, 그 자체가 "직전 맥락
            없음"을 모델에게 정직하게 알리는 값이라 굳이 숨기지 않는다.
        utterance: 어르신이 실제로 한 말. localstore.extraction 에 큐잉될 때
            이미 6자 이상으로 걸러졌다(policy.EXTRACTION_MIN_UTTERANCE_LENGTH).

    반환값
        LLM 에 그대로 넘길 문자열. 순수 함수다.
    """
    return load_template("memory_extract.md").format(
        preceding_robot_utterance=preceding_robot_utterance or "(없음)",
        utterance=utterance,
    )
