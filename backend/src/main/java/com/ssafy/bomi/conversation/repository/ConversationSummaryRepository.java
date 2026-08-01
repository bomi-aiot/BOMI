package com.ssafy.bomi.conversation.repository;

import com.ssafy.bomi.conversation.domain.ConversationSummary;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ConversationSummaryRepository extends JpaRepository<ConversationSummary, UUID> {

    List<ConversationSummary> findTop5BySeniorIdOrderByGeneratedAtDesc(UUID seniorId);
}
