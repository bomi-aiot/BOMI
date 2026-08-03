package com.ssafy.bomi.scenario.inbound;

import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.occupancy.application.DoorEventService;
import com.ssafy.bomi.occupancy.application.EntranceDirectionResolver.Signal;
import com.ssafy.bomi.scenario.config.HomecomingProperties;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Inbound adapter for the hallway PIR (S15P11E102-226).
 *
 * <p><b>The second half of direction.</b> {@code DOOR_OPENED} alone says the door moved;
 * this says somebody was in the hallway. Only the order of the two tells you whether they
 * came in or went out (CLAUDE.md §11).</p>
 *
 * <p>Until this handler existed the backend saw one sensor and could never derive
 * direction — which is why every door open started a homecoming, including the ones where
 * the senior was on their way out.</p>
 *
 * <p>This event type is <b>not yet published by the deployed firmware</b> (CLAUDE.md §24).
 * The handler is here so the server side is ready and testable; nothing breaks while the
 * topic stays silent, the passage simply never resolves.</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class EntranceMotionHandler implements MqttMessageHandler {

    private static final Logger log = LoggerFactory.getLogger(EntranceMotionHandler.class);
    private static final String TYPE_MOTION_DETECTED = "MOTION_DETECTED";

    private final DoorEventService doorEventService;
    private final HomecomingProperties properties;

    public EntranceMotionHandler(DoorEventService doorEventService,
        HomecomingProperties properties) {
        this.doorEventService = doorEventService;
        this.properties = properties;
    }

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.IOT_EVENT
            && TYPE_MOTION_DETECTED.equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        UUID seniorId = properties.findSenior(message.sourceId()).orElse(null);
        if (seniorId == null) {
            // 예외를 던지면 ack 가 생략되어 브로커가 무한 재전송한다. 경고 후 폐기.
            log.warn("Motion event from unmapped sensor; dropping: sensorId={}", message.sourceId());
            return;
        }
        // 도착 시각을 쓴다. 라즈베리파이가 실은 시각이 아니다 — 배터리 백업 RTC 가
        // 없는 기기는 몇 년씩 어긋난 채로 부팅하고, 여기서 순서가 뒤집히면 귀가가
        // 외출로 판정된다 (CLAUDE.md §11).
        doorEventService.accept(seniorId, Signal.MOTION, OffsetDateTime.now(), null);
        log.debug("entrance motion from {}", message.sourceId());
    }
}
