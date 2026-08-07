package com.ssafy.bomi.onboarding.application;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;
import java.util.Map;

/**
 * One question of the shared onboarding contract
 * ({@code onboarding-question-set-v1.json}).
 *
 * <p>The app and the robot run the same question codes, required fields, consent
 * gates and JSON schema; only the surface differs — form controls versus
 * {@code robotPrompt}. That is what lets a session started in the app be finished
 * by voice.</p>
 *
 * <p>This is a read-only projection of the contract file. Nothing here is stored:
 * the file is the source of truth and {@code onboarding_session.question_set_version}
 * records which version a session ran under.</p>
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public record QuestionDefinition(
    String code,
    boolean required,
    List<String> channels,
    String targetDomain,
    String targetType,
    List<String> requiredFields,
    boolean sensitive,
    boolean requiresConfirmation,

    /**
     * The consent that must be GRANTED before this question may be asked.
     *
     * <p>Null for the consent questions themselves. Asking a medication question
     * before health-data consent is a contract violation, so this gate is enforced
     * on the server — a robot-side rule would differ per robot version and nobody
     * would notice it being broken.</p>
     */
    String prerequisiteConsent,

    String appControl,

    /** The sentence the robot speaks. The robot does not compose its own. */
    String robotPrompt,

    String clarification,

    /** JSON Schema for the normalized answer. Passed to the robot as a prompt constraint. */
    Map<String, Object> answerSchema,

    /** Where the confirmed value finally lands (§5 of the design note). */
    Materialization materialization
) {

    /** The final resting place of a confirmed value. */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Materialization(String table, String field, String recordType) {
    }

    /** True when this question is answerable on the given channel. */
    public boolean supports(String channel) {
        return channels != null && channels.contains(channel);
    }

    /**
     * True when this question's confirmed value lands in {@code app_user}.
     *
     * <p>Used to decide what this ticket can materialize today. The other targets
     * ({@code memory}, {@code care_record}, {@code care_relationship}) need their own
     * write paths and are left as CONFIRMED candidates — see
     * {@link OnboardingMaterializer}.</p>
     */
    public boolean materializesIntoAppUser() {
        return materialization != null && "app_user".equals(materialization.table());
    }
}
