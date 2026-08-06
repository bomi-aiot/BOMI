package com.ssafy.bomi.onboarding.web;

import com.ssafy.bomi.fact.domain.ClarificationReason;
import com.ssafy.bomi.onboarding.application.QuestionDefinition;
import com.ssafy.bomi.onboarding.application.RobotOnboardingService.AnswerResult;
import com.ssafy.bomi.onboarding.domain.OnboardingSession;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Request and response shapes for the robot onboarding endpoints.
 *
 * <p>Grouped in one file because they are one contract; splitting six records across six
 * files makes the shape of the conversation harder to see, not easier.</p>
 *
 * <p>Nothing here carries the senior's identity beyond an id. These payloads travel over
 * the same network as everything else and there is no reason for a name or a diagnosis to
 * appear in a request the robot can retry.</p>
 */
public final class RobotOnboardingDtos {

    private RobotOnboardingDtos() {
    }

    /** Start or resume. {@code robotId} is required only when a new session is created. */
    public record StartSessionRequest(@NotNull UUID seniorId, UUID robotId) {
    }

    public record SessionResponse(
        UUID sessionId,
        UUID seniorId,
        String startedChannel,
        String status,
        String currentQuestionCode,
        String questionSetVersion
    ) {
        public static SessionResponse of(OnboardingSession session, String questionSetVersion) {
            return new SessionResponse(
                session.getId(),
                session.getSeniorId(),
                session.getStartedChannel().name(),
                session.getStatus().name(),
                session.getCurrentQuestionCode(),
                questionSetVersion);
        }
    }

    /**
     * The one question to ask next.
     *
     * <p>{@code questionCode} is null when there is nothing left; {@code status} then says
     * COMPLETED. A 200 with nulls rather than a 204 so the robot always gets the session
     * status in the same shape — a 204 would make "finished" and "no body" look alike.</p>
     */
    public record NextQuestionResponse(
        UUID sessionId,
        String status,
        String questionCode,

        /** The sentence to speak. The robot does not compose its own. */
        String robotPrompt,

        /** Field names the answer must contain. Not question text. */
        List<String> requiredFields,

        /** JSON Schema for the answer. Goes into the prompt as a constraint. */
        Map<String, Object> answerSchema,

        /** True → read the whole value back and get an explicit yes before sending it. */
        boolean sensitive,
        boolean requiresConfirmation,
        String questionSetVersion
    ) {
        public static NextQuestionResponse of(UUID sessionId, String status,
            QuestionDefinition question, String version) {
            return new NextQuestionResponse(
                sessionId, status,
                question.code(), question.robotPrompt(), question.requiredFields(),
                question.answerSchema(), question.sensitive(), question.requiresConfirmation(),
                version);
        }

        public static NextQuestionResponse finished(UUID sessionId, String status, String version) {
            return new NextQuestionResponse(sessionId, status, null, null, List.of(), Map.of(),
                false, false, version);
        }
    }

    /**
     * One answer.
     *
     * @param confirmed the senior explicitly confirmed the value after hearing it read
     *     back. Silence, a topic change, "글쎄", "아마도", unclear STT, or an answer to a
     *     different question do not count — do not send true for those.
     */
    public record SubmitAnswerRequest(
        @NotNull String questionCode,
        Map<String, Object> answerValue,
        boolean confirmed,
        UUID conversationId,
        UUID sourceMessageId
    ) {
    }

    /** What the robot should do next. */
    public record SubmitAnswerResponse(
        String outcome,
        String questionCode,

        /** Exactly one field when the outcome is NEEDS_CLARIFICATION. */
        List<String> missingFields,
        ClarificationReason clarificationReason,

        /** The full value to read back when the outcome is NEEDS_CONFIRMATION. */
        Map<String, Object> valueToConfirm,

        UUID factCandidateId,

        /** True when the confirmed value reached its final source (app_user today). */
        boolean materialized
    ) {
        public static SubmitAnswerResponse of(AnswerResult result) {
            return new SubmitAnswerResponse(
                result.outcome().name(),
                result.questionCode(),
                result.missingFields(),
                result.clarificationReason(),
                result.valueToConfirm(),
                result.factCandidateId(),
                result.materialized());
        }
    }
}
