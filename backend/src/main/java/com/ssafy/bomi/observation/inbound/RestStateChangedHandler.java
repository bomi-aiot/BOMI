package com.ssafy.bomi.observation.inbound;

import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.observation.application.RobotObservationService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Inbound adapter for a robot rest-state change ({@code ROBOT_STATUS} /
 * {@code REST_STATE_CHANGED}). The topic {@code sourceId} is the robot device id.
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class RestStateChangedHandler implements MqttMessageHandler {

    private static final String TYPE_REST_STATE_CHANGED = "REST_STATE_CHANGED";

    private final RobotObservationService observationService;

    public RestStateChangedHandler(RobotObservationService observationService) {
        this.observationService = observationService;
    }

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.ROBOT_STATUS
            && TYPE_REST_STATE_CHANGED.equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        observationService.recordRestState(message.sourceId(), message.body());
    }
}
