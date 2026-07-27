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
        Robot robot = robotRepository.findByDeviceId(robotDeviceId).orElse(null);
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
        careRecordRepository.save(record);

        applyRestMode(robot, restState);
        robotRepository.save(robot);
    }

    /** Ambient sensor reported an environment reading: update snapshot + record it. */
    @Transactional
    public void recordAmbient(String sensorId, JsonNode body) {
        UUID seniorId = properties.resolveSenior(sensorId);
        JsonNode payload = ObservationContract.payload(body);

        BigDecimal temperature = ObservationContract.optionalDecimal(payload, ObservationContract.TEMPERATURE_KEY);
        BigDecimal humidity = ObservationContract.optionalDecimal(payload, ObservationContract.HUMIDITY_KEY);
        OffsetDateTime observedAt = ObservationContract.optionalTimestamp(payload, ObservationContract.OBSERVED_AT_KEY);
        JsonNode comfortNode = payload.get(ObservationContract.COMFORT_KEY);
        String comfort = (comfortNode != null && comfortNode.isTextual()) ? comfortNode.textValue() : null;

        robotRepository.findBySeniorId(seniorId).ifPresent(robot -> {
            robot.recordAmbient(temperature, humidity, observedAt == null ? OffsetDateTime.now() : observedAt);
            robotRepository.save(robot);
        });

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
        careRecordRepository.save(CareRecord.create(seniorId, RECORD_ENVIRONMENT_OBSERVATION, details));
    }

    /** RESTING → REST_GUARD; AWAKE clears REST_GUARD back to IDLE (other modes untouched). */
    private void applyRestMode(Robot robot, String restState) {
        if (ObservationContract.REST_STATE_RESTING.equals(restState)) {
            robot.changeMode(RobotMode.REST_GUARD);
        } else if (ObservationContract.REST_STATE_AWAKE.equals(restState)
            && robot.getCurrentMode() == RobotMode.REST_GUARD) {
            robot.changeMode(RobotMode.IDLE);
        }
    }
}
