package com.ssafy.bomi.onboarding;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.onboarding.domain.AnswerVerificationStatus;
import com.ssafy.bomi.onboarding.domain.OnboardingAnswer;
import com.ssafy.bomi.onboarding.domain.OnboardingChannel;
import com.ssafy.bomi.onboarding.repository.OnboardingAnswerRepository;
import java.util.Map;
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
class OnboardingAnswerRepositoryTest {

    @Autowired OnboardingAnswerRepository onboardingAnswerRepository;
    @Autowired TestEntityManager em;

    @Test
    void persistsJsonAnswerAndDefaultVerification() {
        OnboardingAnswer answer = OnboardingAnswer.create(
            UUID.randomUUID(), "PREFERRED_NAME", OnboardingChannel.APP, UUID.randomUUID(),
            Map.of("value", "보미"));
        OnboardingAnswer saved = onboardingAnswerRepository.saveAndFlush(answer);
        em.clear();

        OnboardingAnswer found = onboardingAnswerRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getQuestionCode()).isEqualTo("PREFERRED_NAME");
        assertThat(found.getAnsweredChannel()).isEqualTo(OnboardingChannel.APP);
        assertThat(found.getAnswerValue()).containsEntry("value", "보미");
        assertThat(found.getVerificationStatus()).isEqualTo(AnswerVerificationStatus.UNVERIFIED);
        assertThat(found.getAnsweredAt()).isNotNull();
    }

    @Test
    void linksRobotEvidenceAndConfirms() {
        UUID conversationId = UUID.randomUUID();
        UUID messageId = UUID.randomUUID();
        UUID confirmerId = UUID.randomUUID();
        OnboardingAnswer answer = OnboardingAnswer.create(
            UUID.randomUUID(), "HOBBY", OnboardingChannel.ROBOT, UUID.randomUUID(), Map.of("value", "산책"));
        answer.linkEvidence(conversationId, messageId);
        answer.confirm(AnswerVerificationStatus.USER_CONFIRMED, confirmerId);
        OnboardingAnswer saved = onboardingAnswerRepository.saveAndFlush(answer);
        em.clear();

        OnboardingAnswer found = onboardingAnswerRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getSourceConversationId()).isEqualTo(conversationId);
        assertThat(found.getSourceMessageId()).isEqualTo(messageId);
        assertThat(found.getVerificationStatus()).isEqualTo(AnswerVerificationStatus.USER_CONFIRMED);
        assertThat(found.getConfirmedByUserId()).isEqualTo(confirmerId);
        assertThat(found.getConfirmedAt()).isNotNull();
    }
}
