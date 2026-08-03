package com.ssafy.bomi.observation.inbound;

import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.observation.application.RobotObservationService;
import com.ssafy.bomi.scenario.application.WellnessCheckOrchestrator;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Inbound adapter for an ambient-environment observation ({@code IOT_EVENT} /
 * {@code AMBIENT_ENVIRONMENT_OBSERVED}). The topic {@code sourceId} is the
 * ambient sensor device id, resolved to a senior via configuration.
 *
 * <p>두 단계로 처리한다: ① 관측 기록(항상), ② 임계값 판정 후 안부 확인 시나리오
 * 시작(조건부, {@link WellnessCheckOrchestrator}). 기록과 행동을 분리해 두면
 * 임계값 미만의 평범한 관측도 대시보드에는 남는다.</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class AmbientObservedHandler implements MqttMessageHandler {

    private static final String TYPE_AMBIENT_ENVIRONMENT_OBSERVED = "AMBIENT_ENVIRONMENT_OBSERVED";

    private final RobotObservationService observationService;
    private final WellnessCheckOrchestrator wellnessCheckOrchestrator;

    public AmbientObservedHandler(
        RobotObservationService observationService,
        WellnessCheckOrchestrator wellnessCheckOrchestrator
    ) {
        this.observationService = observationService;
        this.wellnessCheckOrchestrator = wellnessCheckOrchestrator;
    }

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.IOT_EVENT
            && TYPE_AMBIENT_ENVIRONMENT_OBSERVED.equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        observationService.recordAmbient(message.sourceId(), message.body());
        wellnessCheckOrchestrator.onAmbientObserved(message.sourceId(), message.body());
    }
}
