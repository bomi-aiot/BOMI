package com.ssafy.bomi.fact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ssafy.bomi.fact.application.RobotClarificationService;
import com.ssafy.bomi.fact.application.RobotClarificationService.ClarificationResult;
import com.ssafy.bomi.fact.application.RobotClarificationService.Outcome;
import com.ssafy.bomi.fact.domain.ClarificationReason;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.domain.FactOperation;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.fact.domain.RiskLevel;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.annotation.Transactional;

/**
 * Verifies the re-ask half of S15P11E102-227 against a real PostgreSQL.
 *
 * <p>The rule under test is short and easy to break: <b>one active candidate per
 * conversation</b>. It fails silently — a robot that asks about three pending facts is
 * still working, just no longer following the contract — so it is pinned here rather
 * than left to review.</p>
 */
@SpringBootTest(
    properties = {
        "spring.flyway.enabled=true",
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.jpa.open-in-view=false",
        "bomi.mqtt.enabled=false"
    })
@Transactional
class RobotClarificationServiceTest {

    private static EmbeddedPostgres postgres;

    @Autowired private RobotClarificationService clarificationService;
    @Autowired private FactCandidateRepository candidateRepository;
    @Autowired private AppUserRepository appUserRepository;

    private AppUser senior;

    @BeforeAll
    static void startPostgres() throws IOException {
        postgres = EmbeddedPostgres.start();
    }

    @AfterAll
    static void stopPostgres() throws IOException {
        if (postgres != null) {
            postgres.close();
        }
    }

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> postgres.getJdbcUrl("postgres", "postgres"));
        registry.add("spring.datasource.username", () -> "postgres");
        registry.add("spring.datasource.password", () -> "");
        registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
    }

    @BeforeEach
    void setUpSenior() {
        senior = appUserRepository.save(AppUser.create("SENIOR", "김순자", null, "순자님"));
    }

    // ── 완료 조건: 후보가 셋이어도 하나만 ────────────────────────────────────

    @Test
    void threeOpenCandidatesStillYieldExactlyOne() {
        pending("MEDICATION", RiskLevel.SENSITIVE, List.of("dose"));
        pending("DAILY_ROUTINE", RiskLevel.NORMAL, List.of("content"));
        pending("APPOINTMENT", RiskLevel.SENSITIVE, List.of("facilityName"));

        Optional<FactCandidate> active = clarificationService.activeCandidate(senior.getId());

        assertThat(active).isPresent();
        assertThat(candidateRepository.findBySeniorIdAndStatusInOrderByCreatedAtAsc(
            senior.getId(), List.of(FactCandidateStatus.NEEDS_CLARIFICATION))).hasSize(3);
    }

    @Test
    void theRiskiestOpenCandidateGoesFirst() {
        // 먼저 만든 것이 위험도가 낮다. 순서만으로 고르면 이것이 뽑힌다.
        pending("DAILY_ROUTINE", RiskLevel.NORMAL, List.of("content"));
        FactCandidate medication = pending("MEDICATION", RiskLevel.HIGH, List.of("dose"));

        Optional<FactCandidate> active = clarificationService.activeCandidate(senior.getId());

        // 복약의 모호함을 취향보다 먼저 푼다.
        assertThat(active).get().extracting(FactCandidate::getId).isEqualTo(medication.getId());
    }

    @Test
    void withinTheSameRiskTheOldestGoesFirst() {
        FactCandidate first = pending("MEDICATION", RiskLevel.SENSITIVE, List.of("dose"));
        pending("APPOINTMENT", RiskLevel.SENSITIVE, List.of("facilityName"));

        Optional<FactCandidate> active = clarificationService.activeCandidate(senior.getId());

        // 새 후보가 계속 들어와도 오래된 것이 굶지 않는다.
        assertThat(active).get().extracting(FactCandidate::getId).isEqualTo(first.getId());
    }

    @Test
    void nothingPendingIsAnOrdinaryOutcome() {
        assertThat(clarificationService.activeCandidate(senior.getId())).isEmpty();
    }

    @Test
    void settledCandidatesAreNotServed() {
        FactCandidate candidate = pending("MEDICATION", RiskLevel.SENSITIVE, List.of("dose"));
        candidate.confirm(Map.of("dose", 1), senior.getId());
        candidateRepository.save(candidate);

        assertThat(clarificationService.activeCandidate(senior.getId())).isEmpty();
    }

    // ── 완료 조건: 한 필드만 ─────────────────────────────────────────────────

    @Test
    void onlyOneFieldIsExposedEvenWhenThreeAreMissing() {
        FactCandidate candidate = pending("MEDICATION", RiskLevel.SENSITIVE,
            List.of("medicationName", "dose", "doseUnit"));

        List<String> toAsk = clarificationService.fieldToAsk(candidate);

        assertThat(toAsk).hasSize(1);
        assertThat(toAsk).containsExactly("medicationName");
        // 저장은 전부 남아 있다. 하나만 저장하면 그 필드를 채우는 순간 완결된 것처럼 보인다.
        assertThat(candidate.getMissingFields()).hasSize(3);
    }

    @Test
    void answeringOneFieldSurfacesTheNextOneNotAConfirmation() {
        FactCandidate candidate = pending("MEDICATION", RiskLevel.SENSITIVE,
            List.of("medicationName", "dose", "doseUnit"));

        ClarificationResult result = clarificationService.answer(candidate.getId(),
            Map.of("medicationName", "혈압약"), false, null, null);

        // ★ 여기서 CONFIRMED 가 나오면 dose 와 doseUnit 이 빈 채로 복약 정보가 확정된다.
        assertThat(result.outcome()).isEqualTo(Outcome.NEEDS_CLARIFICATION);
        assertThat(result.missingFields()).containsExactly("dose");
    }

    @Test
    void aFullyAnsweredSensitiveCandidateAsksForConfirmationFirst() {
        FactCandidate candidate = pending("MEDICATION", RiskLevel.SENSITIVE, List.of("dose"));

        ClarificationResult result = clarificationService.answer(candidate.getId(),
            Map.of("dose", 1), false, null, null);

        assertThat(result.outcome()).isEqualTo(Outcome.NEEDS_CONFIRMATION);
        // 전체를 읽어줄 수 있도록 되돌려준다. 값이 명확해도 민감 항목은 복창한다.
        assertThat(result.valueToConfirm()).containsEntry("dose", 1);
        assertThat(reload(candidate).getStatus())
            .isEqualTo(FactCandidateStatus.NEEDS_CONFIRMATION);
    }

    @Test
    void anExplicitYesConfirmsTheCandidate() {
        FactCandidate candidate = pending("MEDICATION", RiskLevel.SENSITIVE, List.of("dose"));

        ClarificationResult result = clarificationService.answer(candidate.getId(),
            Map.of("dose", 1), true, null, null);

        assertThat(result.outcome()).isEqualTo(Outcome.CONFIRMED);
        FactCandidate reloaded = reload(candidate);
        assertThat(reloaded.getStatus()).isEqualTo(FactCandidateStatus.CONFIRMED);
        assertThat(reloaded.getConfirmedValue()).containsEntry("dose", 1);
    }

    @Test
    void aNonSensitiveCandidateNeedsNoReadBack() {
        FactCandidate candidate = pending("DAILY_ROUTINE", RiskLevel.NORMAL, List.of("content"));

        ClarificationResult result = clarificationService.answer(candidate.getId(),
            Map.of("content", "아침에 산책하고 점심 먹고 텃밭을 봐요"), false, null, null);

        assertThat(result.outcome()).isEqualTo(Outcome.CONFIRMED);
    }

    @Test
    void blankAnswersDoNotCountAsFilled() {
        FactCandidate candidate = pending("MEDICATION", RiskLevel.SENSITIVE, List.of("dose"));

        ClarificationResult result = clarificationService.answer(candidate.getId(),
            Map.of("dose", "   "), true, null, null);

        // 어르신이 아무 말도 안 한 것과 같다. 확정하지 않고 다시 묻는다.
        assertThat(result.outcome()).isEqualTo(Outcome.NEEDS_CLARIFICATION);
        assertThat(result.missingFields()).containsExactly("dose");
    }

    @Test
    void theClarificationCountGrowsWithEachReAsk() {
        FactCandidate candidate = pending("MEDICATION", RiskLevel.SENSITIVE,
            List.of("medicationName", "dose"));
        int before = candidate.getClarificationCount();

        clarificationService.answer(candidate.getId(), Map.of("medicationName", "혈압약"),
            false, null, null);

        // 반복 재질의가 쌓이는 것은 그 자체로 신호다. 세지 않으면 보이지 않는다.
        assertThat(reload(candidate).getClarificationCount()).isGreaterThan(before);
    }

    @Test
    void answeringAnAlreadySettledCandidateIsRejected() {
        FactCandidate candidate = pending("MEDICATION", RiskLevel.SENSITIVE, List.of("dose"));
        candidate.confirm(Map.of("dose", 1), senior.getId());
        candidateRepository.save(candidate);

        assertThatThrownBy(() -> clarificationService.answer(candidate.getId(),
            Map.of("dose", 2), true, null, null))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("not awaiting an answer");
    }

    @Test
    void theReasonSurvivesTheReAsk() {
        FactCandidate candidate = pending("MEDICATION", RiskLevel.SENSITIVE,
            List.of("medicationName", "dose"), ClarificationReason.LOW_RECOGNITION_CONFIDENCE);

        ClarificationResult result = clarificationService.answer(candidate.getId(),
            Map.of("medicationName", "혈압약"), false, null, null);

        // 낮은 STT 신뢰도로 시작한 재질의는 계속 그 이유로 남는다 — 로봇이 문구를 그에
        // 맞춰 고르고, 그 문구는 오류 메시지가 아니라 평범한 재질문이어야 한다.
        assertThat(result.clarificationReason())
            .isEqualTo(ClarificationReason.LOW_RECOGNITION_CONFIDENCE);
    }

    // ── 헬퍼 ────────────────────────────────────────────────────────────────

    /**
     * A candidate waiting on the named fields.
     *
     * <p>Sourced from an onboarding answer rather than a message because
     * {@code source_message_id} is a physical FK to {@code conversation_message} — using
     * it here would mean building a conversation for every fixture, which tests the
     * conversation tables rather than this rule.</p>
     */
    private FactCandidate pending(String factType, RiskLevel risk, List<String> missing) {
        return pending(factType, risk, missing, ClarificationReason.MISSING_REQUIRED_FIELD);
    }

    private FactCandidate pending(String factType, RiskLevel risk, List<String> missing,
        ClarificationReason reason) {
        FactCandidate candidate = FactCandidate.fromOnboardingAnswer(
            senior.getId(), UUID.randomUUID(),
            FactTargetDomain.CARE_RECORD, factType, FactOperation.CREATE, Map.of(), risk);
        candidate.needsClarification(reason, missing);
        return candidateRepository.saveAndFlush(candidate);
    }

    private FactCandidate reload(FactCandidate candidate) {
        return candidateRepository.findById(candidate.getId()).orElseThrow();
    }
}
