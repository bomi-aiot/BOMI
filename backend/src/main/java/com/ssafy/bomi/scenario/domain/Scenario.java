package com.ssafy.bomi.scenario.domain;

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
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

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
 * Only allowed transitions succeed — see {@link #ALLOWED_TRANSITIONS} and
 * {@link #transitionTo(ScenarioStatus)}.</p>
 *
 * <p><b>Scope note (this sprint):</b> the transition map below encodes the
 * {@code HOMECOMING} happy path plus "any active state → terminal". This is one
 * shared rule set for all types; {@code FALL_RESPONSE} / {@code MANUAL_INTERACTION}
 * paths are added on top of the same map in a follow-up sprint. Robot mode
 * co-transition is intentionally out of scope here and handled by the robot
 * status/observation ticket.</p>
 */
@Entity
@Table(name = "scenario")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Scenario {

    /** Shared transition rules: from-status → allowed next statuses. */
    private static final Map<ScenarioStatus, Set<ScenarioStatus>> ALLOWED_TRANSITIONS =
        buildAllowedTransitions();

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

    // --- State machine -------------------------------------------------------

    /**
     * Moves to {@code next} if the transition is allowed by the shared rule set,
     * otherwise throws {@link IllegalStateException}. This is the single
     * enforcement point; the intent methods below delegate here.
     */
    public void transitionTo(ScenarioStatus next) {
        requireNonNull(next, "next");
        Set<ScenarioStatus> allowed = ALLOWED_TRANSITIONS.getOrDefault(finalStatus, Set.of());
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
        transitionTo(ScenarioStatus.COMPLETED);
    }

    // Terminal exits available from any active state.
    public void fail() {
        transitionTo(ScenarioStatus.FAILED);
    }

    public void cancel() {
        transitionTo(ScenarioStatus.CANCELLED);
    }

    public void timeOut() {
        transitionTo(ScenarioStatus.TIMED_OUT);
    }

    public boolean isTerminated() {
        return finalStatus.isTerminal();
    }

    private static Map<ScenarioStatus, Set<ScenarioStatus>> buildAllowedTransitions() {
        // Terminal statuses reachable from every active (non-terminal) status.
        Set<ScenarioStatus> terminals = EnumSet.of(
            ScenarioStatus.FAILED, ScenarioStatus.CANCELLED, ScenarioStatus.TIMED_OUT);

        Map<ScenarioStatus, Set<ScenarioStatus>> map = new EnumMap<>(ScenarioStatus.class);
        // HOMECOMING happy path (linear).
        putTransition(map, ScenarioStatus.RECEIVED, ScenarioStatus.MOVING_TO_ENTRANCE, terminals);
        putTransition(map, ScenarioStatus.MOVING_TO_ENTRANCE, ScenarioStatus.CHECKING_INTERACTION, terminals);
        putTransition(map, ScenarioStatus.CHECKING_INTERACTION, ScenarioStatus.CONVERSING, terminals);
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
}
