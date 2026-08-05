package com.ssafy.bomi.conversation.repository;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import jakarta.persistence.LockModeType;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ConversationRepository extends JpaRepository<Conversation, UUID> {

    Optional<Conversation> findByScenarioId(UUID scenarioId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select c from Conversation c where c.id = :id")
    Optional<Conversation> findByIdForUpdate(@Param("id") UUID id);

    List<Conversation> findByStatusAndStartCommandIdIsNotNullAndAiStartedAtIsNullAndStartedAtLessThanEqual(
        ConversationStatus status, OffsetDateTime cutoff);

    List<Conversation> findByStatusAndStartCommandIdIsNotNullAndAiStartedAtIsNotNullAndAiStartedAtLessThanEqual(
        ConversationStatus status, OffsetDateTime cutoff);
}
