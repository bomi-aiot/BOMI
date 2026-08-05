package com.ssafy.bomi.robot;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.ActiveProfiles;

@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class RobotRepositoryTest {

    @Autowired RobotRepository robotRepository;
    @Autowired TestEntityManager em;

    @Test
    void persistsWithDefaultsAndNullableSenior() {
        Robot robot = Robot.create(null);
        Robot saved = robotRepository.saveAndFlush(robot);
        em.clear();

        Robot found = robotRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getSeniorId()).isNull();
        assertThat(found.getCurrentMode()).isEqualTo(RobotMode.IDLE);
        assertThat(found.isActive()).isTrue();
    }

    @Test
    void recordsAmbientReading() {
        Robot robot = Robot.create(UUID.randomUUID());
        robot.changeMode(RobotMode.SCENARIO_ACTIVE);
        robot.recordAmbient(new BigDecimal("23.50"), new BigDecimal("48.20"), OffsetDateTime.now());
        Robot saved = robotRepository.saveAndFlush(robot);
        em.clear();

        Robot found = robotRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getSeniorId()).isNotNull();
        assertThat(found.getCurrentMode()).isEqualTo(RobotMode.SCENARIO_ACTIVE);
        assertThat(found.getAmbientTemperatureC()).isEqualByComparingTo("23.50");
        assertThat(found.getAmbientObservedAt()).isNotNull();
    }

    @Test
    void findsRobotByDeviceIdForScenarioStartLocking() {
        Robot saved = robotRepository.saveAndFlush(
            Robot.create(UUID.randomUUID(), "robot-lock-01"));
        em.clear();

        Robot locked = robotRepository.findByDeviceIdForUpdate("robot-lock-01").orElseThrow();

        assertThat(locked.getId()).isEqualTo(saved.getId());
    }
}
