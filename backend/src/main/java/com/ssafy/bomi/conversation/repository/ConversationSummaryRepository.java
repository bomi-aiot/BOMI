package com.ssafy.bomi.conversation.repository;

import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.embedding.domain.EmbeddingStatus;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ConversationSummaryRepository extends JpaRepository<ConversationSummary, UUID> {

    /** Recent summaries for the guardian dashboard (S15P11E102-221). */
    List<ConversationSummary> findTop5BySeniorIdOrderByGeneratedAtDesc(UUID seniorId);

    /**
     * The current summary of one conversation, if it has been summarised.
     *
     * <p>Excludes superseded rows. Regeneration writes a new row and links the old one
     * via {@code superseded_by_id}, so an unfiltered query returns every historic
     * version and the newest is not guaranteed to be last.</p>
     */
    Optional<ConversationSummary> findByConversationIdAndSupersededByIdIsNull(UUID conversationId);

    /**
     * Candidate summaries for a senior, newest period first, superseded excluded.
     *
     * <p>Returns candidates rather than a final selection on purpose. Which summaries
     * are <em>relevant</em> depends on what the senior just said, and that judgement
     * belongs in the assembly service where the query text is known. The ERD is
     * explicit that we must not attach every daily summary every turn, so the caller
     * trims what comes back.</p>
     */
    @Query("""
        SELECT s FROM ConversationSummary s
        WHERE s.seniorId = :seniorId
          AND s.supersededById IS NULL
        ORDER BY s.periodEndedAt DESC
        """)
    List<ConversationSummary> findRecentBySenior(
        @Param("seniorId") UUID seniorId, Pageable pageable);
    /**
     * Summaries whose vector needs (re)building, oldest period first (S15P11E102-218).
     *
     * <p>Paged for the same reason as {@code MemoryRepository.findNeedingEmbedding}: one row
     * is one billed embedding call, so the page size is a spending cap rather than a tuning
     * knob.</p>
     *
     * <p>Superseded summaries are skipped. A regenerated summary writes a new row and links
     * the old one, so indexing the old one pays to make a stale version findable.</p>
     */
    @Query("""
        SELECT s FROM ConversationSummary s
        WHERE s.embeddingStatus IN :statuses
          AND s.supersededById IS NULL
        ORDER BY s.periodEndedAt ASC NULLS FIRST
        """)
    List<ConversationSummary> findNeedingEmbedding(
        @Param("statuses") Collection<EmbeddingStatus> statuses, Pageable pageable);

    /** Marks synced rows from a different embedding model stale (S15P11E102-218). */
    @Modifying
    @Query("""
        UPDATE ConversationSummary s
        SET s.embeddingStatus = com.ssafy.bomi.embedding.domain.EmbeddingStatus.STALE
        WHERE s.embeddingStatus = com.ssafy.bomi.embedding.domain.EmbeddingStatus.SYNCED
          AND (s.embeddingModel IS NULL OR s.embeddingModel <> :currentModel)
        """)
    int markStaleForOtherModels(@Param("currentModel") String currentModel);
}
