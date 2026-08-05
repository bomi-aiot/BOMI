package com.ssafy.bomi.conversation.repository;

import com.ssafy.bomi.conversation.domain.ConversationMessage;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ConversationMessageRepository extends JpaRepository<ConversationMessage, UUID> {

    /**
     * The tail of a conversation, newest first.
     *
     * <p>Ordered descending and paged so the query reads only the window the prompt
     * needs. Loading a whole conversation and slicing in memory would work today and
     * stop working the first time someone talks to the robot for an hour.</p>
     *
     * <p>The caller reverses the result before building the prompt: the model needs
     * chronological order, but the database needs to find the newest rows first.
     * {@code sequenceNo} breaks ties so two messages recorded in the same instant keep
     * the order they were actually said in.</p>
     */
    List<ConversationMessage> findByConversationIdOrderByOccurredAtDescSequenceNoDesc(
        UUID conversationId, Pageable pageable);

    /**
     * The highest sequence number used in a conversation, or null when it is empty.
     *
     * <p>The robot does not track sequence numbers. It would have to survive reboots and
     * stay in step with the app writing to the same conversation, and getting that wrong
     * reorders a transcript nobody would notice was wrong. The server owns the ordering;
     * the robot only says "this happened next".</p>
     */
    @Query("SELECT MAX(m.sequenceNo) FROM ConversationMessage m "
        + "WHERE m.conversationId = :conversationId")
    Integer findMaxSequenceNo(@Param("conversationId") UUID conversationId);

    /**
     * 이 대화에서 가장 최근 발화 시각, 또는 발화가 하나도 없으면 {@code null}
     * (S15P11E102-254).
     *
     * <p>{@code ConversationLifecycleService} 가 "마지막으로 무슨 일이 있었나"를
     * 판단하는 데 쓴다 — 발화가 있으면 그 시각이, 없으면 호출부가
     * {@code conversation.startedAt} 으로 대체한다. {@code findMaxSequenceNo} 와 같은
     * 이유로 서버가 계산한다: 로봇은 재시작을 버티며 정확한 순서를 유지할 필요가
     * 없다.</p>
     */
    @Query("SELECT MAX(m.occurredAt) FROM ConversationMessage m "
        + "WHERE m.conversationId = :conversationId")
    OffsetDateTime findMaxOccurredAt(@Param("conversationId") UUID conversationId);

    /**
     * 이 대화에 발화가 하나라도 있는가 (S15P11E102-254).
     *
     * <p>유휴시간 초과로 대화를 닫을 때 COMPLETED(발화 있음)와 CANCELLED(발화
     * 없음)를 가르는 데 쓴다 — 완료 조건이 명시적으로 요구하는 구분이다.</p>
     */
    boolean existsByConversationId(UUID conversationId);

    /**
     * One senior's messages within a time window.
     *
     * <p>Used by the daily aggregation. The subquery exists because {@code senior_id}
     * lives on {@code conversation}, not on the message — a message belongs to a
     * conversation, and only the conversation belongs to a person.</p>
     *
     * <p>The window is half-open ({@code >= from, < to}) so consecutive days never
     * double-count the midnight boundary.</p>
     */
    @Query("""
        SELECT m FROM ConversationMessage m
        WHERE m.conversationId IN (
            SELECT c.id FROM Conversation c WHERE c.seniorId = :seniorId)
          AND m.occurredAt >= :from AND m.occurredAt < :to
        """)
    List<ConversationMessage> findForSeniorBetween(
        @Param("seniorId") UUID seniorId,
        @Param("from") OffsetDateTime from,
        @Param("to") OffsetDateTime to);
}
