package com.ssafy.bomi.fact;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.fact.domain.CoordinationStatus;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.domain.FactOperation;
import com.ssafy.bomi.fact.domain.FactSourceType;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.fact.domain.RiskLevel;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
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
class FactCandidateRepositoryTest {

    @Autowired FactCandidateRepository factCandidateRepository;
    @Autowired TestEntityManager em;

    @Test
    void capturesFromOnboardingWithJsonAndDefaults() {
        UUID onboardingAnswerId = UUID.randomUUID();
        FactCandidate candidate = FactCandidate.fromOnboardingAnswer(
            UUID.randomUUID(), onboardingAnswerId, FactTargetDomain.PROFILE, "preferred_name",
            FactOperation.CREATE, Map.of("value", "보미"), RiskLevel.NORMAL);
        FactCandidate saved = factCandidateRepository.saveAndFlush(candidate);
        em.clear();

        FactCandidate found = factCandidateRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getSourceType()).isEqualTo(FactSourceType.ONBOARDING_ANSWER);
        assertThat(found.getOnboardingAnswerId()).isEqualTo(onboardingAnswerId);
        assertThat(found.getProposedValue()).containsEntry("value", "보미");
        assertThat(found.getStatus()).isEqualTo(FactCandidateStatus.CAPTURED);
        assertThat(found.getCoordinationStatus()).isEqualTo(CoordinationStatus.NOT_REQUIRED);
        assertThat(found.getMissingFields()).isEmpty();
        assertThat(found.getClarificationCount()).isZero();
        assertThat(found.isRequiresCoordination()).isFalse();
        assertThat(found.getCreatedAt()).isNotNull();
        assertThat(found.getUpdatedAt()).isNotNull();
    }

    @Test
    void confirmsThenMaterializes() {
        FactCandidate candidate = FactCandidate.fromConversationMessage(
            UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(), FactTargetDomain.CARE_RECORD,
            "medication_dose", FactOperation.CREATE, Map.of("drug", "타이레놀"), RiskLevel.SENSITIVE);
        candidate.confirm(Map.of("drug", "타이레놀", "dose", "500mg"), UUID.randomUUID());
        UUID targetId = UUID.randomUUID();
        candidate.materialize(targetId);
        FactCandidate saved = factCandidateRepository.saveAndFlush(candidate);
        em.clear();

        FactCandidate found = factCandidateRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getSourceType()).isEqualTo(FactSourceType.CONVERSATION_MESSAGE);
        assertThat(found.getConfirmedValue()).containsEntry("dose", "500mg");
        assertThat(found.getStatus()).isEqualTo(FactCandidateStatus.MATERIALIZED);
        assertThat(found.getMaterializedTargetId()).isEqualTo(targetId);
        assertThat(found.getConfirmedAt()).isNotNull();
        assertThat(found.getMaterializedAt()).isNotNull();
    }
}
