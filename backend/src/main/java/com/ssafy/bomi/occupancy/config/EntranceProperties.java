package com.ssafy.bomi.occupancy.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Timing dials for entrance direction and greetings (S15P11E102-226).
 *
 * <p>All three are <b>empirical</b> — they depend on hallway length, how fast this senior
 * walks, and how quickly the robot can speak. Config rather than constants is the point of
 * putting direction judgement on the server: tuning must not need a robot deploy
 * (CLAUDE.md §11, §24).</p>
 */
@Component
@ConfigurationProperties(prefix = "bomi.entrance")
public class EntranceProperties {

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
