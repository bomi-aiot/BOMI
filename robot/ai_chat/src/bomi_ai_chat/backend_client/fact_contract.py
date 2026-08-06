"""추출 프롬프트의 factType 을 백엔드 계약의 필드들로 옮긴다 (S15P11E102-255).

왜 이 모듈이 따로 있는가
    추출 프롬프트(prompts/templates/memory_extract.md)는 어르신의 말을 다섯
    가지로만 분류한다 — FAMILY, HOBBY, DAILY_LIFE, HEALTH, OTHER. 사람이 읽고
    쓰기 쉬운 어휘이고, 모델에게 스무 개짜리 목록을 외우게 하는 것보다 훨씬
    안정적으로 지켜진다.

    반면 백엔드의 POST /api/v1/robot/fact-candidates 는 그것보다 훨씬 구체적인
    값을 요구한다 — targetDomain(MEMORY/CARE_RECORD), memory_type/record_type
    어휘와 같은 factType, operation, riskLevel. 서버가 이 값들로 "자동 반영해도
    되는가"를 판정하기 때문이다(FactRiskPolicy).

    이 둘을 잇는 표를 클라이언트(fact_client)나 틱(jobs/ticks) 안에 흩어 놓으면
    "모델이 뱉는 말"과 "서버가 요구하는 계약" 중 어느 쪽이 바뀌었을 때 어디를
    고쳐야 하는지 알 수 없게 된다. 그래서 변환만 하는 순수 함수 한 곳에 모은다.

주의 — 이 표가 곧 안전 판정의 입력이다
    HEALTH 를 MEMORY 로 잘못 보내면 서버는 그것을 "안전한 사실"로 보고 확인
    없이 저장한다. 복약·건강 관련 발화는 반드시 CARE_RECORD 로 가야 서버가
    보호자 확인 대기로 남긴다(CLAUDE.md §8 쓰기 경로 안전 규칙).

참고
    CLAUDE.md §8, §12 / 서버 측: FactRiskPolicy, ConversationFactIntakeService
"""

from __future__ import annotations

from typing import Any

# 추출 프롬프트의 factType -> (targetDomain, 서버 factType, riskLevel)
#
# 서버 factType 은 MEMORY 면 MemoryType enum, CARE_RECORD 면 care_record.record_type
# 어휘를 그대로 쓴다 — 서버의 FactMaterializer 가 이 문자열을 그대로 그 두 곳에
# 넣기 때문에, 알 수 없는 값을 보내면 조용히 OTHER 로 떨어진다.
#
# HEALTH 만 CARE_RECORD 로 보내는 이유
#   서버의 FactRiskPolicy 는 CARE_RECORD 중 일정류만 자동 반영하고 나머지는
#   전부 확인 대기로 남긴다. HEALTH_CONDITION 은 그 "나머지"에 속하므로,
#   "이제 아침 약 안 먹어" 류가 확인 없이 반영되는 일이 구조적으로 막힌다.
_FACT_TYPE_MAP: dict[str, tuple[str, str, str]] = {
    "FAMILY": ("MEMORY", "PERSONAL_RELATIONSHIP", "NORMAL"),
    "HOBBY": ("MEMORY", "HOBBY", "NORMAL"),
    "DAILY_LIFE": ("MEMORY", "DAILY_ROUTINE", "NORMAL"),
    "HEALTH": ("CARE_RECORD", "HEALTH_CONDITION", "SENSITIVE"),
    "OTHER": ("MEMORY", "OTHER", "NORMAL"),
}

# 모델이 목록에 없는 값을 뱉었을 때. 버리지 않고 OTHER 기억으로 남긴다 —
# 분류를 놓치는 것과 내용을 잃는 것은 다른 손해이고, 후자가 더 크다.
# (서버의 FactMaterializer.memoryType 이 알 수 없는 값을 OTHER 로 떨구는 것과
#  같은 방향의 판단이다.)
_FALLBACK = ("MEMORY", "OTHER", "NORMAL")


def to_intake_payload(
    fact: dict[str, Any],
    *,
    senior_id: str,
    conversation_id: str | None,
    source_message_id: str | None,
) -> dict[str, Any]:
    """추출된 사실 하나를 백엔드 요청 본문 하나로 바꾼다.

    무엇을 하는가
        {"factType": "FAMILY", "content": "..."} 를 서버의
        FactCandidateIntakeRequest 형태로 옮긴다.

    반환값
        seniorId/conversationId/sourceMessageId/targetDomain/factType/
        operation/proposedValue/riskLevel 을 담은 dict. 서버의 필수 필드를
        모두 채운다 — 하나라도 빠지면 bean validation 이 400 으로 거절한다.

    주의사항
        operation 은 항상 CREATE 다. 자유 대화에서 "기존 값을 고쳐라"를 판단할
        근거가 로봇에게 없다 — UPDATE/CANCEL 은 계약 대화(온보딩·재질의)나
        보호자 화면처럼 대상 행이 특정된 경로의 몫이다.
    """
    target_domain, server_fact_type, risk_level = _FACT_TYPE_MAP.get(
        str(fact.get("factType", "")).upper(), _FALLBACK
    )
    return {
        "seniorId": senior_id,
        "conversationId": conversation_id,
        "sourceMessageId": source_message_id,
        "targetDomain": target_domain,
        "factType": server_fact_type,
        "operation": "CREATE",
        "proposedValue": {"content": str(fact.get("content", ""))},
        "riskLevel": risk_level,
    }
