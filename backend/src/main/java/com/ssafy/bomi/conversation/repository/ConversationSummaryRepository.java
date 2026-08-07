package com.ssafy.bomi.conversation.repository;

import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.conversation.domain.SummaryType;
import com.ssafy.bomi.embedding.domain.EmbeddingStatus;
import java.time.OffsetDateTime;
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

    long countByEmbeddingStatus(EmbeddingStatus status);

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
     * 이 어르신·이 유형·이 기간의 요약이 이미 있는가 (S15P11E102 G1 일간 요약).
     *
     * <p>DAILY 요약의 멱등성 1차 방어선이자, 그보다 먼저 <b>지출</b> 방어선이다. 일간
     * 요약 창(로컬 [02:00, 06:00))은 매시간 틱이 재시도가 되도록 일부러 넓게 잡혀
     * 있어서, 같은 어르신의 같은 날에 대해 이 검사가 하루 네 번 돈다. 이 검사가 없으면
     * 그 재시도가 전부 새 LLM 호출이 되어 요금이 네 배가 되고, 요약 행도 네 개가
     * 시도된다.</p>
     *
     * <p>{@link #findByConversationIdAndSupersededByIdIsNull} 은 여기에 쓸 수 없다 —
     * DAILY 행의 {@code conversation_id} 는 null 이라 하루를 특정하지 못한다.</p>
     *
     * <p><b>{@code supersededById IS NULL} 을 조건에 붙이면 안 된다.</b> DB 제약
     * {@code uq_conversation_summary_period} 는 supersede 여부와 무관하게 4-튜플 전체에
     * 걸려 있다. 선검사가 제약보다 좁으면 "선검사는 통과했는데 INSERT 만 터지는" 경로가
     * 생기고, 그건 돈을 쓴 뒤에 버리는 최악의 순서다.</p>
     */
    boolean existsBySeniorIdAndSummaryTypeAndPeriodStartedAtAndPeriodEndedAt(
        UUID seniorId, SummaryType summaryType,
        OffsetDateTime periodStartedAt, OffsetDateTime periodEndedAt);

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
