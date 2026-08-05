package com.ssafy.bomi.scenario.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** Time limits for the Backend ↔ AI conversation lifecycle. */
@Component
@ConfigurationProperties(prefix = "bomi.ai-conversation")
public class AiConversationProperties {

    private Duration startTimeout = Duration.ofSeconds(10);
    private Duration maxDuration = Duration.ofMinutes(5);
    private long timeoutCheckIntervalMillis = 1_000L;

    public Duration getStartTimeout() {
        return startTimeout;
    }

    public void setStartTimeout(Duration startTimeout) {
        this.startTimeout = positive(startTimeout, "startTimeout");
    }

    public Duration getMaxDuration() {
        return maxDuration;
    }

    public void setMaxDuration(Duration maxDuration) {
        this.maxDuration = positive(maxDuration, "maxDuration");
    }

    public long getTimeoutCheckIntervalMillis() {
        return timeoutCheckIntervalMillis;
    }

    public void setTimeoutCheckIntervalMillis(long timeoutCheckIntervalMillis) {
        if (timeoutCheckIntervalMillis <= 0) {
            throw new IllegalArgumentException("timeoutCheckIntervalMillis must be positive");
        }
        this.timeoutCheckIntervalMillis = timeoutCheckIntervalMillis;
    }

    private static Duration positive(Duration value, String field) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(field + " must be positive");
        }
        return value;
    }
}
