package com.ssafy.bomi.onboarding.application;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import java.io.IOException;
import java.io.InputStream;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

/**
 * The onboarding question contract, loaded once at startup.
 *
 * <p>The file lives at {@code docs/database/onboarding-question-set-v1.json} and the
 * build copies it onto the classpath (see {@code build.gradle}). There is no committed
 * duplicate: the app, the robot and this service must speak the same contract, and a
 * second copy would drift the moment someone edits one of them. If the drifting text is
 * a consent sentence, the drift is a contract violation, not a typo.</p>
 *
 * <p>The robot never reads this file. It receives {@code robotPrompt} in the API
 * response, so a wording change ships with the server.</p>
 */
@Component
public class OnboardingQuestionSet {

    private static final String RESOURCE = "onboarding/onboarding-question-set-v1.json";

    private final ObjectMapper objectMapper;

    private String version;
    /** Insertion-ordered: the ask order is the file order. */
    private Map<String, QuestionDefinition> byCode = Map.of();
    private List<QuestionDefinition> ordered = List.of();

    public OnboardingQuestionSet(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /**
     * Loads and validates the contract.
     *
     * <p>Fails startup when the file is missing or unreadable. A server that boots
     * without the question set would answer "no more questions" to every robot and
     * quietly leave every senior un-onboarded — that is worse than not booting.</p>
     */
    @PostConstruct
    void load() {
        ClassPathResource resource = new ClassPathResource(RESOURCE);
        try (InputStream in = resource.getInputStream()) {
            QuestionSetFile file = objectMapper.readValue(in, QuestionSetFile.class);
            this.version = file.version();

            Map<String, QuestionDefinition> codes = new LinkedHashMap<>();
            for (QuestionDefinition question : file.questions()) {
                if (codes.put(question.code(), question) != null) {
                    throw new IllegalStateException(
                        "duplicate question code in the onboarding contract: " + question.code());
                }
            }
            this.byCode = Map.copyOf(codes);
            this.ordered = List.copyOf(codes.values());
        } catch (IOException e) {
            throw new IllegalStateException(
                "cannot read the onboarding question set from the classpath (" + RESOURCE + "). "
                    + "The build copies it from docs/database/; check build.gradle processResources.",
                e);
        }

        validatePrerequisites();
    }

    /**
     * Every {@code prerequisiteConsent} must name a question that exists and comes earlier.
     *
     * <p>A prerequisite pointing at a later question can never be satisfied, so the
     * dependent question would be skipped forever and nobody would see an error.
     * Catching it at startup turns a silent gap into a failed deploy.</p>
     */
    private void validatePrerequisites() {
        for (int i = 0; i < ordered.size(); i++) {
            QuestionDefinition question = ordered.get(i);
            String prerequisite = question.prerequisiteConsent();
            if (prerequisite == null) {
                continue;
            }
            QuestionDefinition target = byCode.get(prerequisite);
            if (target == null) {
                throw new IllegalStateException("%s requires unknown consent %s"
                    .formatted(question.code(), prerequisite));
            }
            if (ordered.indexOf(target) > i) {
                throw new IllegalStateException(
                    "%s requires %s, which is asked later; it could never be satisfied"
                        .formatted(question.code(), prerequisite));
            }
        }
    }

    public String version() {
        return version;
    }

    /** All questions in ask order. */
    public List<QuestionDefinition> questions() {
        return ordered;
    }

    public Optional<QuestionDefinition> find(String code) {
        return Optional.ofNullable(byCode.get(code));
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    private record QuestionSetFile(String version, List<QuestionDefinition> questions) {
    }
}
