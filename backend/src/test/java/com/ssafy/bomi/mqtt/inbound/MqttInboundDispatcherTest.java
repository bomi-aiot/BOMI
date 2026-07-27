package com.ssafy.bomi.mqtt.inbound;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * Pure unit tests for {@link MqttInboundDispatcher} routing (no Spring context).
 */
class MqttInboundDispatcherTest {

    private MqttInboundMessage message(MqttInboundCategory category, String type) {
        return new MqttInboundMessage(
            category, "bomi/v1/topic", "src-01", "evt-01", type, OffsetDateTime.now(), 1, false, null);
    }

    /** Test handler that records the messages it receives and matches by category. */
    private static final class RecordingHandler implements MqttMessageHandler {
        private final MqttInboundCategory supported;
        private final List<MqttInboundMessage> received = new ArrayList<>();

        RecordingHandler(MqttInboundCategory supported) {
            this.supported = supported;
        }

        @Override
        public boolean supports(MqttInboundMessage message) {
            return message.category() == supported;
        }

        @Override
        public void handle(MqttInboundMessage message) {
            received.add(message);
        }
    }

    @Test
    void routesOnlyToMatchingHandler() {
        RecordingHandler iot = new RecordingHandler(MqttInboundCategory.IOT_EVENT);
        RecordingHandler result = new RecordingHandler(MqttInboundCategory.ROBOT_RESULT);
        MqttInboundDispatcher dispatcher = new MqttInboundDispatcher(List.of(iot, result));

        dispatcher.dispatch(message(MqttInboundCategory.IOT_EVENT, "DOOR_OPENED"));

        assertThat(iot.received).hasSize(1);
        assertThat(iot.received.get(0).type()).isEqualTo("DOOR_OPENED");
        assertThat(result.received).isEmpty();
    }

    @Test
    void deliversToEveryMatchingHandler() {
        RecordingHandler a = new RecordingHandler(MqttInboundCategory.ROBOT_STATUS);
        RecordingHandler b = new RecordingHandler(MqttInboundCategory.ROBOT_STATUS);
        MqttInboundDispatcher dispatcher = new MqttInboundDispatcher(List.of(a, b));

        dispatcher.dispatch(message(MqttInboundCategory.ROBOT_STATUS, "NAVIGATION_STATUS"));

        assertThat(a.received).hasSize(1);
        assertThat(b.received).hasSize(1);
    }

    @Test
    void ignoresMessageWhenNoHandlerMatches() {
        RecordingHandler iot = new RecordingHandler(MqttInboundCategory.IOT_EVENT);
        MqttInboundDispatcher dispatcher = new MqttInboundDispatcher(List.of(iot));

        // No handler for ROBOT_RESULT — must not throw, must not deliver anywhere.
        dispatcher.dispatch(message(MqttInboundCategory.ROBOT_RESULT, "NAVIGATION_RESULT"));

        assertThat(iot.received).isEmpty();
    }

    @Test
    void toleratesEmptyHandlerList() {
        MqttInboundDispatcher dispatcher = new MqttInboundDispatcher(List.of());
        // Should simply log-and-ignore without throwing.
        dispatcher.dispatch(message(MqttInboundCategory.ROBOT_EVENT, "ONBOARDING_ANSWER_CAPTURED"));
    }
}
