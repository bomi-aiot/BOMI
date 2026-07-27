package com.ssafy.bomi.conversation.repository;

import com.ssafy.bomi.conversation.domain.Conversation;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ConversationRepository extends JpaRepository<Conversation, UUID> {
}
