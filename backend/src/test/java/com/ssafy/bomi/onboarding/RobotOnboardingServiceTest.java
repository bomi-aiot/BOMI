package com.ssafy.bomi.onboarding;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ssafy.bomi.fact.domain.ClarificationReason;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import com.ssafy.bomi.onboarding.application.QuestionDefinition;
import com.ssafy.bomi.onboarding.application.RobotOnboardingService;
import com.ssafy.bomi.onboarding.application.RobotOnboardingService.AnswerResult;
import com.ssafy.bomi.onboarding.application.RobotOnboardingService.Outcome;
import com.ssafy.bomi.onboarding.domain.AnswerVerificationStatus;
import com.ssafy.bomi.onboarding.domain.OnboardingAnswer;
import com.ssafy.bomi.onboarding.domain.OnboardingChannel;
import com.ssafy.bomi.onboarding.domain.OnboardingSession;
import com.ssafy.bomi.onboarding.domain.OnboardingSessionStatus;
import com.ssafy.bomi.onboarding.repository.OnboardingAnswerRepository;
import com.ssafy.bomi.onboarding.repository.OnboardingSessionRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.ConsentStatus;
import com.ssafy.bomi.user.domain.OnboardingStatus;
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
 * Verifies the completion conditions of S15P11E102-227 against a real PostgreSQL.
 *
 * <p>The rules under test are the ones the robot must not be trusted to hold: one field
 * at a time, consent before health questions, sensitive values confirmed explicitly, and
 * a session that survives a channel change. Each of them is a contract violation when it
 * fails, not a bad user experience.</p>
 *
 * <p>Real PostgreSQL rather than H2 because the answer and candidate values are JSONB and
 * {@code missing_fields} is a text array — the two shapes H2 does not reproduce.</p>
 */
@SpringBootTest(
    properties = {
        "spring.flyway.enabled=true",
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.jpa.open-in-view=false",
        "bomi.mqtt.enabled=false"
    })
@Transactional
class RobotOnboardingServiceTest {

    private static EmbeddedPostgres postgres;

    @Autowired private RobotOnboardingService onboardingService;
    @Autowired private AppUserRepository appUserRepository;
    @Autowired private OnboardingSessionRepository sessionRepository;
    @Autowired private OnboardingAnswerRepository answerRepository;
    @Autowired private FactCandidateRepository candidateRepository;

    private AppUser senior;
    private final UUID robotId = UUID.randomUUID();

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

    // ── 완료 조건 1: 앱에서 시작한 세션을 로봇이 이어받는다 ───────────────────

    @Test
    void robotResumesTheSessionTheAppStarted() {
        OnboardingSession appSession = sessionRepository.save(
            OnboardingSession.startFromApp(senior.getId(), null, "onboarding-v1"));

        OnboardingSession resumed = onboardingService.startOrResume(senior.getId(), robotId);

        assertThat(resumed.getId()).isEqualTo(appSession.getId());
        // 최초 채널은 유지된다. 이어받았다고 APP 이 ROBOT 으로 바뀌면, 세션이 어디서
        // 시작됐는지에 대한 기록이 사라진다.
        assertThat(resumed.getStartedChannel()).isEqualTo(OnboardingChannel.APP);
        assertThat(sessionRepository.count()).isEqualTo(1);
    }

    @Test
    void answersFromTheRobotAreRecordedOnTheRobotChannel() {
        OnboardingSession session = sessionRepository.save(
            OnboardingSession.startFromApp(senior.getId(), null, "onboarding-v1"));
        onboardingService.startOrResume(senior.getId(), robotId);

        grant(session, "PERSONALIZATION_CONSENT");

        OnboardingAnswer answer = answerRepository
            .findBySessionIdAndQuestionCode(session.getId(), "PERSONALIZATION_CONSENT")
            .orElseThrow();
        assertThat(answer.getAnsweredChannel()).isEqualTo(OnboardingChannel.ROBOT);
    }

    @Test
    void aSecondStartDoesNotOpenASecondSession() {
        OnboardingSession first = onboardingService.startOrResume(senior.getId(), robotId);
        OnboardingSession second = onboardingService.startOrResume(senior.getId(), robotId);

        assertThat(second.getId()).isEqualTo(first.getId());
        assertThat(sessionRepository.count()).isEqualTo(1);
    }

    @Test
    void startingMarksTheUserAsInProgress() {
        onboardingService.startOrResume(senior.getId(), robotId);

        assertThat(reloadSenior().getOnboardingStatus()).isEqualTo(OnboardingStatus.IN_PROGRESS);
    }

    // ── 완료 조건 2: 동의 전에는 그에 딸린 질문이 내려가지 않는다 ─────────────

    @Test
    void theConsentQuestionComesBeforeAnythingItGates() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);

        QuestionDefinition first = next(session);

        // 계약의 첫 질문이 개인화 동의다. 그 뒤의 어떤 질문도 먼저 나올 수 없다.
        assertThat(first.code()).isEqualTo("PERSONALIZATION_CONSENT");
        assertThat(first.prerequisiteConsent()).isNull();
    }

    @Test
    void medicationIsNeverAskedBeforeHealthDataConsent() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);

        // 건강정보 동의를 뺀 나머지를 전부 처리한다.
        grant(session, "PERSONALIZATION_CONSENT");
        grant(session, "SCHEDULE_CONSENT");
        grant(session, "GUARDIAN_SHARING_CONSENT");

        // 이 시점에 남은 질문들을 끝까지 훑어도 복약 질문은 나오지 않아야 한다.
        List<String> served = serveUntilStuck(session, 12);

        assertThat(served).doesNotContain("MEDICATION", "MEDICATION_SCHEDULE");
        // 대신 건강정보 동의가 먼저 나온다.
        assertThat(served).contains("HEALTH_DATA_CONSENT");
    }

    @Test
    void grantingHealthConsentUnlocksTheMedicationQuestion() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);
        grantAllConsents(session);

        List<String> served = serveUntilStuck(session, 12);

        assertThat(served).contains("MEDICATION");
    }

    // ── 완료 조건 3: 동의를 거절하면 건너뛰고 정상 종료 ───────────────────────

    @Test
    void refusingConsentSkipsItsQuestionsAndStillCompletes() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);

        deny(session, "PERSONALIZATION_CONSENT");
        deny(session, "HEALTH_DATA_CONSENT");
        deny(session, "SCHEDULE_CONSENT");
        deny(session, "GUARDIAN_SHARING_CONSENT");

        List<String> served = serveUntilStuck(session, 12);

        // 거절한 동의에 딸린 질문은 아예 나오지 않는다. 되묻지도 않는다.
        assertThat(served).isEmpty();
        // 그리고 그것이 '실패'가 아니라 정상 종료 경로다. 어르신이 아니라고 했고,
        // 딸린 질문들은 올바르게 실행되지 않았다.
        assertThat(reload(session).getStatus()).isEqualTo(OnboardingSessionStatus.COMPLETED);
        assertThat(reloadSenior().getOnboardingStatus()).isEqualTo(OnboardingStatus.COMPLETED);
    }

    @Test
    void aRefusedConsentIsRecordedNotJustSkipped() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);
        deny(session, "HEALTH_DATA_CONSENT");

        assertThat(reloadSenior().getHealthDataConsentStatus()).isEqualTo(ConsentStatus.DENIED);
    }

    // ── 완료 조건 4: 한 필드만 재질의 ────────────────────────────────────────

    @Test
    void aMedicationMissingItsDoseIsReAskedForThatFieldOnly() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);
        grantAllConsents(session);

        AnswerResult result = onboardingService.submitAnswer(session.getId(), "MEDICATION",
            Map.of("medicationName", "혈압약", "doseUnit", "정"), true, null, null);

        assertThat(result.outcome()).isEqualTo(Outcome.NEEDS_CLARIFICATION);
        assertThat(result.missingFields()).containsExactly("dose");
        assertThat(result.clarificationReason())
            .isEqualTo(ClarificationReason.MISSING_REQUIRED_FIELD);
    }

    @Test
    void threeMissingFieldsStillProduceOneQuestionButAreAllRemembered() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);
        grantAllConsents(session);

        AnswerResult result = onboardingService.submitAnswer(session.getId(), "MEDICATION",
            Map.of(), true, null, null);

        // 로봇에게 가는 것은 하나.
        assertThat(result.missingFields()).hasSize(1);

        // ★ 저장된 것은 전부. 하나만 저장하면 그 필드를 채우는 순간 후보가 완결된 것처럼
        //   보이고, 나머지 두 필드가 빈 채로 복약 정보가 확정된다.
        FactCandidate candidate = candidateRepository.findById(result.factCandidateId())
            .orElseThrow();
        assertThat(candidate.getMissingFields())
            .containsExactlyInAnyOrder("medicationName", "dose", "doseUnit");
        assertThat(candidate.getStatus()).isEqualTo(FactCandidateStatus.NEEDS_CLARIFICATION);
    }

    @Test
    void anUnansweredQuestionKeepsComingBack() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);
        grantAllConsents(session);
        onboardingService.submitAnswer(session.getId(), "MEDICATION",
            Map.of("medicationName", "혈압약"), true, null, null);

        List<String> served = serveUntilStuck(session, 12);

        // 미확정 답변을 남긴 질문은 건너뛰어지지 않는다. 건너뛰면 반쯤 아는 복약 정보가
        // 그대로 남는다.
        assertThat(served).contains("MEDICATION");
    }

    // ── 민감 항목은 확인 전까지 확정되지 않는다 ──────────────────────────────

    @Test
    void aSensitiveValueIsNotConfirmedWithoutAnExplicitYes() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);
        grantAllConsents(session);

        AnswerResult result = onboardingService.submitAnswer(session.getId(), "MEDICATION",
            Map.of("medicationName", "혈압약", "dose", 1, "doseUnit", "정"),
            false, null, null);

        assertThat(result.outcome()).isEqualTo(Outcome.NEEDS_CONFIRMATION);
        // 전체 값을 읽어줄 수 있도록 되돌려준다.
        assertThat(result.valueToConfirm()).containsEntry("medicationName", "혈압약");

        OnboardingAnswer answer = answerRepository
            .findBySessionIdAndQuestionCode(session.getId(), "MEDICATION").orElseThrow();
        assertThat(answer.getVerificationStatus()).isEqualTo(AnswerVerificationStatus.UNVERIFIED);
        assertThat(answer.getConfirmedAt()).isNull();
    }

    @Test
    void confirmingASensitiveValueSettlesIt() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);
        grantAllConsents(session);
        Map<String, Object> value = Map.of("medicationName", "혈압약", "dose", 1, "doseUnit", "정");

        onboardingService.submitAnswer(session.getId(), "MEDICATION", value, false, null, null);
        AnswerResult confirmed = onboardingService.submitAnswer(
            session.getId(), "MEDICATION", value, true, null, null);

        assertThat(confirmed.outcome()).isEqualTo(Outcome.ACCEPTED);
        FactCandidate candidate = candidateRepository.findById(confirmed.factCandidateId())
            .orElseThrow();
        // care_record 로 가는 쓰기 경로는 아직 없다. CONFIRMED 에 머무는 것이 정직한 상태다.
        assertThat(candidate.getStatus()).isEqualTo(FactCandidateStatus.CONFIRMED);
        assertThat(confirmed.materialized()).isFalse();
    }

    @Test
    void reAnsweringUpdatesTheSameCandidateInsteadOfAddingOne() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);
        grantAllConsents(session);

        AnswerResult first = onboardingService.submitAnswer(session.getId(), "MEDICATION",
            Map.of("medicationName", "혈압약"), true, null, null);
        AnswerResult second = onboardingService.submitAnswer(session.getId(), "MEDICATION",
            Map.of("medicationName", "혈압약", "dose", 1, "doseUnit", "정"), true, null, null);

        // 후보가 둘이면 같은 사실을 두 번 묻게 된다.
        assertThat(second.factCandidateId()).isEqualTo(first.factCandidateId());
        assertThat(answerRepository.findBySessionId(session.getId())).hasSize(5);
    }

    // ── 동의는 즉시 반영된다 ────────────────────────────────────────────────

    @Test
    void aConfirmedConsentReachesAppUserImmediately() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);

        AnswerResult result = grant(session, "HEALTH_DATA_CONSENT");

        assertThat(result.materialized()).isTrue();
        assertThat(reloadSenior().getHealthDataConsentStatus()).isEqualTo(ConsentStatus.GRANTED);
        FactCandidate candidate = candidateRepository.findById(result.factCandidateId())
            .orElseThrow();
        assertThat(candidate.getStatus()).isEqualTo(FactCandidateStatus.MATERIALIZED);
    }

    @Test
    void anUnconfirmedConsentIsNotApplied() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);

        onboardingService.submitAnswer(session.getId(), "HEALTH_DATA_CONSENT",
            Map.of("consentStatus", "GRANTED"), false, null, null);

        // 어르신이 명시적으로 확인하지 않은 동의는 동의가 아니다.
        assertThat(reloadSenior().getHealthDataConsentStatus())
            .isEqualTo(ConsentStatus.NOT_REQUESTED);
    }

    // ── S15P11E102-259: 생년월일 온보딩 ──────────────────────────────────────

    @Test
    void aConfirmedBirthDateReachesAppUserImmediately() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);
        grant(session, "PERSONALIZATION_CONSENT");

        AnswerResult result = onboardingService.submitAnswer(session.getId(), "BIRTH_DATE",
            Map.of("birthDate", "1950-05-12"), true, null, null);

        // PREFERRED_NAME 과 같은 모양의 질문이다: 민감하지 않고 확인을 요구하지
        // 않으므로, 확정 즉시(그 자체가 '확인'이다) app_user 에 반영된다.
        assertThat(result.outcome()).isEqualTo(Outcome.ACCEPTED);
        assertThat(result.materialized()).isTrue();
        assertThat(reloadSenior().getBirthDate()).isEqualTo(java.time.LocalDate.of(1950, 5, 12));
        FactCandidate candidate = candidateRepository.findById(result.factCandidateId())
            .orElseThrow();
        assertThat(candidate.getStatus()).isEqualTo(FactCandidateStatus.MATERIALIZED);
    }

    @Test
    void anUnknownQuestionCodeIsRejected() {
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);

        assertThatThrownBy(() -> onboardingService.submitAnswer(session.getId(),
            "FAVOURITE_COLOUR", Map.of(), true, null, null))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("unknown question code");
    }

    // ── 209 에서 발견한 결함: 재답변이 이전 필드를 지웠다 ─────────────────────

    @Test
    void answeringOneFieldAtATimeAccumulatesInsteadOfOverwriting() {
        /*
         * ★★ 계약이 한 필드씩 되묻는 이상, 재답변은 본질적으로 '부분'이다.
         *
         * 어르신이 "혈압약" 이라고 답하면 dose 와 doseUnit 을 다시 묻는다. 그 다음
         * 턴에 로봇이 보내는 것은 {"dose": 1, "doseUnit": "정"} 뿐이다. 덮어쓰면
         * 방금 들은 약 이름이 사라지고, 서버는 그것을 다시 묻는다 — 끝나지 않는다.
         *
         * 209 의 압축 워크스루가 이 순환을 실제로 보여줬다.
         */
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);
        grantAllConsents(session);

        onboardingService.submitAnswer(session.getId(), "MEDICATION",
            Map.of("medicationName", "혈압약"), true, null, null);
        AnswerResult second = onboardingService.submitAnswer(session.getId(), "MEDICATION",
            Map.of("dose", 1, "doseUnit", "정"), true, null, null);

        assertThat(second.outcome()).isEqualTo(Outcome.ACCEPTED);

        OnboardingAnswer answer = answerRepository
            .findBySessionIdAndQuestionCode(session.getId(), "MEDICATION").orElseThrow();
        assertThat(answer.getAnswerValue())
            .containsEntry("medicationName", "혈압약")
            .containsEntry("dose", 1)
            .containsEntry("doseUnit", "정");
    }

    @Test
    void aBlankReAnswerDoesNotEraseWhatWasAlreadyKnown() {
        /*
         * 빈 값은 어르신이 알아들을 만한 말을 하지 않았을 때 도착한다. 그것이 이미
         * 아는 값을 지우면, 못 알아들은 한 턴이 데이터 손실이 된다.
         */
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);
        grantAllConsents(session);

        onboardingService.submitAnswer(session.getId(), "MEDICATION",
            Map.of("medicationName", "혈압약"), true, null, null);
        onboardingService.submitAnswer(session.getId(), "MEDICATION",
            Map.of("medicationName", "   "), true, null, null);

        OnboardingAnswer answer = answerRepository
            .findBySessionIdAndQuestionCode(session.getId(), "MEDICATION").orElseThrow();
        assertThat(answer.getAnswerValue()).containsEntry("medicationName", "혈압약");
    }

    @Test
    void theCandidateSeesTheAccumulatedValueToo() {
        /*
         * 후보의 제안값이 누적되지 않으면, 최종 확인 단계에서 어르신에게 반쪽짜리
         * 값을 복창하게 된다.
         */
        OnboardingSession session = onboardingService.startOrResume(senior.getId(), robotId);
        grantAllConsents(session);

        onboardingService.submitAnswer(session.getId(), "MEDICATION",
            Map.of("medicationName", "혈압약"), false, null, null);
        AnswerResult second = onboardingService.submitAnswer(session.getId(), "MEDICATION",
            Map.of("dose", 1, "doseUnit", "정"), false, null, null);

        assertThat(second.outcome()).isEqualTo(Outcome.NEEDS_CONFIRMATION);
        assertThat(second.valueToConfirm()).containsEntry("medicationName", "혈압약");
        FactCandidate candidate = candidateRepository.findById(second.factCandidateId())
            .orElseThrow();
        assertThat(candidate.getProposedValue()).containsEntry("medicationName", "혈압약");
    }

    // ── 헬퍼 ────────────────────────────────────────────────────────────────

    private QuestionDefinition next(OnboardingSession session) {
        return onboardingService.nextQuestion(session.getId()).orElseThrow();
    }

    /**
     * Serves questions until the flow stops offering anything new.
     *
     * <p>Answering nothing means {@code next} keeps returning the same question, so this
     * collects distinct codes and stops when one repeats. That is exactly the behaviour
     * under test elsewhere ("an unanswered question keeps coming back"), so the loop must
     * not treat it as progress.</p>
     */
    private List<String> serveUntilStuck(OnboardingSession session, int limit) {
        List<String> seen = new java.util.ArrayList<>();
        for (int i = 0; i < limit; i++) {
            Optional<QuestionDefinition> question = onboardingService.nextQuestion(session.getId());
            if (question.isEmpty() || seen.contains(question.get().code())) {
                break;
            }
            seen.add(question.get().code());
            // 답하지 않고 다음을 물으면 같은 질문이 나오므로, 진행을 위해 임시로 표시만 한다.
            markAnswered(session, question.get());
        }
        return seen;
    }

    /**
     * Marks a question settled without going through the real answer path.
     *
     * <p>Used only to walk the question order. The real path is exercised by the
     * consent and medication tests; here the point is which questions are <em>offered</em>.
     */
    private void markAnswered(OnboardingSession session, QuestionDefinition question) {
        OnboardingAnswer answer = answerRepository
            .findBySessionIdAndQuestionCode(session.getId(), question.code())
            .orElseGet(() -> answerRepository.save(OnboardingAnswer.create(
                session.getId(), question.code(), OnboardingChannel.ROBOT, senior.getId(),
                Map.of())));
        answer.confirm(AnswerVerificationStatus.AUTO_ACCEPTED, senior.getId());
        answerRepository.save(answer);
    }

    private AnswerResult grant(OnboardingSession session, String consentCode) {
        return onboardingService.submitAnswer(session.getId(), consentCode,
            Map.of("consentStatus", "GRANTED"), true, null, null);
    }

    private void deny(OnboardingSession session, String consentCode) {
        onboardingService.submitAnswer(session.getId(), consentCode,
            Map.of("consentStatus", "DENIED"), true, null, null);
    }

    private void grantAllConsents(OnboardingSession session) {
        grant(session, "PERSONALIZATION_CONSENT");
        grant(session, "HEALTH_DATA_CONSENT");
        grant(session, "SCHEDULE_CONSENT");
        grant(session, "GUARDIAN_SHARING_CONSENT");
    }

    private AppUser reloadSenior() {
        return appUserRepository.findById(senior.getId()).orElseThrow();
    }

    private OnboardingSession reload(OnboardingSession session) {
        return sessionRepository.findById(session.getId()).orElseThrow();
    }
}
