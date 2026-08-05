package com.ssafy.bomi.observation.application;

import com.fasterxml.jackson.databind.JsonNode;
import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.observation.config.ObservationProperties;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Reflects robot/IoT observations into the robot snapshot and care records.
 *
 * <p>Rest state (robot-sourced): records a {@code REST_OBSERVATION} and toggles
 * the robot's {@code REST_GUARD} mode. Ambient environment (sensor-sourced):
 * updates the robot's latest ambient snapshot and records an
 * {@code ENVIRONMENT_OBSERVATION}. Scenario-driven modes are left untouched.</p>
 */
@Service
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class RobotObservationService {

    private static final Logger log = LoggerFactory.getLogger(RobotObservationService.class);
    private static final String RECORD_REST_OBSERVATION = "REST_OBSERVATION";
    private static final String RECORD_ENVIRONMENT_OBSERVATION = "ENVIRONMENT_OBSERVATION";

    private final RobotRepository robotRepository;
    private final CareRecordRepository careRecordRepository;
    private final ObservationProperties properties;

    public RobotObservationService(
        RobotRepository robotRepository,
        CareRecordRepository careRecordRepository,
        ObservationProperties properties
    ) {
        this.robotRepository = robotRepository;
        this.careRecordRepository = careRecordRepository;
        this.properties = properties;
    }

    /** Robot reported a rest-state change: record it and toggle REST_GUARD. */
    @Transactional
    public void recordRestState(String robotDeviceId, JsonNode body) {
        Robot robot = robotRepository.findByDeviceIdForUpdate(robotDeviceId).orElse(null);
        if (robot == null) {
            log.warn("Rest state for unknown robot; ignoring: deviceId={}", robotDeviceId);
            return;
        }
        if (robot.getSeniorId() == null) {
            log.warn("Robot has no senior; ignoring rest state: deviceId={}", robotDeviceId);
            return;
        }

        JsonNode payload = ObservationContract.payload(body);
        String restState = ObservationContract.requiredText(payload, ObservationContract.REST_STATE_KEY);

        CareRecord record = CareRecord.create(
            robot.getSeniorId(), RECORD_REST_OBSERVATION,
            Map.of(ObservationContract.REST_STATE_KEY, restState));
        // 휴식 상태 관찰에는 지금까지 시각이 아예 없었다 (S15P11E102-230).
        //
        // details 에 상태만 있고 "언제"가 없어서, 침묵 사다리가 참고하는 "어제 몇 시부터
        // 주무셨나"를 물을 방법이 없었다. 이 관찰은 방금 도착한 것이므로 지금이 맞다.
        record.occurredAt(OffsetDateTime.now());
        careRecordRepository.save(record);

        applyRestMode(robot, restState);
        robotRepository.save(robot);
    }

    /** Ambient sensor reported an environment reading: update snapshot + record it. */
    @Transactional
    public void recordAmbient(String sensorId, JsonNode body) {
        UUID seniorId = properties.findSenior(sensorId).orElse(null);
        if (seniorId == null) {
            // 예외를 던지면 ack 가 생략되어 브로커가 무한 재전송한다. 경고 후 폐기.
            log.warn("Ambient event from unmapped sensor; dropping: sensorId={}", sensorId);
            return;
        }
        JsonNode payload = ObservationContract.payload(body);

        BigDecimal temperature = ObservationContract.optionalDecimal(payload, ObservationContract.TEMPERATURE_KEY);
        BigDecimal humidity = ObservationContract.optionalDecimal(payload, ObservationContract.HUMIDITY_KEY);
        OffsetDateTime observedAt = ObservationContract.optionalTimestamp(payload, ObservationContract.OBSERVED_AT_KEY);
        JsonNode comfortNode = payload.get(ObservationContract.COMFORT_KEY);
        String comfort = (comfortNode != null && comfortNode.isTextual()) ? comfortNode.textValue() : null;

        OffsetDateTime effectiveObservedAt = observedAt == null
            ? OffsetDateTime.now()
            : observedAt;
        UUID robotId = robotRepository.findIdBySeniorId(seniorId).orElse(null);
        if (robotId == null) {
            log.warn("No robot for senior {}; ambient reading recorded as an event only", seniorId);
        } else {
            robotRepository.updateAmbientSnapshotById(
                robotId, temperature, humidity, effectiveObservedAt);
        }

        Map<String, Object> details = new HashMap<>();
        if (temperature != null) {
            details.put(ObservationContract.TEMPERATURE_KEY, temperature);
        }
        if (humidity != null) {
            details.put(ObservationContract.HUMIDITY_KEY, humidity);
        }
        if (comfort != null) {
            details.put(ObservationContract.COMFORT_KEY, comfort);
        }
        CareRecord record = CareRecord.create(seniorId, RECORD_ENVIRONMENT_OBSERVATION, details);
        // 센서가 실은 관측 시각이 우선이다. 도착 시각으로 적으면 MQTT 가 밀린 만큼
        // 측정값이 미래로 이동한다.
        record.occurredAt(effectiveObservedAt);
        careRecordRepository.save(record);
    }

    /** RESTING → REST_GUARD; AWAKE clears REST_GUARD back to IDLE (other modes untouched). */
    private void applyRestMode(Robot robot, String restState) {
        if (ObservationContract.REST_STATE_RESTING.equals(restState)
            && robot.getCurrentMode() == RobotMode.IDLE) {
            robot.changeMode(RobotMode.REST_GUARD);
        } else if (ObservationContract.REST_STATE_AWAKE.equals(restState)
            && robot.getCurrentMode() == RobotMode.REST_GUARD) {
            robot.changeMode(RobotMode.IDLE);
        }
    }
}
