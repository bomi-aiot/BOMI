package com.ssafy.bomi.conversation;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationOutcome;
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

    @Test
    void persistsAiCommandCorrelationStartAcknowledgementAndNoResponseOutcome() {
        UUID scenarioId = UUID.randomUUID();
        OffsetDateTime requestedAt = OffsetDateTime.parse("2026-08-05T10:00:00+09:00");
        OffsetDateTime aiStartedAt = requestedAt.plusSeconds(1);
        OffsetDateTime endedAt = requestedAt.plusMinutes(1);
        Conversation conversation = Conversation.requestForScenario(
            UUID.randomUUID(), scenarioId, "cmd-ai-01", requestedAt);
        conversation.markAiStarted(aiStartedAt);
        conversation.end(ConversationOutcome.NO_RESPONSE, null, endedAt);

        Conversation saved = conversationRepository.saveAndFlush(conversation);
        em.clear();

        Conversation found = conversationRepository.findByScenarioId(scenarioId).orElseThrow();
        assertThat(found.getId()).isEqualTo(saved.getId());
        assertThat(found.getStartCommandId()).isEqualTo("cmd-ai-01");
        assertThat(found.getStartedAt()).isEqualTo(requestedAt);
        assertThat(found.getAiStartedAt()).isEqualTo(aiStartedAt);
        assertThat(found.getEndOutcome()).isEqualTo(ConversationOutcome.NO_RESPONSE);
        assertThat(found.getStatus()).isEqualTo(ConversationStatus.COMPLETED);
        assertThat(found.getEndedAt()).isEqualTo(endedAt);
    }
}
