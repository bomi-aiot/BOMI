package com.ssafy.bomi.llm.config;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/**
 * Pins the billing-control defaults (S15P11E102-254 완료 조건).
 *
 * <p>Mirrors {@code EmbeddingPropertiesTest} in spirit: the whole point of this class is
 * that a fresh {@code LlmProperties} must never be usable, however it is constructed, unless
 * both an explicit enable and a real key are supplied.</p>
 */
class LlmPropertiesTest {

    @Test
    void defaultsAreOffAndUnusable() {
        LlmProperties properties = new LlmProperties();

        assertThat(properties.isEnabled()).isFalse();
        assertThat(properties.getApiKey()).isEmpty();
        assertThat(properties.isUsable()).isFalse();
    }

    @Test
    void enabledWithoutAnApiKeyIsStillUnusable() {
        LlmProperties properties = new LlmProperties();
        properties.setEnabled(true);

        assertThat(properties.isUsable()).isFalse();
    }

    @Test
    void blankApiKeyIsTreatedAsNoKey() {
        LlmProperties properties = new LlmProperties();
        properties.setEnabled(true);
        properties.setApiKey("   ");

        assertThat(properties.isUsable()).isFalse();
    }

    @Test
    void enabledWithARealKeyIsUsable() {
        LlmProperties properties = new LlmProperties();
        properties.setEnabled(true);
        properties.setApiKey("real-key");

        assertThat(properties.isUsable()).isTrue();
    }

    /** 실행당 처리 상한은 지출 상한이다 — 기본값이 조용히 무한대가 되면 안 된다. */
    @Test
    void maxCallsPerRunHasAFiniteDefault() {
        LlmProperties properties = new LlmProperties();

        assertThat(properties.getMaxCallsPerRun()).isPositive().isLessThan(1000);
    }
}
