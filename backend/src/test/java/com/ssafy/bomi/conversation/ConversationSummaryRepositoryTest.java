package com.ssafy.bomi.conversation;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.conversation.domain.SummaryType;
import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
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
class ConversationSummaryRepositoryTest {

    @Autowired ConversationSummaryRepository conversationSummaryRepository;
    @Autowired TestEntityManager em;

    @Test
    void persistsConversationSummaryWithGeneratedAt() {
        OffsetDateTime start = OffsetDateTime.now().minusHours(1);
        OffsetDateTime end = OffsetDateTime.now();
        ConversationSummary summary = ConversationSummary.forConversation(
            UUID.randomUUID(), UUID.randomUUID(), start, end, "짧은 안부 대화 요약", 8);
        ConversationSummary saved = conversationSummaryRepository.saveAndFlush(summary);
        em.clear();

        ConversationSummary found = conversationSummaryRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getSummaryType()).isEqualTo(SummaryType.CONVERSATION);
        assertThat(found.getConversationId()).isNotNull();
        assertThat(found.getSourceMessageCount()).isEqualTo(8);
        assertThat(found.getGeneratedAt()).isNotNull();
        assertThat(found.getSupersededById()).isNull();
    }

    @Test
    void linksSupersededByOnRegeneration() {
        OffsetDateTime start = OffsetDateTime.now().minusDays(1);
        OffsetDateTime end = OffsetDateTime.now();
        UUID seniorId = UUID.randomUUID();
        ConversationSummary regenerated = ConversationSummary.forDay(seniorId, start, end, "새 요약", 20);
        ConversationSummary newer = conversationSummaryRepository.saveAndFlush(regenerated);

        ConversationSummary old = ConversationSummary.forConversation(
            seniorId, UUID.randomUUID(), start, end, "구 요약", 20);
        old.supersededBy(newer.getId());
        ConversationSummary savedOld = conversationSummaryRepository.saveAndFlush(old);
        em.clear();

        ConversationSummary found = conversationSummaryRepository.findById(savedOld.getId()).orElseThrow();
        assertThat(found.getSummaryType()).isEqualTo(SummaryType.CONVERSATION);
        assertThat(found.getSupersededById()).isEqualTo(newer.getId());
    }
}
