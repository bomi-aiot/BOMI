package com.ssafy.bomi.fact.repository;

import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.domain.FactSourceType;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface FactCandidateRepository extends JpaRepository<FactCandidate, UUID> {

    /**
     * 같은 어르신·같은 발화·같은 factType 으로 이미 제출된 후보가 있는지 찾는다
     * (S15P11E102-255). 로봇의 큐 flush 는 최소 한 번(at-least-once) 제출을 전제해
     * 네트워크 타임아웃 뒤 재시도가 이미 성공한 제출을 다시 보낼 수 있다 — 이 조회로
     * 같은 발화가 기억에 두 번 쌓이는 것을 막는다.
     */
    Optional<FactCandidate> findBySeniorIdAndSourceMessageIdAndFactType(
            UUID seniorId, UUID sourceMessageId, String factType);

    /** 하루 저장 건수 상한 판정에 쓴다(S15P11E102-255). 온보딩 답변 유입은 세지 않는다. */
    long countBySeniorIdAndSourceTypeAndCreatedAtAfter(
            UUID seniorId, FactSourceType sourceType, OffsetDateTime after);

    List<FactCandidate> findBySeniorIdAndStatusInOrderByCreatedAtDesc(
            UUID seniorId, Collection<FactCandidateStatus> statuses);

    long countBySeniorIdAndStatusIn(UUID seniorId, Collection<FactCandidateStatus> statuses);

    /**
     * Candidates the robot could raise in conversation, oldest first.
     *
     * <p>Oldest first so nothing starves. The caller then picks <b>exactly one</b> —
     * the ERD contract allows a single active candidate per conversation, and asking
     * about three pending facts at once breaks it (CLAUDE.md §12).</p>
     */
    List<FactCandidate> findBySeniorIdAndStatusInOrderByCreatedAtAsc(
            UUID seniorId, Collection<FactCandidateStatus> statuses);

    /**
     * "기억하지 마" — 한 대화에서 나온 미확정 후보 전부 (S15P11E102-348).
     *
     * <p>로봇은 서버가 배정한 후보 id 를 모르므로 취소의 단위는 대화다. 상태
     * 목록은 호출부(FactCandidateCancellationService)가 미확정 단계만 넘긴다.</p>
     */
    List<FactCandidate> findBySeniorIdAndConversationIdAndStatusIn(
            UUID seniorId, UUID conversationId, Collection<FactCandidateStatus> statuses);

    /**
     * The candidate produced by a given onboarding answer.
     *
     * <p>Answers are upserted, so their candidate is updated in place rather than
     * duplicated. Without this lookup, re-answering a question would leave the old
     * candidate behind and the senior would be asked about the same fact twice.</p>
     */
    Optional<FactCandidate> findByOnboardingAnswerId(UUID onboardingAnswerId);
}
