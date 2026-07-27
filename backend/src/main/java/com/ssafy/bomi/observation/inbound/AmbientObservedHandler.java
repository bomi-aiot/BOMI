package com.ssafy.bomi.observation.inbound;

import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.observation.application.RobotObservationService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Inbound adapter for an ambient-environment observation ({@code IOT_EVENT} /
 * {@code AMBIENT_ENVIRONMENT_OBSERVED}). The topic {@code sourceId} is the
 * ambient sensor device id, resolved to a senior via configuration.
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class AmbientObservedHandler implements MqttMessageHandler {

    private static final String TYPE_AMBIENT_ENVIRONMENT_OBSERVED = "AMBIENT_ENVIRONMENT_OBSERVED";

    private final RobotObservationService observationService;

    public AmbientObservedHandler(RobotObservationService observationService) {
        this.observationService = observationService;
    }

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.IOT_EVENT
            && TYPE_AMBIENT_ENVIRONMENT_OBSERVED.equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        observationService.recordAmbient(message.sourceId(), message.body());
    }
}
