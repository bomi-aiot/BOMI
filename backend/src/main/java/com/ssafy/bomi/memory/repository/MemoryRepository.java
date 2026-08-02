package com.ssafy.bomi.memory.repository;

import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryLifecycleStatus;
import com.ssafy.bomi.memory.domain.MemoryVisibility;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MemoryRepository extends JpaRepository<Memory, UUID> {

    /** Recent memories for the guardian dashboard (S15P11E102-221). */
    List<Memory> findTop5BySeniorIdAndLifecycleStatusOrderByFirstObservedAtDesc(
            UUID seniorId, MemoryLifecycleStatus lifecycleStatus);

    /** 가디언 '대화 정보/기억' 화면용 — 한 어르신의 전체 기억(삭제 제외는 서비스에서). */
    List<Memory> findBySeniorIdOrderByFirstObservedAtDesc(UUID seniorId);

    /**
     * Every memory a given requester is allowed to see for one senior.
     *
     * <p>This query <strong>is</strong> the pre-filter the MVP ERD §4 specifies, and it
     * is a privacy and safety control rather than an optimisation:</p>
     * <ul>
     *   <li>{@code seniorId} — never mix two seniors' memories.</li>
     *   <li>{@code lifecycleStatus = ACTIVE} — a superseded fact is a fact that changed.
     *       Surfacing it makes the robot state something that is no longer true.</li>
     *   <li>{@code verificationStatus != REJECTED} — a rejected extraction was wrong.
     *       Often it was wrong because ASR mis-heard, so it is exactly the material
     *       that must never reach a prompt.</li>
     *   <li>{@code visibility IN (allowed)} — decided by who is asking. The robot
     *       talking to the senior may use {@code PRIVATE}; a guardian may not.</li>
     * </ul>
     *
     * <p>Ranking is deliberately absent. Similarity, importance, and recency are
     * combined by the assembly service, because the similarity half comes from an
     * external store and cannot be expressed in this query.</p>
     *
     * <p>Note for anyone adding a guardian-facing query here: the dashboard method
     * above filters only by lifecycle. That is fine for its own use, but it is
     * <em>not</em> the retrieval pre-filter — it does not apply visibility, so it must
     * never be used to build prompt context.</p>
     */
    @Query("""
        SELECT m FROM Memory m
        WHERE m.seniorId = :seniorId
          AND m.lifecycleStatus = com.ssafy.bomi.memory.domain.MemoryLifecycleStatus.ACTIVE
          AND m.verificationStatus <> com.ssafy.bomi.memory.domain.MemoryVerificationStatus.REJECTED
          AND m.visibility IN :allowedVisibilities
        """)
    List<Memory> findRetrievable(
        @Param("seniorId") UUID seniorId,
        @Param("allowedVisibilities") Collection<MemoryVisibility> allowedVisibilities);
}
