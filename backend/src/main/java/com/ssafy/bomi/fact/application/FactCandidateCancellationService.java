package com.ssafy.bomi.fact.application;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * "기억하지 마" — 어르신 요청으로 한 대화의 미확정 사실 후보를 닫는다 (S15P11E102-348).
 *
 * <p>왜 대화 단위인가 — 로봇은 서버가 배정한 후보 id 를 모른다. 로봇 쪽
 * ({@code extraction.forget_conversation})이 이미 대화 단위로 대기 행을 지우고
 * 있으므로, 서버 쪽 절반도 같은 단위를 받아야 요청 하나로 양쪽이 맞아떨어진다.</p>
 *
 * <p>왜 물리 삭제가 아니라 상태 전이인가 — 감사 이력을 보존하면서, 재질의·확인요청·
 * 대시보드의 열림 판정(전부 상태 화이트리스트)에서 자동으로 빠지게 한다. 지워진
 * 척하면서 어딘가에 살아 있는 것과, 닫혔다고 기록된 채 남아 있는 것은 다르다 —
 * 후자만이 "지웠다"는 약속을 검증 가능하게 만든다.</p>
 *
 * <p>무엇을 지우지 않는가 — {@code CONFIRMED}/{@code MATERIALIZED} 는 이미 사실로
 * 반영됐거나 반영 직전이라 이 경로로 닫지 않는다(그쪽 되돌리기는 보호자 화면의 몫,
 * 티켓 미결 사항). 그래서 반환값이 0 일 수 있고, 그것은 오류가 아니라 "이 대화에서
 * 아직 안 굳은 후보가 없었다"는 정직한 답이다.</p>
 */
@Service
public class FactCandidateCancellationService {

    private static final Logger log = LoggerFactory.getLogger(FactCandidateCancellationService.class);

    /** 어르신 요청 취소가 닿는 미확정 단계. FactCandidate.isCancellableBySenior 와 같은 기준. */
    private static final List<FactCandidateStatus> CANCELLABLE = List.of(
            FactCandidateStatus.CAPTURED,
            FactCandidateStatus.NEEDS_CLARIFICATION,
            FactCandidateStatus.NEEDS_CONFIRMATION,
            FactCandidateStatus.COORDINATION_REQUIRED);

    private final FactCandidateRepository factCandidateRepository;
    private final ConversationRepository conversationRepository;

    public FactCandidateCancellationService(
            FactCandidateRepository factCandidateRepository,
            ConversationRepository conversationRepository) {
        this.factCandidateRepository = factCandidateRepository;
        this.conversationRepository = conversationRepository;
    }

    /**
     * 이 대화의 미확정 후보를 전부 {@code CANCELLED_BY_SENIOR} 로 전이하고 개수를 돌려준다.
     *
     * <p>소유권 검증은 인테이크({@code ConversationFactIntakeService.intake})와 같은
     * 규칙이다 — 다른 어르신의 대화를 조용히 받아들이면 그 사람의 기억을 이
     * 어르신의 요청으로 지우게 된다. 크게, 즉시 실패한다(400).</p>
     *
     * <p>멱등하다 — 같은 요청을 다시 보내면 이미 닫힌 후보는 조회에 걸리지 않아
     * 0 을 돌려준다. 로봇의 재시도 큐가 중복 전송해도 안전하다.</p>
     */
    @Transactional
    public int cancelBySenior(UUID seniorId, UUID conversationId) {
        Conversation conversation = conversationRepository.findById(conversationId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "unknown conversationId: " + conversationId));
        if (!conversation.getSeniorId().equals(seniorId)) {
            throw new IllegalArgumentException(
                    "conversation " + conversationId + " does not belong to senior " + seniorId);
        }

        List<FactCandidate> candidates = factCandidateRepository
                .findBySeniorIdAndConversationIdAndStatusIn(seniorId, conversationId, CANCELLABLE);
        candidates.forEach(FactCandidate::cancelBySenior);

        // 발화 원문은 로그에 싣지 않는다 — 지우라는 요청을 로그로 남기는 모순.
        log.info("fact candidates cancelled by the senior: senior={} conversation={} count={}",
                seniorId, conversationId, candidates.size());
        return candidates.size();
    }
}
