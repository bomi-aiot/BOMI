package com.ssafy.bomi.conversation;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.domain.MessageRole;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.ActiveProfiles;

@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class ConversationMessageRepositoryTest {

    @Autowired ConversationMessageRepository conversationMessageRepository;
    @Autowired TestEntityManager em;

    @Test
    void persistsUtteranceWithRoleAndCreatedAt() {
        UUID conversationId = UUID.randomUUID();
        ConversationMessage message = ConversationMessage.of(
            conversationId, 1, MessageRole.SENIOR, "오늘 날씨가 좋네", OffsetDateTime.now());
        ConversationMessage saved = conversationMessageRepository.saveAndFlush(message);
        em.clear();

        ConversationMessage found = conversationMessageRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getConversationId()).isEqualTo(conversationId);
        assertThat(found.getSequenceNo()).isEqualTo(1);
        assertThat(found.getRole()).isEqualTo(MessageRole.SENIOR);
        assertThat(found.getContent()).isEqualTo("오늘 날씨가 좋네");
        assertThat(found.getOccurredAt()).isNotNull();
        assertThat(found.getCreatedAt()).isNotNull();
    }
}
