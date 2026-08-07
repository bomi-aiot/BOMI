package com.ssafy.bomi.scenario.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** Backend deadlines for command acknowledgements and the complete WALK lifecycle. */
@Component
@ConfigurationProperties(prefix = "bomi.walk")
public class WalkTimeoutProperties {

    private Duration followStartAckTimeout = Duration.ofSeconds(10);
    private Duration followStopAckTimeout = Duration.ofSeconds(10);
    private Duration maxDuration = Duration.ofHours(2);
    private long timeoutCheckIntervalMillis = 1_000;

    public Duration getFollowStartAckTimeout() {
        return followStartAckTimeout;
    }

    public void setFollowStartAckTimeout(Duration value) {
        this.followStartAckTimeout = positive(value, "followStartAckTimeout");
    }

    public Duration getFollowStopAckTimeout() {
        return followStopAckTimeout;
    }

    public void setFollowStopAckTimeout(Duration value) {
        this.followStopAckTimeout = positive(value, "followStopAckTimeout");
    }

    public Duration getMaxDuration() {
        return maxDuration;
    }

    public void setMaxDuration(Duration value) {
        this.maxDuration = positive(value, "maxDuration");
    }

    public long getTimeoutCheckIntervalMillis() {
        return timeoutCheckIntervalMillis;
    }

    public void setTimeoutCheckIntervalMillis(long value) {
        if (value <= 0) {
            throw new IllegalArgumentException("timeoutCheckIntervalMillis must be positive");
        }
        this.timeoutCheckIntervalMillis = value;
    }

    private static Duration positive(Duration value, String field) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(field + " must be positive");
        }
        return value;
    }
}
