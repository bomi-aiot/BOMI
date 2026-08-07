package com.ssafy.bomi.robot.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.domain.RobotModeRecoveryAudit;
import com.ssafy.bomi.robot.domain.RobotModeRecoveryDisposition;
import com.ssafy.bomi.robot.repository.RobotModeRecoveryAuditRepository;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.application.ScenarioRobotStartPolicy;
import com.ssafy.bomi.scenario.application.ScenarioRobotStartPolicy.ModePolicy;
import com.ssafy.bomi.scenario.application.ScenarioStartGuard;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class RobotModeRecoveryConcurrencyTest {

    @Autowired RobotRepository robotRepository;
    @Autowired ScenarioRepository scenarioRepository;
    @Autowired AppUserRepository appUserRepository;
    @Autowired RobotModeRecoveryAuditRepository auditRepository;
    @Autowired PlatformTransactionManager transactionManager;

    private TransactionTemplate transactions;
    private RobotModeRecoveryService recoveryService;
    private ScenarioRobotStartPolicy startPolicy;
    private final Clock clock = Clock.fixed(
        Instant.parse("2026-08-05T12:00:00Z"), ZoneOffset.UTC);
    private String deviceId;
    private UUID robotId;

    @BeforeEach
    void setUp() {
        transactions = new TransactionTemplate(transactionManager);
        ScenarioStartGuard startGuard =
            new ScenarioStartGuard(scenarioRepository, appUserRepository);
        startPolicy = new ScenarioRobotStartPolicy(
            startGuard, robotRepository, scenarioRepository);
        recoveryService = new RobotModeRecoveryService(
            robotRepository,
            scenarioRepository,
            startGuard,
            auditRepository,
            clock);
        deviceId = "recovery-race-" + UUID.randomUUID();

        transactions.executeWithoutResult(ignored -> {
            UUID seniorId = appUserRepository.saveAndFlush(
                AppUser.create("SENIOR", "복구 동시성 테스트 어르신")).getId();
            Robot robot = Robot.create(seniorId, deviceId);
            robot.changeMode(RobotMode.SAFE_STOP);
            robotId = robotRepository.saveAndFlush(robot).getId();
        });
    }

    @AfterEach
    void cleanUp() {
        transactions.executeWithoutResult(ignored -> {
            auditRepository.deleteAll();
            scenarioRepository.deleteAll();
            robotRepository.deleteAll();
            appUserRepository.deleteAll();
        });
    }

    @Test
    void recoveryAndScenarioStartNeverCommitIdleWithAnActiveScenario() throws Exception {
        runConcurrently(this::recover, this::tryStartScenario);

        Robot robot = robotRepository.findById(robotId).orElseThrow();
        boolean activeScenario = scenarioRepository.existsByRobotIdAndFinalStatusIn(
            robotId, ScenarioStatus.activeStatuses());

        if (activeScenario) {
            assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.SCENARIO_ACTIVE);
        } else {
            assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.IDLE);
        }
        assertThat(auditRepository.findAll()).hasSize(1);
    }

    @Test
    void alreadyIdleNoOpPersistsAuditInTheDatabase() {
        transactions.executeWithoutResult(ignored ->
            robotRepository.findByIdForUpdate(robotId).orElseThrow()
                .changeMode(RobotMode.IDLE));

        RobotModeRecoveryResult result = transactions.execute(ignored ->
            recoveryService.recoverToIdle(
                deviceId,
                "operator-idle-test",
                true,
                "already idle state verified"));

        assertThat(result).isNotNull();
        assertThat(result.disposition())
            .isEqualTo(RobotModeRecoveryDisposition.NO_OP_ALREADY_IDLE);
        assertThat(robotRepository.findById(robotId).orElseThrow().getCurrentMode())
            .isEqualTo(RobotMode.IDLE);
        assertThat(auditRepository.findAll()).singleElement().satisfies(audit -> {
            assertThat(audit.getId()).isEqualTo(result.auditId());
            assertThat(audit.getPreviousMode()).isEqualTo(RobotMode.IDLE);
            assertThat(audit.getTargetMode()).isEqualTo(RobotMode.IDLE);
            assertThat(audit.isPhysicalSafetyConfirmed()).isTrue();
            assertThat(audit.getOperatorId()).isEqualTo("operator-idle-test");
            assertThat(audit.getReason()).isEqualTo("already idle state verified");
        });
    }

    @Test
    void auditFailureRollsBackModeRecovery() {
        RobotModeRecoveryAuditRepository failingAuditRepository =
            mock(RobotModeRecoveryAuditRepository.class);
        when(failingAuditRepository.save(any(RobotModeRecoveryAudit.class)))
            .thenThrow(new IllegalStateException("audit unavailable"));
        ScenarioStartGuard startGuard =
            new ScenarioStartGuard(scenarioRepository, appUserRepository);
        RobotModeRecoveryService failingService = new RobotModeRecoveryService(
            robotRepository,
            scenarioRepository,
            startGuard,
            failingAuditRepository,
            clock);

        assertThatThrownBy(() -> transactions.executeWithoutResult(ignored ->
            failingService.recoverToIdle(
                deviceId,
                "operator-rollback-test",
                true,
                "audit persistence must be atomic")))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("audit unavailable");

        assertThat(robotRepository.findById(robotId).orElseThrow().getCurrentMode())
            .isEqualTo(RobotMode.SAFE_STOP);
        assertThat(auditRepository.findAll()).isEmpty();
    }

    private void recover() {
        transactions.executeWithoutResult(ignored -> recoveryService.recoverToIdle(
            deviceId,
            "operator-concurrency-test",
            true,
            "physical safety confirmed before concurrency test"));
    }

    private void tryStartScenario() {
        transactions.executeWithoutResult(ignored -> {
            var decision = startPolicy.admitByDevice(
                deviceId, ScenarioType.HOMECOMING, Duration.ZERO, ModePolicy.IDLE_ONLY);
            if (!decision.allowed()) {
                return;
            }
            Robot robot = decision.robot();
            Scenario scenario = Scenario.create(
                robot.getSeniorId(), robot.getId(), ScenarioType.HOMECOMING,
                "recovery-race-event-" + UUID.randomUUID());
            scenario.beginMovingToEntrance();
            robot.changeMode(RobotMode.SCENARIO_ACTIVE);
            scenarioRepository.save(scenario);
        });
    }

    private static void runConcurrently(Runnable first, Runnable second) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        try {
            Future<?> one = executor.submit(() -> runWhenReleased(first, ready, start));
            Future<?> two = executor.submit(() -> runWhenReleased(second, ready, start));
            ready.await();
            start.countDown();
            one.get();
            two.get();
        } finally {
            executor.shutdownNow();
        }
    }

    private static void runWhenReleased(
        Runnable task,
        CountDownLatch ready,
        CountDownLatch start
    ) {
        ready.countDown();
        try {
            start.await();
            task.run();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Recovery concurrency test was interrupted", ex);
        }
    }
}
