package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.domain.WakeWordTriggerDisposition;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.scenario.repository.WakeWordTriggerReceiptRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
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
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.test.context.ActiveProfiles;

@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class WakeWordCallConcurrencyTest {

    @Autowired ScenarioRepository scenarioRepository;
    @Autowired WakeWordTriggerReceiptRepository receiptRepository;
    @Autowired RobotRepository robotRepository;
    @Autowired AppUserRepository appUserRepository;
    @Autowired PlatformTransactionManager transactionManager;

    private final Clock clock = Clock.fixed(
        Instant.parse("2026-08-05T01:00:00Z"), ZoneOffset.UTC);
    private final OffsetDateTime occurredAt =
        OffsetDateTime.parse("2026-08-05T10:00:00+09:00");

    private TransactionTemplate transactions;
    private RecordingPublisher publisher;
    private WakeWordCallOrchestrator orchestrator;
    private String deviceId;
    private UUID seniorId;

    @BeforeEach
    void setUp() {
        transactions = new TransactionTemplate(transactionManager);
        publisher = new RecordingPublisher();
        deviceId = "robot-" + UUID.randomUUID();
        transactions.executeWithoutResult(ignored -> {
            seniorId = appUserRepository.saveAndFlush(
                AppUser.create("SENIOR", "동시성 테스트 시니어")).getId();
            robotRepository.saveAndFlush(Robot.create(seniorId, deviceId));
        });
        ScenarioStartGuard startGuard =
            new ScenarioStartGuard(scenarioRepository, appUserRepository);
        ScenarioRobotStartPolicy startPolicy = new ScenarioRobotStartPolicy(
            startGuard, robotRepository, scenarioRepository);
        orchestrator = new WakeWordCallOrchestrator(
            scenarioRepository,
            receiptRepository,
            robotRepository,
            publisher,
            startPolicy,
            clock);
    }

    @AfterEach
    void cleanUp() {
        transactions.executeWithoutResult(ignored -> {
            receiptRepository.deleteAll();
            scenarioRepository.deleteAll();
            robotRepository.deleteAll();
            appUserRepository.deleteAll();
        });
    }

    @Test
    void concurrentRedeliveryCreatesOneScenarioAndOneCommand() throws Exception {
        String eventId = "wake-same-" + UUID.randomUUID();

        runConcurrently(
            () -> process(eventId),
            () -> process(eventId));

        assertThat(scenarioRepository.findAll()).hasSize(1);
        assertThat(scenarioRepository.findAll().get(0).getScenarioType())
            .isEqualTo(ScenarioType.WAKE_WORD_CALL);
        assertThat(receiptRepository.findAll()).hasSize(1);
        assertThat(receiptRepository.findAll().get(0).getDisposition())
            .isEqualTo(WakeWordTriggerDisposition.ACCEPTED);
        assertThat(publisher.commands).hasSize(1);
    }

    @Test
    void differentConcurrentEventsForOneRobotAcceptOnlyOneActiveScenario() throws Exception {
        runConcurrently(
            () -> process("wake-a-" + UUID.randomUUID()),
            () -> process("wake-b-" + UUID.randomUUID()));

        assertThat(scenarioRepository.findAll()).hasSize(1);
        assertThat(publisher.commands).hasSize(1);
        assertThat(receiptRepository.findAll())
            .extracting(receipt -> receipt.getDisposition())
            .containsExactlyInAnyOrder(
                WakeWordTriggerDisposition.ACCEPTED,
                WakeWordTriggerDisposition.REJECTED_ACTIVE_SCENARIO);
    }

    @Test
    void differentRobotsAssignedToOneSeniorAreSerializedByTheSeniorLock() throws Exception {
        String otherDeviceId = "robot-" + UUID.randomUUID();
        transactions.executeWithoutResult(ignored ->
            robotRepository.saveAndFlush(Robot.create(seniorId, otherDeviceId)));

        runConcurrently(
            () -> process(deviceId, "wake-first-" + UUID.randomUUID()),
            () -> process(otherDeviceId, "wake-second-" + UUID.randomUUID()));

        assertThat(scenarioRepository.findAll()).hasSize(1);
        assertThat(publisher.commands).hasSize(1);
        assertThat(receiptRepository.findAll())
            .extracting(receipt -> receipt.getDisposition())
            .containsExactlyInAnyOrder(
                WakeWordTriggerDisposition.ACCEPTED,
                WakeWordTriggerDisposition.REJECTED_ACTIVE_SCENARIO);
    }

    private void process(String eventId) {
        process(deviceId, eventId);
    }

    private void process(String targetDeviceId, String eventId) {
        transactions.executeWithoutResult(ignored -> orchestrator.onWakeWordDetected(
            targetDeviceId, eventId, occurredAt, "보미야", 0.92));
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
            throw new IllegalStateException("Concurrent wake-word test was interrupted", ex);
        }
    }

    private static final class RecordingPublisher implements RobotCommandPublisher {
        private final List<RobotCommand> commands = new CopyOnWriteArrayList<>();

        @Override
        public void publish(RobotCommand command) {
            commands.add(command);
        }
    }
}
