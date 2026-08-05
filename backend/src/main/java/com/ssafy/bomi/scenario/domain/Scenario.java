package com.ssafy.bomi.scenario.domain;

import com.ssafy.bomi.conversation.domain.ConversationIntent;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.annotations.UpdateTimestamp;
import org.hibernate.type.SqlTypes;

/**
 * Scenario triggered for a senior/robot (maps table {@code scenario}).
 *
 * <p>Aggregate root representing <b>one run of a robot behavior flow</b>.
 * {@code externalEventId} is the MQTT event that triggered it; {@code seniorId}
 * and {@code robotId} are raw {@link UUID} logical references. Although
 * {@code conversation} references {@code scenario}, this entity holds no
 * back-reference to conversations.</p>
 *
 * <p>{@code finalStatus} keeps the <b>current</b> coarse status throughout the
 * flow (the column name is kept for compatibility; see {@link ScenarioStatus}).
 * Only allowed transitions succeed — see {@link #ALLOWED_TRANSITIONS_BY_TYPE} and
 * {@link #transitionTo(ScenarioStatus)}.</p>
 *
 * <p>Conversation-driven types keep the existing homecoming path. The wake-word
 * call has its own short path ({@code RECEIVED -> NAVIGATING -> COMPLETED}) so an
 * arrival can never accidentally start an AI conversation or a return command.</p>
 */
@Entity
@Table(name = "scenario")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Scenario {

    /** Scenario type → from-status → allowed next statuses. */
    private static final Map<ScenarioType, Map<ScenarioStatus, Set<ScenarioStatus>>>
        ALLOWED_TRANSITIONS_BY_TYPE = buildAllowedTransitionsByType();

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "senior_id", nullable = false)
    private UUID seniorId;

    @Column(name = "robot_id", nullable = false)
    private UUID robotId;

    @Column(name = "external_event_id", length = 255)
    private String externalEventId;

    @Enumerated(EnumType.STRING)
    @Column(name = "scenario_type", nullable = false, length = 50)
    private ScenarioType scenarioType;

    /** Current coarse status (column kept as {@code final_status}); starts at RECEIVED. */
    @Enumerated(EnumType.STRING)
    @Column(name = "final_status", nullable = false, length = 50)
    private ScenarioStatus finalStatus = ScenarioStatus.RECEIVED;

    /**
     * AI conversation input captured before navigation. Keeping this in the scenario
     * preserves the original greeting and trigger snapshot across a backend restart.
     */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "conversation_request")
    private Map<String, Object> conversationRequest;

    /** The only NAVIGATE command whose result may advance this scenario. */
    @Column(name = "active_navigation_command_id", length = 64)
    private String activeNavigationCommandId;

    @Column(name = "active_navigation_target", length = 30)
    private String activeNavigationTarget;

    /** Minimal structured trigger metadata; never contains raw audio or full STT text. */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "trigger_context")
    private Map<String, Object> triggerContext;

    /** Terminal Robot result code used by scenario history and diagnostics. */
    @Column(name = "completion_result_code", length = 50)
    private String completionResultCode;

    /** Stable terminal reason code; human prose belongs in logs, not this field. */
    @Column(name = "completion_reason_code", length = 100)
    private String completionReasonCode;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    /**
     * 마지막 상태 전이 시각. 시나리오는 상태가 바뀔 때만 저장되므로 터미널 상태
     * 행에서는 "끝난 시각"을 뜻한다. {@code ScenarioStartGuard}의 쿨다운 판정이 읽는다.
     */
    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    private Scenario(UUID seniorId, UUID robotId, ScenarioType scenarioType, String externalEventId) {
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.robotId = requireNonNull(robotId, "robotId");
        this.scenarioType = requireNonNull(scenarioType, "scenarioType");
        this.externalEventId = externalEventId;
        this.finalStatus = ScenarioStatus.RECEIVED;
    }

    public static Scenario create(UUID seniorId, UUID robotId, ScenarioType scenarioType) {
        return new Scenario(seniorId, robotId, scenarioType, null);
    }

    public static Scenario create(
        UUID seniorId, UUID robotId, ScenarioType scenarioType, String externalEventId) {
        return new Scenario(seniorId, robotId, scenarioType, externalEventId);
    }

    public void linkExternalEvent(String externalEventId) {
        this.externalEventId = externalEventId;
    }

    /** Stores the exact AI conversation request that must be used after navigation. */
    public void prepareConversation(
        ConversationIntent intent,
        String text,
        Map<String, Object> triggerContext
    ) {
        PreparedConversation prepared = new PreparedConversation(intent, text, triggerContext);
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("intent", prepared.intent().name());
        request.put("text", prepared.text());
        request.put("triggerContext", new LinkedHashMap<>(prepared.triggerContext()));
        this.conversationRequest = request;
    }

    /** Returns a typed, defensive view of the conversation request stored as JSON. */
    public PreparedConversation requirePreparedConversation() {
        if (conversationRequest == null) {
            throw new IllegalStateException("Scenario has no prepared conversation: " + id);
        }
        Object intentValue = conversationRequest.get("intent");
        Object textValue = conversationRequest.get("text");
        Object contextValue = conversationRequest.get("triggerContext");
        if (!(intentValue instanceof String intentText) || !(textValue instanceof String text)) {
            throw new IllegalStateException("Scenario conversation request is malformed: " + id);
        }
        Map<String, Object> context = stringObjectMap(contextValue);
        try {
            return new PreparedConversation(ConversationIntent.valueOf(intentText), text, context);
        } catch (IllegalArgumentException ex) {
            throw new IllegalStateException("Scenario conversation request is malformed: " + id, ex);
        }
    }

    public Map<String, Object> getConversationRequest() {
        return conversationRequest == null ? null : Map.copyOf(conversationRequest);
    }

    /** Stores the smallest useful trigger snapshot for non-conversation scenarios. */
    public void recordTriggerContext(Map<String, Object> context) {
        if (context == null) {
            this.triggerContext = Map.of();
            return;
        }
        this.triggerContext = new LinkedHashMap<>(context);
    }

    public Map<String, Object> getTriggerContext() {
        return triggerContext == null ? null : Map.copyOf(triggerContext);
    }

    /** Stores command correlation before the after-commit MQTT publish is registered. */
    public void expectNavigationResult(String commandId, String target) {
        if (activeNavigationCommandId != null) {
            throw new IllegalStateException(
                "Scenario already has an active navigation command: " + id);
        }
        this.activeNavigationCommandId = requireText(commandId, "commandId", 64);
        this.activeNavigationTarget = requireText(target, "target", 30);
    }

    /** Clears the correlation only after the result was checked by the orchestrator. */
    public void clearExpectedNavigationResult() {
        if (activeNavigationCommandId == null || activeNavigationTarget == null) {
            throw new IllegalStateException(
                "Scenario has no active navigation command: " + id);
        }
        this.activeNavigationCommandId = null;
        this.activeNavigationTarget = null;
    }

    // --- State machine -------------------------------------------------------

    /**
     * Moves to {@code next} if the transition is allowed by this scenario type,
     * otherwise throws {@link IllegalStateException}. This is the single
     * enforcement point; the intent methods below delegate here.
     */
    public void transitionTo(ScenarioStatus next) {
        requireNonNull(next, "next");
        Map<ScenarioStatus, Set<ScenarioStatus>> transitions =
            ALLOWED_TRANSITIONS_BY_TYPE.getOrDefault(
                scenarioType, ALLOWED_TRANSITIONS_BY_TYPE.get(ScenarioType.HOMECOMING));
        Set<ScenarioStatus> allowed = transitions.getOrDefault(finalStatus, Set.of());
        if (!allowed.contains(next)) {
            throw new IllegalStateException(
                "Illegal scenario transition: " + finalStatus + " -> " + next);
        }
        this.finalStatus = next;
    }

    // Intent methods for the HOMECOMING happy path (readability for orchestration).
    public void beginMovingToEntrance() {
        transitionTo(ScenarioStatus.MOVING_TO_ENTRANCE);
    }

    /** Starts the wake-word call's one-way movement to the senior. */
    public void beginNavigation() {
        transitionTo(ScenarioStatus.NAVIGATING);
    }

    public void checkInteraction() {
        transitionTo(ScenarioStatus.CHECKING_INTERACTION);
    }

    public void beginConversation() {
        transitionTo(ScenarioStatus.CONVERSING);
    }

    public void decideReturn() {
        transitionTo(ScenarioStatus.RETURN_DECISION);
    }

    public void returnToDefault() {
        transitionTo(ScenarioStatus.RETURNING_TO_DEFAULT);
    }

    public void complete() {
        complete(null, null);
    }

    public void complete(String resultCode, String reasonCode) {
        finish(ScenarioStatus.COMPLETED, resultCode, reasonCode);
    }

    // Terminal exits available from any active state.
    public void fail() {
        fail(null, null);
    }

    public void fail(String resultCode, String reasonCode) {
        finish(ScenarioStatus.FAILED, resultCode, reasonCode);
    }

    public void cancel() {
        cancel(null, null);
    }

    public void cancel(String resultCode, String reasonCode) {
        finish(ScenarioStatus.CANCELLED, resultCode, reasonCode);
    }

    public void timeOut() {
        timeOut(null, null);
    }

    public void timeOut(String resultCode, String reasonCode) {
        finish(ScenarioStatus.TIMED_OUT, resultCode, reasonCode);
    }

    public boolean isTerminated() {
        return finalStatus.isTerminal();
    }

    private static Map<ScenarioType, Map<ScenarioStatus, Set<ScenarioStatus>>>
        buildAllowedTransitionsByType() {
        Map<ScenarioStatus, Set<ScenarioStatus>> conversation =
            buildConversationTransitions();
        Map<ScenarioStatus, Set<ScenarioStatus>> wakeWord =
            buildWakeWordCallTransitions();
        Map<ScenarioType, Map<ScenarioStatus, Set<ScenarioStatus>>> byType =
            new EnumMap<>(ScenarioType.class);
        for (ScenarioType type : ScenarioType.values()) {
            byType.put(type, conversation);
        }
        byType.put(ScenarioType.WAKE_WORD_CALL, wakeWord);
        return Map.copyOf(byType);
    }

    private static Map<ScenarioStatus, Set<ScenarioStatus>> buildConversationTransitions() {
        // Terminal statuses reachable from every active (non-terminal) status.
        Set<ScenarioStatus> terminals = EnumSet.of(
            ScenarioStatus.FAILED, ScenarioStatus.CANCELLED, ScenarioStatus.TIMED_OUT);

        Map<ScenarioStatus, Set<ScenarioStatus>> map = new EnumMap<>(ScenarioStatus.class);
        // HOMECOMING happy path (linear).
        putTransition(map, ScenarioStatus.RECEIVED, ScenarioStatus.MOVING_TO_ENTRANCE, terminals);
        putTransition(map, ScenarioStatus.MOVING_TO_ENTRANCE, ScenarioStatus.CHECKING_INTERACTION, terminals);
        putTransition(map, ScenarioStatus.CHECKING_INTERACTION, ScenarioStatus.CONVERSING, terminals);
        map.get(ScenarioStatus.CHECKING_INTERACTION).add(ScenarioStatus.RETURN_DECISION);
        putTransition(map, ScenarioStatus.CONVERSING, ScenarioStatus.RETURN_DECISION, terminals);
        putTransition(map, ScenarioStatus.RETURN_DECISION, ScenarioStatus.RETURNING_TO_DEFAULT, terminals);
        putTransition(map, ScenarioStatus.RETURNING_TO_DEFAULT, ScenarioStatus.COMPLETED, terminals);
        // Terminal statuses admit no outgoing transitions.
        map.put(ScenarioStatus.COMPLETED, Set.of());
        map.put(ScenarioStatus.FAILED, Set.of());
        map.put(ScenarioStatus.CANCELLED, Set.of());
        map.put(ScenarioStatus.TIMED_OUT, Set.of());
        return map;
    }

    private static Map<ScenarioStatus, Set<ScenarioStatus>> buildWakeWordCallTransitions() {
        Set<ScenarioStatus> exceptionalTerminals = EnumSet.of(
            ScenarioStatus.FAILED, ScenarioStatus.CANCELLED, ScenarioStatus.TIMED_OUT);
        Map<ScenarioStatus, Set<ScenarioStatus>> map = new EnumMap<>(ScenarioStatus.class);
        putTransition(map, ScenarioStatus.RECEIVED, ScenarioStatus.NAVIGATING,
            exceptionalTerminals);
        putTransition(map, ScenarioStatus.NAVIGATING, ScenarioStatus.COMPLETED,
            exceptionalTerminals);
        map.put(ScenarioStatus.COMPLETED, Set.of());
        map.put(ScenarioStatus.FAILED, Set.of());
        map.put(ScenarioStatus.CANCELLED, Set.of());
        map.put(ScenarioStatus.TIMED_OUT, Set.of());
        return map;
    }

    private static void putTransition(
        Map<ScenarioStatus, Set<ScenarioStatus>> map,
        ScenarioStatus from,
        ScenarioStatus happyNext,
        Set<ScenarioStatus> terminals) {
        Set<ScenarioStatus> allowed = EnumSet.of(happyNext);
        allowed.addAll(terminals);
        map.put(from, allowed);
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }

    private static String requireText(String value, String field, int maxLength) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        if (value.length() > maxLength) {
            throw new IllegalArgumentException(
                field + " must not exceed " + maxLength + " characters");
        }
        return value;
    }

    private static Map<String, Object> stringObjectMap(Object value) {
        if (!(value instanceof Map<?, ?> raw)) {
            throw new IllegalStateException("Scenario conversation triggerContext must be an object");
        }
        Map<String, Object> copied = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new IllegalStateException(
                    "Scenario conversation triggerContext keys must be strings");
            }
            copied.put(key, entry.getValue());
        }
        return copied;
    }

    private void finish(
        ScenarioStatus terminalStatus,
        String resultCode,
        String reasonCode
    ) {
        transitionTo(terminalStatus);
        this.completionResultCode = normalizeCode(resultCode, "resultCode", 50);
        this.completionReasonCode = normalizeCode(reasonCode, "reasonCode", 100);
        clearNavigationCorrelation();
    }

    private static String normalizeCode(String value, String field, int maxLength) {
        if (value == null) {
            return null;
        }
        String normalized = value.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        if (normalized.length() > maxLength) {
            throw new IllegalArgumentException(
                field + " must not exceed " + maxLength + " characters");
        }
        return normalized;
    }

    private void clearNavigationCorrelation() {
        this.activeNavigationCommandId = null;
        this.activeNavigationTarget = null;
    }
}
