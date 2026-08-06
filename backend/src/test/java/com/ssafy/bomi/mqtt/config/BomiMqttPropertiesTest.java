package com.ssafy.bomi.mqtt.config;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.validation.Validation;
import java.time.Duration;
import org.junit.jupiter.api.Test;

class BomiMqttPropertiesTest {

    @Test
    void defaultsAreSafeAndContractCompatible() {
        BomiMqttProperties properties = new BomiMqttProperties();

        assertThat(properties.isEnabled()).isFalse();
        assertThat(properties.getBrokerUrl()).isEqualTo("tcp://localhost:1883");
        assertThat(properties.getClientIdPrefix()).isEqualTo("bomi-backend");
        assertThat(properties.getQos()).isEqualTo(1);
    }

    @Test
    void rejectsNonContractQosAndNonPositiveTimeout() {
        BomiMqttProperties properties = new BomiMqttProperties();
        properties.setQos(2);
        properties.setCompletionTimeout(Duration.ZERO);

        try (var factory = Validation.buildDefaultValidatorFactory()) {
            var violations = factory.getValidator().validate(properties);
            assertThat(violations)
                .extracting(violation -> violation.getPropertyPath().toString())
                .contains("qos", "timeoutsValid");
        }
    }
}
