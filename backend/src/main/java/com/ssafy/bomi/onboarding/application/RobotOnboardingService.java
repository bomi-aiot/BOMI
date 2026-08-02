package com.ssafy.bomi.onboarding.application;

import com.ssafy.bomi.fact.domain.ClarificationReason;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.domain.FactOperation;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.fact.domain.RiskLevel;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
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
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Drives the onboarding contract for the robot channel.
 *
 * <h2>Why the server owns the state machine</h2>
 *
 * <p>Every rule in the contract is one the robot cannot be trusted to hold, not because
 * the robot is untrustworthy but because the rule depends on data the robot does not
 * have, or must hold identically across robot versions:</p>
 *
 * <ul>
 *   <li><b>One field at a time</b> — a robot-side rule would differ per version and
 *       nobody would notice it being broken.</li>
 *   <li><b>Prerequisite consent</b> — consent lives in {@code app_user}. Asking a
 *       medication question before health-data consent is a contract violation.</li>
 *   <li><b>Resuming across channels</b> — the session belongs to the server, which is
 *       what lets the app start it and the voice finish it.</li>
 * </ul>
 *
 * <p>The robot's job is small on purpose: say the sentence it is given, send back what
 * it heard. Giving the model less freedom is the design intent of the whole flow
 * (CLAUDE.md §12), so a thin robot and a strict server agree rather than conflict.</p>
 *
 * <h2>The rule that makes the loop terminate</h2>
 *
 * <p>A question counts as answered only when its answer is <b>verified</b>. A sensitive
 * answer that has not been read back and confirmed stays UNVERIFIED and
 * {@link #nextQuestion} serves it again. Without that, an unconfirmed medication dose
 * would be silently skipped and never confirmed — which is the exact failure the
 * candidate flow exists to prevent.</p>
 */
@Service
public class RobotOnboardingService {

    private static final Logger log = LoggerFactory.getLogger(RobotOnboardingService.class);

    /** The robot channel is implicit: these entry points are only reachable by the robot. */
    private static final OnboardingChannel CHANNEL = OnboardingChannel.ROBOT;

    private final OnboardingQuestionSet questionSet;
    private final OnboardingSessionRepository sessionRepository;
    private final OnboardingAnswerRepository answerRepository;
    private final FactCandidateRepository candidateRepository;
    private final AppUserRepository appUserRepository;
    private final OnboardingMaterializer materializer;

    public RobotOnboardingService(
        OnboardingQuestionSet questionSet,
        OnboardingSessionRepository sessionRepository,
        OnboardingAnswerRepository answerRepository,
        FactCandidateRepository candidateRepository,
        AppUserRepository appUserRepository,
        OnboardingMaterializer materializer
    ) {
        this.questionSet = questionSet;
        this.sessionRepository = sessionRepository;
        this.answerRepository = answerRepository;
        this.candidateRepository = candidateRepository;
        this.appUserRepository = appUserRepository;
        this.materializer = materializer;
    }

    // ── 세션 ────────────────────────────────────────────────────────────────

    /**
     * Starts a session, or resumes the senior's in-progress one.
     *
     * <p>Resuming is the whole point of a server-side session. A senior who answered
     * three questions in the app must not be asked them again by voice, and
     * {@code started_channel} must keep saying APP — only the individual answers say
     * ROBOT.</p>
     *
     * <p>The session status and {@code app_user.onboarding_status} move in the same
     * transaction (design note §2). Letting them drift would leave a user marked
     * NOT_STARTED with a live session, and the app would offer to start onboarding
     * that is already half done.</p>
     */
    @Transactional
    public OnboardingSession startOrResume(UUID seniorId, UUID robotId) {
        AppUser senior = requireSenior(seniorId);

        Optional<OnboardingSession> existing = sessionRepository
            .findFirstBySeniorIdAndStatusOrderByStartedAtDesc(
                seniorId, OnboardingSessionStatus.IN_PROGRESS);
        if (existing.isPresent()) {
            log.info("resuming onboarding session {} for senior {} (started on {})",
                existing.get().getId(), seniorId, existing.get().getStartedChannel());
            return existing.get();
        }

        if (robotId == null) {
            throw new IllegalArgumentException("robotId is required to start a ROBOT session");
        }
        OnboardingSession session = OnboardingSession.startFromRobot(
            seniorId, robotId, questionSet.version());
        sessionRepository.save(session);
        senior.changeOnboardingStatus(OnboardingStatus.IN_PROGRESS);
        return session;
    }

    // ── 다음 질문 ───────────────────────────────────────────────────────────

    /**
     * The single next question, or empty when there is nothing left to ask.
     *
     * <p>Walks the contract in file order and returns the first question that is still
     * open. Four things can close a question:</p>
     *
     * <ol>
     *   <li>it already has a <b>verified</b> answer;</li>
     *   <li>its prerequisite consent was refused — the question is skipped entirely;</li>
     *   <li>it is not answerable on this channel;</li>
     *   <li>nothing is left, and the session completes.</li>
     * </ol>
     *
     * <p>A pending prerequisite does not skip the question, it <b>reorders</b> it: the
     * consent question is served first. The robot never decides that order — if it did,
     * a robot that got the order wrong would collect health data without consent and the
     * violation would live in a device, not in a reviewable server rule.</p>
     */
    @Transactional
    public Optional<QuestionDefinition> nextQuestion(UUID sessionId) {
        OnboardingSession session = requireSession(sessionId);
        if (session.getStatus() != OnboardingSessionStatus.IN_PROGRESS) {
            return Optional.empty();
        }
        AppUser senior = requireSenior(session.getSeniorId());
        Map<String, OnboardingAnswer> answers = answersByCode(sessionId);

        for (QuestionDefinition question : questionSet.questions()) {
            if (!question.supports(CHANNEL.name())) {
                continue;
            }
            if (isSettled(answers.get(question.code()))) {
                continue;
            }

            Gate gate = gateFor(question, senior);
            if (gate == Gate.REFUSED) {
                // 동의를 거절했다. 이 질문은 물어서는 안 되고, 되물어서도 안 된다.
                continue;
            }
            if (gate == Gate.PENDING) {
                // 선행 동의가 아직 없다. 그 동의 질문이 먼저다.
                QuestionDefinition consent = questionSet.find(question.prerequisiteConsent())
                    .orElseThrow();
                if (!isSettled(answers.get(consent.code()))) {
                    session.moveToQuestion(consent.code());
                    return Optional.of(consent);
                }
                // 동의 질문에는 답했는데 아직 GRANTED 가 아니다(확인 대기 등). 넘어간다.
                continue;
            }

            session.moveToQuestion(question.code());
            return Optional.of(question);
        }

        complete(session, senior);
        return Optional.empty();
    }

    /**
     * Ends the session.
     *
     * <p>Reaching here means every question is either answered or legitimately skipped —
     * "필수 질문 또는 허용된 동의 거절·건너뛰기 경로 뒤만 완료한다" (design note §2). A refused
     * consent is a valid path to completion, not a failure: the senior said no and the
     * dependent questions correctly never ran.</p>
     */
    private void complete(OnboardingSession session, AppUser senior) {
        session.moveToQuestion(null);
        session.complete();
        senior.changeOnboardingStatus(OnboardingStatus.COMPLETED);
        log.info("onboarding session {} completed for senior {}",
            session.getId(), session.getSeniorId());
    }

    private enum Gate { OPEN, PENDING, REFUSED }

    /**
     * Whether this question's prerequisite consent allows asking it.
     *
     * <p>Reads the consent from {@code app_user}, not from the answer rows, because
     * {@code app_user} is where consent finally lives and where every other part of the
     * system reads it. A consent that was answered but not yet materialized is not a
     * consent.</p>
     */
    private Gate gateFor(QuestionDefinition question, AppUser senior) {
        String prerequisite = question.prerequisiteConsent();
        if (prerequisite == null) {
            return Gate.OPEN;
        }

        ConsentStatus status = consentValue(prerequisite, senior);
        return switch (status) {
            case GRANTED -> Gate.OPEN;
            case DENIED, REVOKED -> Gate.REFUSED;
            case NOT_REQUESTED -> Gate.PENDING;
        };
    }

    private ConsentStatus consentValue(String consentQuestionCode, AppUser senior) {
        return switch (consentQuestionCode) {
            case "PERSONALIZATION_CONSENT" -> senior.getPersonalizationConsentStatus();
            case "HEALTH_DATA_CONSENT" -> senior.getHealthDataConsentStatus();
            case "SCHEDULE_CONSENT" -> senior.getScheduleConsentStatus();
            case "GUARDIAN_SHARING_CONSENT" -> senior.getGuardianSharingConsentStatus();
            // 계약에 새 동의가 추가됐는데 여기 분기를 안 만든 경우다. 조용히 OPEN 을 주면
            // 동의 없이 민감 질문이 나가므로 요란하게 실패한다.
            default -> throw new IllegalStateException(
                "no consent projection for question " + consentQuestionCode);
        };
    }

    /** Answered and verified. An unverified sensitive answer is not settled — it is re-asked. */
    private boolean isSettled(OnboardingAnswer answer) {
        if (answer == null) {
            return false;
        }
        AnswerVerificationStatus status = answer.getVerificationStatus();
        return status == AnswerVerificationStatus.AUTO_ACCEPTED
            || status == AnswerVerificationStatus.USER_CONFIRMED
            || status == AnswerVerificationStatus.GUARDIAN_CONFIRMED;
    }

    // ── 답변 제출 ───────────────────────────────────────────────────────────

    /** What the robot should do next with this question. */
    public enum Outcome {
        /** Accepted and, where possible, written to its final source. Move on. */
        ACCEPTED,
        /** One field is missing or unclear. Ask only that one. */
        NEEDS_CLARIFICATION,
        /** Complete but sensitive. Read the whole value back and get an explicit yes. */
        NEEDS_CONFIRMATION
    }

    /** The result of submitting one answer. */
    public record AnswerResult(
        Outcome outcome,
        String questionCode,
        List<String> missingFields,
        ClarificationReason clarificationReason,
        Map<String, Object> valueToConfirm,
        UUID factCandidateId,
        boolean materialized
    ) {
    }

    /**
     * Records one answer and decides what happens next.
     *
     * <p>Follows the design note's sequence: upsert the answer, create or update its
     * candidate, then re-ask / confirm / materialize. Only a confirmed value is ever
     * written to a final source.</p>
     *
     * @param confirmed the robot reports that the senior explicitly confirmed the value
     *     after hearing it read back. Silence, a topic change, "글쎄", "아마도", unclear
     *     STT, or an answer to a <b>different</b> question do not count — the robot must
     *     not send true for those. The server checks what it can: a sensitive value
     *     without this flag stays UNVERIFIED and comes back.
     */
    @Transactional
    public AnswerResult submitAnswer(UUID sessionId, String questionCode,
        Map<String, Object> answerValue, boolean confirmed,
        UUID conversationId, UUID sourceMessageId) {

        OnboardingSession session = requireSession(sessionId);
        AppUser senior = requireSenior(session.getSeniorId());
        QuestionDefinition question = questionSet.find(questionCode)
            .orElseThrow(() -> new IllegalArgumentException("unknown question code " + questionCode));
        if (!question.supports(CHANNEL.name())) {
            throw new IllegalArgumentException(
                questionCode + " is not answerable on the ROBOT channel");
        }

        Map<String, Object> value = answerValue == null ? Map.of() : answerValue;
        OnboardingAnswer answer = upsertAnswer(session, question, value, conversationId,
            sourceMessageId);
        FactCandidate candidate = upsertCandidate(session, question, answer, value);

        List<String> missing = missingFields(question, value);
        if (!missing.isEmpty()) {
            // 저장은 전부, 질문은 하나.
            //
            // 저장까지 하나만 하면 그 한 필드를 채우는 순간 후보가 완결된 것처럼 보이고,
            // 나머지 두 필드가 빈 채로 복약 정보가 확정된다. 반대로 세 개를 한꺼번에 물으면
            // 계약이 깨지고 음성으로는 아무것도 기억되지 않는다.
            candidate.needsClarification(ClarificationReason.MISSING_REQUIRED_FIELD, missing);
            answer.markUnverified();
            return new AnswerResult(Outcome.NEEDS_CLARIFICATION, questionCode,
                List.of(missing.get(0)),
                ClarificationReason.MISSING_REQUIRED_FIELD, null, candidate.getId(), false);
        }

        if (question.requiresConfirmation() && !confirmed) {
            // 값이 명확해도 민감 항목은 전체를 읽어주고 명시적 확인을 받는다.
            candidate.needsConfirmation();
            answer.markUnverified();
            return new AnswerResult(Outcome.NEEDS_CONFIRMATION, questionCode, List.of(),
                ClarificationReason.SENSITIVE_INFORMATION_CONFIRMATION, value,
                candidate.getId(), false);
        }

        AnswerVerificationStatus verification = question.requiresConfirmation()
            ? AnswerVerificationStatus.USER_CONFIRMED
            : AnswerVerificationStatus.AUTO_ACCEPTED;
        answer.confirm(verification, senior.getId());
        candidate.confirm(value, senior.getId());

        boolean materialized = materializer.materialize(question, senior, value);
        if (materialized) {
            candidate.materialize(senior.getId());
        }

        return new AnswerResult(Outcome.ACCEPTED, questionCode, List.of(), null, null,
            candidate.getId(), materialized);
    }

    /**
     * Creates the answer row, or overwrites the previous attempt.
     *
     * <p>Upsert rather than append. Two rows for the same question would make "the
     * current answer" depend on read order, and re-asking a field is normal here.</p>
     */
    private OnboardingAnswer upsertAnswer(OnboardingSession session, QuestionDefinition question,
        Map<String, Object> value, UUID conversationId, UUID sourceMessageId) {

        OnboardingAnswer answer = answerRepository
            .findBySessionIdAndQuestionCode(session.getId(), question.code())
            .orElseGet(() -> answerRepository.save(OnboardingAnswer.create(
                session.getId(), question.code(), CHANNEL, session.getSeniorId(), value)));

        answer.updateAnswerValue(value);
        // 로봇 답변은 근거 대화·메시지를 연결한다. 앱 답변에는 없을 수 있다(설계 노트 §1).
        answer.linkEvidence(conversationId, sourceMessageId);
        return answer;
    }

    /**
     * Creates the candidate for this answer, or reuses it.
     *
     * <p>Reused rather than duplicated: re-answering must not leave the previous
     * candidate behind, or the senior gets asked about the same fact twice — once from
     * the stale candidate and once from the new one.</p>
     */
    private FactCandidate upsertCandidate(OnboardingSession session, QuestionDefinition question,
        OnboardingAnswer answer, Map<String, Object> value) {

        Optional<FactCandidate> existing = candidateRepository
            .findByOnboardingAnswerId(answer.getId());
        if (existing.isPresent()) {
            FactCandidate candidate = existing.get();
            candidate.updateProposedValue(value);
            return candidate;
        }

        FactCandidate candidate = FactCandidate.fromOnboardingAnswer(
            session.getSeniorId(),
            answer.getId(),
            FactTargetDomain.valueOf(question.targetDomain()),
            question.targetType(),
            FactOperation.CREATE,
            value,
            question.sensitive() ? RiskLevel.SENSITIVE : RiskLevel.NORMAL);
        candidate.initiatedBy(session.getSeniorId());
        return candidateRepository.save(candidate);
    }

    /**
     * Required fields with no usable value, in contract order.
     *
     * <p>Order matters: it decides which single field gets re-asked, and the contract's
     * order is the one a person would ask in ("what medicine, how much, what unit").</p>
     */
    private List<String> missingFields(QuestionDefinition question, Map<String, Object> value) {
        List<String> missing = new ArrayList<>();
        for (String field : question.requiredFields()) {
            Object raw = value.get(field);
            if (raw == null || raw.toString().isBlank()) {
                missing.add(field);
            }
        }
        return missing;
    }

    // ── 조회 헬퍼 ───────────────────────────────────────────────────────────

    private Map<String, OnboardingAnswer> answersByCode(UUID sessionId) {
        Map<String, OnboardingAnswer> byCode = new HashMap<>();
        for (OnboardingAnswer answer : answerRepository.findBySessionId(sessionId)) {
            byCode.put(answer.getQuestionCode(), answer);
        }
        return byCode;
    }

    private OnboardingSession requireSession(UUID sessionId) {
        return sessionRepository.findById(sessionId)
            .orElseThrow(() -> new IllegalArgumentException("no onboarding session " + sessionId));
    }

    private AppUser requireSenior(UUID seniorId) {
        return appUserRepository.findById(seniorId)
            .orElseThrow(() -> new IllegalArgumentException("no senior " + seniorId));
    }

    /** Exposed so the controller can echo the contract version the robot is running. */
    public String questionSetVersion() {
        return questionSet.version();
    }

    /** True when this candidate status still keeps a question open. */
    public static boolean isOpen(FactCandidateStatus status) {
        return status == FactCandidateStatus.NEEDS_CLARIFICATION
            || status == FactCandidateStatus.NEEDS_CONFIRMATION;
    }
}
