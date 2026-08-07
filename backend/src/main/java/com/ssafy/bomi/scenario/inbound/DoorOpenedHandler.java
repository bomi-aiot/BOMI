package com.ssafy.bomi.scenario.inbound;

import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.occupancy.application.DoorEventService;
import com.ssafy.bomi.occupancy.application.EntranceDirectionResolver.Signal;
import com.ssafy.bomi.occupancy.config.EntranceProperties;
import com.ssafy.bomi.scenario.application.HomecomingOrchestrator;
import com.ssafy.bomi.scenario.config.HomecomingProperties;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Inbound adapter for a door-open IoT event.
 *
 * <p>There are two ways to answer "the door opened, now what", and this handler picks
 * between them with {@code bomi.entrance.direction-resolution-enabled}
 * (S15P11E102-365).</p>
 *
 * <pre>
 *   off (default)  DOOR_OPENED -> HomecomingOrchestrator directly.
 *                  Every door open starts a homecoming, whichever way the senior was
 *                  walking. PIR has no effect at all.
 *
 *   on             DOOR_OPENED -> DoorEventService -> EntranceDirectionResolver.
 *                  A passage only resolves when the *other* sensor fires inside the
 *                  correlation window, so direction (IN/OUT) exists, occupancy moves,
 *                  and GreetingDecider can pick between "어서 오세요" and "다녀오세요".
 * </pre>
 *
 * <p><b>Why this is a switch and not a straight replacement.</b> Direction is derived
 * from the <em>order</em> of two signals, and a PIR mounted near the door can see somebody
 * approaching from outside before the contact opens. That order reads as
 * {@code MOTION -> DOOR_OPENED}, which is {@code OUT} — the robot would say "다녀오세요"
 * to a senior who just came home. Whether that happens depends on where the PIR points,
 * which is a field measurement, not something this code can decide. So the resolved path
 * ships off, gets verified in a rehearsal, and is turned on with one environment variable
 * (and turned back off just as fast if the field says otherwise).</p>
 *
 * <p><b>What the off path silently costs.</b> No direction means no occupancy transition
 * and no {@code occupancy_event} row, so {@code DailyActivityMetric.outingCount} — which
 * feeds both the conversation context and the daily summary — stays at zero, and the
 * escort greeting chain (unconfirmed medication, today's appointment) never runs. That is
 * a real loss, not a cosmetic one; it is accepted deliberately while the sensor geometry
 * is unverified.</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class DoorOpenedHandler implements MqttMessageHandler {

    private static final Logger log = LoggerFactory.getLogger(DoorOpenedHandler.class);
    private static final String TYPE_DOOR_OPENED = "DOOR_OPENED";

    private final HomecomingOrchestrator orchestrator;
    private final DoorEventService doorEventService;
    private final HomecomingProperties homecomingProperties;
    private final EntranceProperties entranceProperties;

    public DoorOpenedHandler(HomecomingOrchestrator orchestrator,
        DoorEventService doorEventService,
        HomecomingProperties homecomingProperties,
        EntranceProperties entranceProperties) {
        this.orchestrator = orchestrator;
        this.doorEventService = doorEventService;
        this.homecomingProperties = homecomingProperties;
        this.entranceProperties = entranceProperties;
    }

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.IOT_EVENT
            && TYPE_DOOR_OPENED.equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        if (!entranceProperties.isDirectionResolutionEnabled()) {
            // 옛 경로. 방향을 묻지 않고 문이 열렸다는 사실만으로 귀가를 시작한다.
            orchestrator.startHomecoming(message.sourceId());
            return;
        }

        UUID seniorId = homecomingProperties.findSenior(message.sourceId()).orElse(null);
        if (seniorId == null) {
            // 예외를 던지면 ack 가 생략되어 브로커가 무한 재전송한다. 경고 후 폐기 —
            // EntranceMotionHandler 와 같은 처리다.
            log.warn("Door event from unmapped sensor; dropping: sensorId={}",
                message.sourceId());
            return;
        }

        // 도착 시각을 쓴다. 라즈베리파이가 실은 시각이 아니다 — 배터리 백업 RTC 가
        // 없는 기기는 몇 년씩 어긋난 채로 부팅하고, 여기서 순서가 뒤집히면 귀가가
        // 외출로 판정된다 (CLAUDE.md §11). PIR 쪽과 같은 시계를 써야 두 신호의
        // 순서가 의미를 갖는다.
        doorEventService.accept(seniorId, Signal.DOOR_OPENED, OffsetDateTime.now(), null);
        log.debug("door opened from {} fed to direction resolution", message.sourceId());
    }
}
