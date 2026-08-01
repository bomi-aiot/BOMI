package com.ssafy.bomi.conversation.repository;

import com.ssafy.bomi.conversation.domain.ConversationMessage;
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

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
}
