package com.ssafy.bomi.conversation.repository;

import com.ssafy.bomi.conversation.domain.ConversationMessage;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ConversationMessageRepository extends JpaRepository<ConversationMessage, UUID> {
}
