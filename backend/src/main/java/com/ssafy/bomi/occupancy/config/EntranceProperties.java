package com.ssafy.bomi.occupancy.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Timing dials for entrance direction and greetings (S15P11E102-226).
 *
 * <p>All three durations are <b>empirical</b> — they depend on hallway length, how fast
 * this senior walks, and how quickly the robot can speak. Config rather than constants is
 * the point of putting direction judgement on the server: tuning must not need a robot
 * deploy (CLAUDE.md §11, §24).</p>
 */
@Component
@ConfigurationProperties(prefix = "bomi.entrance")
public class EntranceProperties {

    /**
     * Whether a door-open on MQTT goes through direction resolution (S15P11E102-365).
     *
     * <p><b>Off (default):</b> {@code DoorOpenedHandler} calls the homecoming orchestrator
     * directly. Every door open starts a homecoming regardless of which way the senior was
     * walking, and the PIR has no effect — the resolver only ever sees half a passage, so
     * it never resolves one.</p>
     *
     * <p><b>On:</b> the door event joins the PIR in {@code DoorEventService}, direction
     * (IN/OUT) becomes available, occupancy moves, an {@code occupancy_event} row is
     * written (which is what {@code outingCount} counts), and {@code GreetingDecider}
     * chooses between the welcome and escort chains.</p>
     *
     * <p><b>Why it defaults to off.</b> Direction is the <em>order</em> of two signals. A
     * PIR mounted near the door can see somebody approaching from outside before the
     * contact opens, and {@code MOTION → DOOR_OPENED} means {@code OUT} — so a senior
     * arriving home would be told "다녀오세요". Whether that happens is a property of
     * where the sensor points, which only a field run can answer. Ship off, verify in a
     * rehearsal, turn on with one environment variable.</p>
     */
    private boolean directionResolutionEnabled = false;

    /**
     * How long after one sensor fires the other still counts as the same passage.
     *
     * <p>Too short and a slow walk never resolves, so nobody is ever greeted. Too long and
     * two unrelated events pair up, which invents a direction and moves occupancy on a
     * guess. Starts at 15s; measure on real hardware.</p>
     */
    private Duration correlationWindow = Duration.ofSeconds(15);

    /**
     * A greeting older than this is dropped rather than spoken.
     *
     * <p>"Welcome home" ten minutes late is worse than silence — the robot announces to an
     * empty hallway. Expired greetings are <b>dropped, not rescheduled</b>
     * (CLAUDE.md §11).</p>
     */
    private Duration greetingTtl = Duration.ofSeconds(45);

    /**
     * A reversal inside this window is treated as a contradiction, not two passages.
     *
     * <p>A delivery looks like a passage: somebody walks to the door, it opens, and moments
     * later the pattern reverses. Believing both readings would flip occupancy twice and
     * greet a senior who never went anywhere.</p>
     *
     * <p>On contradiction we do not pick the more likely story — we fall back to
     * {@code UNKNOWN} and let speech settle it (CLAUDE.md §11).</p>
     */
    private Duration reversalWindow = Duration.ofSeconds(30);

    public boolean isDirectionResolutionEnabled() {
        return directionResolutionEnabled;
    }

    public void setDirectionResolutionEnabled(boolean directionResolutionEnabled) {
        this.directionResolutionEnabled = directionResolutionEnabled;
    }

    public Duration getCorrelationWindow() {
        return correlationWindow;
    }

    public void setCorrelationWindow(Duration correlationWindow) {
        this.correlationWindow = correlationWindow;
    }

    public Duration getGreetingTtl() {
        return greetingTtl;
    }

    public void setGreetingTtl(Duration greetingTtl) {
        this.greetingTtl = greetingTtl;
    }

    public Duration getReversalWindow() {
        return reversalWindow;
    }

    public void setReversalWindow(Duration reversalWindow) {
        this.reversalWindow = reversalWindow;
    }
}
