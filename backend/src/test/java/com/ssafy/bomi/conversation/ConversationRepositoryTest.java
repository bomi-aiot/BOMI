package com.ssafy.bomi.conversation;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
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
class ConversationRepositoryTest {

    @Autowired ConversationRepository conversationRepository;
    @Autowired TestEntityManager em;

    @Test
    void opensWithDefaultStatusAndStartedAt() {
        Conversation conversation = Conversation.open(UUID.randomUUID());
        Conversation saved = conversationRepository.saveAndFlush(conversation);
        em.clear();

        Conversation found = conversationRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getSeniorId()).isNotNull();
        assertThat(found.getScenarioId()).isNull();
        assertThat(found.getStatus()).isEqualTo(ConversationStatus.OPEN);
        assertThat(found.getStartedAt()).isNotNull();
        assertThat(found.getEndedAt()).isNull();
    }

    @Test
    void endsWithTerminalStatusAndRawExpiry() {
        Conversation conversation = Conversation.openForScenario(UUID.randomUUID(), UUID.randomUUID());
        conversation.scheduleRawExpiry(OffsetDateTime.now().plusDays(30));
        conversation.end(ConversationStatus.COMPLETED);
        Conversation saved = conversationRepository.saveAndFlush(conversation);
        em.clear();

        Conversation found = conversationRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getScenarioId()).isNotNull();
        assertThat(found.getStatus()).isEqualTo(ConversationStatus.COMPLETED);
        assertThat(found.getEndedAt()).isNotNull();
        assertThat(found.getRawMessagesExpiresAt()).isNotNull();
    }
}
