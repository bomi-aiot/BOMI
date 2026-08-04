package com.ssafy.bomi.fact.web;

import com.ssafy.bomi.fact.domain.FactOperation;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.fact.domain.RiskLevel;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.Map;
import java.util.UUID;

/**
 * 로봇이 자유 대화에서 추출한 사실 후보 하나를 서버에 제출하는 요청 (S15P11E102-255).
 *
 * <p>왜 존재하는가 — 지금까지 대화 중에 나온 사실을 저장하는 통로가 전혀 없어서, "요즘
 * 손자가 자주 놀러 와요" 같은 이야기를 다음 주에 다시 물어봐도 로봇은 처음 듣는 것처럼
 * 반응했다. 이 요청은 그 통로의 입구다 — 로봇이 발화 하나에서 뽑아낸 사실 후보를 그대로
 * {@code fact_candidate} 행 하나로 옮긴다.</p>
 *
 * <p>여기서는 위험도 분류(건강·복약 어휘 거부, PROFILE/CARE_RELATIONSHIP 거절)나 동의
 * 확인을 하지 않는다 — 그것은 이 티켓의 다른 절반이 다루는 몫이고, 이 요청/서비스는 오직
 * "대화가 이 어르신 것이 맞는지" 검증한 뒤 후보를 CAPTURED 상태로 큐에 쌓는 것까지만
 * 책임진다.</p>
 *
 * @param seniorId 이 사실이 속한 어르신. conversationId 가 실제로 이 사람 것인지 서비스가
 *     검증한다 — 다른 사람의 대화 id 를 실수로 보내면 그 사람의 발화가 이 어르신의 기억으로
 *     새어 들어갈 수 있다.
 * @param conversationId 이 사실이 나온 대화. {@code fact_candidate.conversation_id}.
 * @param sourceMessageId 이 사실의 근거가 된 발화. {@code fact_candidate.source_message_id}
 *     (conversation_message 에 대한 물리 FK, ON DELETE SET NULL). 반드시 conversationId 가
 *     가리키는 대화에 속한 메시지여야 한다.
 * @param targetDomain 이 사실이 최종적으로 실체화될 대상 도메인 (MEMORY / CARE_RECORD 등).
 * @param factType 사실의 종류. {@code memory_type} 또는 {@code care_record.record_type} 과
 *     같은 어휘를 그대로 쓴다.
 * @param operation 이 후보가 제안하는 동작 (CREATE / UPDATE / CANCEL).
 * @param proposedValue 로봇이 추출한 값. 확정 전이므로 {@code confirmed_value} 가 아니라
 *     {@code proposed_value} 에 쌓인다.
 * @param riskLevel 로봇이 판단한 민감도. NORMAL 이 아니면 이후 확인 절차를 거친다(§6, §10).
 */
public record FactCandidateIntakeRequest(
        @NotNull UUID seniorId,
        @NotNull UUID conversationId,
        @NotNull UUID sourceMessageId,
        @NotNull FactTargetDomain targetDomain,
        @NotBlank String factType,
        @NotNull FactOperation operation,
        @NotEmpty Map<String, Object> proposedValue,
        @NotNull RiskLevel riskLevel) {
}
