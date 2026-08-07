package com.ssafy.bomi.scenario.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import org.junit.jupiter.api.Test;

class AiConversationPropertiesTest {

    @Test
    void defaultsToAgreedTimeouts() {
        AiConversationProperties properties = new AiConversationProperties();

        assertThat(properties.getStartTimeout()).isEqualTo(Duration.ofSeconds(10));
        assertThat(properties.getMaxDuration()).isEqualTo(Duration.ofMinutes(5));
        assertThat(properties.getTimeoutCheckIntervalMillis()).isEqualTo(1_000L);
    }

    @Test
    void rejectsNonPositiveTimeouts() {
        AiConversationProperties properties = new AiConversationProperties();

        assertThatThrownBy(() -> properties.setStartTimeout(Duration.ZERO))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> properties.setMaxDuration(Duration.ofSeconds(-1)))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> properties.setTimeoutCheckIntervalMillis(0))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
