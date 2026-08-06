package com.ssafy.bomi.observation.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.any;
import static org.mockito.Mockito.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.observation.config.ObservationProperties;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class RobotObservationServiceTest {

    private final RobotRepository robotRepository = mock(RobotRepository.class);
    private final CareRecordRepository careRecordRepository = mock(CareRecordRepository.class);
    private final ObservationProperties properties = new ObservationProperties();
    private final ObjectMapper objectMapper = new ObjectMapper();

    private RobotObservationService service;

    private final UUID seniorId = UUID.randomUUID();
    private final UUID robotId = UUID.randomUUID();
    private final String deviceId = "robot-01";
    private final String ambientSensorId = "ambient-sensor-01";

    @BeforeEach
    void setUp() {
        properties.setAmbientSensorToSenior(Map.of(ambientSensorId, seniorId));
        service = new RobotObservationService(robotRepository, careRecordRepository, properties);
    }

    private ObjectNode restBody(String state) {
        ObjectNode body = objectMapper.createObjectNode();
        body.putObject("payload").put("restState", state);
        return body;
    }

    @Test
    void restingRecordsObservationAndEntersRestGuard() {
        Robot robot = Robot.create(seniorId, deviceId);
        when(robotRepository.findByDeviceIdForUpdate(deviceId)).thenReturn(Optional.of(robot));

        service.recordRestState(deviceId, restBody("RESTING"));

        ArgumentCaptor<CareRecord> captor = ArgumentCaptor.forClass(CareRecord.class);
        verify(careRecordRepository).save(captor.capture());
        assertThat(captor.getValue().getRecordType()).isEqualTo("REST_OBSERVATION");
        assertThat(captor.getValue().getDetails()).containsEntry("restState", "RESTING");
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.REST_GUARD);
        verify(robotRepository).save(robot);
    }

    @Test
    void awakeClearsRestGuardBackToIdle() {
        Robot robot = Robot.create(seniorId, deviceId);
        robot.changeMode(RobotMode.REST_GUARD);
        when(robotRepository.findByDeviceIdForUpdate(deviceId)).thenReturn(Optional.of(robot));

        service.recordRestState(deviceId, restBody("AWAKE"));

        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.IDLE);
    }

    @Test
    void unknownRobotIsIgnored() {
        when(robotRepository.findByDeviceIdForUpdate("ghost")).thenReturn(Optional.empty());

        service.recordRestState("ghost", restBody("RESTING")); // must not throw

        verifyNoInteractions(careRecordRepository);
    }

    @Test
    void restStateNeverOverwritesSafeStop() {
        Robot robot = Robot.create(seniorId, deviceId);
        robot.changeMode(RobotMode.SAFE_STOP);
        when(robotRepository.findByDeviceIdForUpdate(deviceId)).thenReturn(Optional.of(robot));

        service.recordRestState(deviceId, restBody("RESTING"));
        service.recordRestState(deviceId, restBody("AWAKE"));

        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.SAFE_STOP);
    }

    @Test
    void restStateNeverOverwritesActiveScenarioMode() {
        Robot robot = Robot.create(seniorId, deviceId);
        robot.changeMode(RobotMode.SCENARIO_ACTIVE);
        when(robotRepository.findByDeviceIdForUpdate(deviceId)).thenReturn(Optional.of(robot));

        service.recordRestState(deviceId, restBody("RESTING"));
        service.recordRestState(deviceId, restBody("AWAKE"));

        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.SCENARIO_ACTIVE);
    }

    @Test
    void ambientFromUnmappedSensorIsDroppedWithoutThrowing() {
        // 예외가 새어 나가면 인바운드 엔드포인트가 ack 를 생략해 브로커가
        // 같은 메시지를 무한 재전송한다. 미등록 센서는 조용히 폐기해야 한다.
        ObjectNode body = objectMapper.createObjectNode();
        body.putObject("payload").put("temperatureC", 31.0);

        service.recordAmbient("unmapped-sensor", body); // must not throw

        verifyNoInteractions(careRecordRepository);
        verifyNoInteractions(robotRepository);
    }

    @Test
    void ambientUpdatesRobotSnapshotAndRecordsObservation() {
        when(robotRepository.findIdBySeniorId(seniorId)).thenReturn(Optional.of(robotId));
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("temperatureC", 24.5);
        payload.put("humidityPercent", 50.0);
        payload.put("comfortAssessment", "COMFORTABLE");

        service.recordAmbient(ambientSensorId, body);

        verify(robotRepository).updateAmbientSnapshotById(
            eq(robotId), eq(new java.math.BigDecimal("24.5")),
            eq(new java.math.BigDecimal("50.0")), any());

        ArgumentCaptor<CareRecord> captor = ArgumentCaptor.forClass(CareRecord.class);
        verify(careRecordRepository).save(captor.capture());
        assertThat(captor.getValue().getRecordType()).isEqualTo("ENVIRONMENT_OBSERVATION");
        assertThat(captor.getValue().getDetails())
            .containsKey("temperatureC")
            .containsEntry("comfortAssessment", "COMFORTABLE");
    }
}
