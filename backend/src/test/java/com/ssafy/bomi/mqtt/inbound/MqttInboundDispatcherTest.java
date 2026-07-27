package com.ssafy.bomi.mqtt.inbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * Pure unit tests for {@link MqttInboundDispatcher}: routing + idempotency
 * (no Spring context).
 */
class MqttInboundDispatcherTest {

    private MqttInboundMessage message(MqttInboundCategory category, String type) {
        return message(category, type, "evt-01");
    }

    private MqttInboundMessage message(MqttInboundCategory category, String type, String eventId) {
        return new MqttInboundMessage(
            category, "bomi/v1/topic", "src-01", eventId, type, OffsetDateTime.now(), 1, false, null);
    }

    private MqttInboundDispatcher dispatcher(MqttMessageHandler... handlers) {
        return new MqttInboundDispatcher(List.of(handlers), new InMemoryProcessedEventStore());
    }

    /** Records the messages it receives and matches by category. */
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

    /** Matches by category and always throws, counting attempts. */
    private static final class ThrowingHandler implements MqttMessageHandler {
        private final MqttInboundCategory supported;
        private int attempts = 0;

        ThrowingHandler(MqttInboundCategory supported) {
            this.supported = supported;
        }

        @Override
        public boolean supports(MqttInboundMessage message) {
            return message.category() == supported;
        }

        @Override
        public void handle(MqttInboundMessage message) {
            attempts++;
            throw new IllegalStateException("boom");
        }
    }

    @Test
    void routesOnlyToMatchingHandler() {
        RecordingHandler iot = new RecordingHandler(MqttInboundCategory.IOT_EVENT);
        RecordingHandler result = new RecordingHandler(MqttInboundCategory.ROBOT_RESULT);
        MqttInboundDispatcher dispatcher = dispatcher(iot, result);

        dispatcher.dispatch(message(MqttInboundCategory.IOT_EVENT, "DOOR_OPENED"));

        assertThat(iot.received).hasSize(1);
        assertThat(iot.received.get(0).type()).isEqualTo("DOOR_OPENED");
        assertThat(result.received).isEmpty();
    }

    @Test
    void deliversToEveryMatchingHandler() {
        RecordingHandler a = new RecordingHandler(MqttInboundCategory.ROBOT_STATUS);
        RecordingHandler b = new RecordingHandler(MqttInboundCategory.ROBOT_STATUS);
        MqttInboundDispatcher dispatcher = dispatcher(a, b);

        dispatcher.dispatch(message(MqttInboundCategory.ROBOT_STATUS, "NAVIGATION_STATUS"));

        assertThat(a.received).hasSize(1);
        assertThat(b.received).hasSize(1);
    }

    @Test
    void ignoresMessageWhenNoHandlerMatches() {
        RecordingHandler iot = new RecordingHandler(MqttInboundCategory.IOT_EVENT);
        MqttInboundDispatcher dispatcher = dispatcher(iot);

        dispatcher.dispatch(message(MqttInboundCategory.ROBOT_RESULT, "NAVIGATION_RESULT"));

        assertThat(iot.received).isEmpty();
    }

    @Test
    void toleratesEmptyHandlerList() {
        MqttInboundDispatcher dispatcher = dispatcher();
        dispatcher.dispatch(message(MqttInboundCategory.ROBOT_EVENT, "ONBOARDING_ANSWER_CAPTURED"));
    }

    @Test
    void skipsDuplicateEventId() {
        RecordingHandler iot = new RecordingHandler(MqttInboundCategory.IOT_EVENT);
        MqttInboundDispatcher dispatcher = dispatcher(iot);

        MqttInboundMessage first = message(MqttInboundCategory.IOT_EVENT, "DOOR_OPENED", "same-id");
        MqttInboundMessage duplicate = message(MqttInboundCategory.IOT_EVENT, "DOOR_OPENED", "same-id");
        dispatcher.dispatch(first);
        dispatcher.dispatch(duplicate);

        assertThat(iot.received).hasSize(1); // processed exactly once
    }

    @Test
    void failedHandlingIsRetriableOnRedelivery() {
        ThrowingHandler thrower = new ThrowingHandler(MqttInboundCategory.ROBOT_RESULT);
        MqttInboundDispatcher dispatcher = dispatcher(thrower);

        MqttInboundMessage msg = message(MqttInboundCategory.ROBOT_RESULT, "NAVIGATION_RESULT", "retry-id");
        // First delivery fails; reservation must be released so a redelivery retries.
        assertThatThrownBy(() -> dispatcher.dispatch(msg)).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> dispatcher.dispatch(msg)).isInstanceOf(IllegalStateException.class);

        assertThat(thrower.attempts).isEqualTo(2); // not skipped as duplicate after failure
    }
}
