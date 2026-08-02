package com.ssafy.bomi.memory.repository;

import com.ssafy.bomi.embedding.domain.EmbeddingStatus;
import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryLifecycleStatus;
import com.ssafy.bomi.memory.domain.MemoryVisibility;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
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
    /**
     * Memories whose vector needs (re)building, oldest first (S15P11E102-218).
     *
     * <p><b>Paged, and the caller's page size is a spending cap.</b> Every row returned here
     * becomes one billed embedding call. An unpaged query would hand the sync job the entire
     * backlog and it would spend the whole API balance in one run.</p>
     *
     * <p>Only retrievable memories are worth embedding. A {@code SUPERSEDED} or
     * {@code REJECTED} memory can never be returned by {@link #findRetrievable}, so paying to
     * index it buys nothing — and a rejected extraction is usually a mis-heard sentence,
     * which is the last thing that should be findable by meaning.</p>
     *
     * <p>Oldest first so a permanently failing row cannot starve newer ones forever: it is
     * marked {@code FAILED}, and {@code FAILED} is only retried when the caller asks for it.</p>
     */
    @Query("""
        SELECT m FROM Memory m
        WHERE m.embeddingStatus IN :statuses
          AND m.lifecycleStatus = com.ssafy.bomi.memory.domain.MemoryLifecycleStatus.ACTIVE
          AND m.verificationStatus <> com.ssafy.bomi.memory.domain.MemoryVerificationStatus.REJECTED
        ORDER BY m.firstObservedAt ASC NULLS FIRST
        """)
    List<Memory> findNeedingEmbedding(
        @Param("statuses") Collection<EmbeddingStatus> statuses, Pageable pageable);

    /**
     * Marks every synced row of one model stale (S15P11E102-218).
     *
     * <p>Used when the embedding model changes. A vector from a different model sits in a
     * different vector space, so its similarity scores are not merely worse — they are
     * meaningless, and they look like ordinary numbers.</p>
     *
     * <p>A bulk update rather than a loop because this touches every row and none of them
     * need an entity loaded. It costs no API calls; the re-embedding happens later, capped
     * per run.</p>
     */
    @Modifying
    @Query("""
        UPDATE Memory m
        SET m.embeddingStatus = com.ssafy.bomi.embedding.domain.EmbeddingStatus.STALE
        WHERE m.embeddingStatus = com.ssafy.bomi.embedding.domain.EmbeddingStatus.SYNCED
          AND (m.embeddingModel IS NULL OR m.embeddingModel <> :currentModel)
        """)
    int markStaleForOtherModels(@Param("currentModel") String currentModel);
}
