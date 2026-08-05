package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.WalkTimeoutProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.domain.WalkAction;
import com.ssafy.bomi.scenario.domain.WalkRequestDisposition;
import com.ssafy.bomi.scenario.domain.WalkRequestIngress;
import com.ssafy.bomi.scenario.domain.WalkRequestSource;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.scenario.repository.WalkRequestReceiptRepository;
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
class WalkOrchestratorConcurrencyTest {

    @Autowired ScenarioRepository scenarioRepository;
    @Autowired WalkRequestReceiptRepository receiptRepository;
    @Autowired RobotRepository robotRepository;
    @Autowired AppUserRepository appUserRepository;
    @Autowired PlatformTransactionManager transactionManager;

    private final Clock clock = Clock.fixed(
        Instant.parse("2026-08-05T08:00:00Z"), ZoneOffset.UTC);
    private final OffsetDateTime occurredAt =
        OffsetDateTime.parse("2026-08-05T17:00:00+09:00");

    private TransactionTemplate transactions;
    private RecordingPublisher publisher;
    private WalkOrchestrator orchestrator;
    private String deviceId;

    @BeforeEach
    void setUp() {
        transactions = new TransactionTemplate(transactionManager);
        publisher = new RecordingPublisher();
        deviceId = "walk-robot-" + UUID.randomUUID();
        transactions.executeWithoutResult(ignored -> {
            UUID seniorId = appUserRepository.saveAndFlush(
                AppUser.create("SENIOR", "산책 동시성 테스트 시니어")).getId();
            robotRepository.saveAndFlush(Robot.create(seniorId, deviceId));
        });
        orchestrator = newOrchestrator();
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
    void concurrentSameMqttRequestCreatesOneWalkAndOneFollowStart() throws Exception {
        String requestId = "walk-same-" + UUID.randomUUID();

        runConcurrently(
            () -> processVoice(requestId),
            () -> processVoice(requestId));

        assertThat(scenarioRepository.findAll()).hasSize(1);
        assertThat(scenarioRepository.findAll().get(0).getScenarioType())
            .isEqualTo(ScenarioType.WALK);
        assertThat(receiptRepository.findAll()).hasSize(1);
        assertThat(receiptRepository.findAll().get(0).getDisposition())
            .isEqualTo(WalkRequestDisposition.ACCEPTED);
        assertThat(publisher.commands)
            .extracting(RobotCommand::type)
            .containsExactly(RobotCommandType.FOLLOW_START);
    }

    @Test
    void concurrentVoiceAndGuardianStartsAreSerializedPerSenior() throws Exception {
        runConcurrently(
            () -> processVoice("walk-voice-" + UUID.randomUUID()),
            () -> processGuardian("walk-app-" + UUID.randomUUID()));

        assertThat(scenarioRepository.findAll()).hasSize(1);
        assertThat(publisher.commands)
            .extracting(RobotCommand::type)
            .containsExactly(RobotCommandType.FOLLOW_START);
        assertThat(receiptRepository.findAll())
            .extracting(receipt -> receipt.getDisposition())
            .containsExactlyInAnyOrder(
                WalkRequestDisposition.ACCEPTED,
                WalkRequestDisposition.REJECTED_ACTIVE_SCENARIO);
        assertThat(receiptRepository.findAll())
            .extracting(receipt -> receipt.getIngress())
            .containsExactlyInAnyOrder(
                WalkRequestIngress.MQTT,
                WalkRequestIngress.GUARDIAN_REST);
    }

    @Test
    void concurrentSameRequestIdAcrossRobotsClaimsBeforeCreatingScenario() throws Exception {
        String otherDeviceId = "walk-other-" + UUID.randomUUID();
        transactions.executeWithoutResult(ignored -> {
            UUID otherSeniorId = appUserRepository.saveAndFlush(
                AppUser.create("SENIOR", "다른 산책 동시성 테스트 시니어")).getId();
            robotRepository.saveAndFlush(Robot.create(otherSeniorId, otherDeviceId));
        });
        String requestId = "walk-reused-" + UUID.randomUUID();

        runConcurrently(
            () -> processVoice(requestId, deviceId),
            () -> processVoice(requestId, otherDeviceId));

        assertThat(scenarioRepository.findAll()).hasSize(1);
        assertThat(receiptRepository.findAll()).hasSize(1);
        assertThat(publisher.commands)
            .extracting(RobotCommand::type)
            .containsExactly(RobotCommandType.FOLLOW_START);
    }

    @Test
    void concurrentDuplicateUnknownRobotRequestReturnsOneDurableRejection() throws Exception {
        String requestId = "walk-unknown-" + UUID.randomUUID();
        String unknownDeviceId = "unknown-" + UUID.randomUUID();

        runConcurrently(
            () -> processGuardian(requestId, unknownDeviceId),
            () -> processGuardian(requestId, unknownDeviceId));

        assertThat(scenarioRepository.findAll()).isEmpty();
        assertThat(receiptRepository.findAll()).singleElement()
            .extracting(receipt -> receipt.getDisposition())
            .isEqualTo(WalkRequestDisposition.REJECTED_UNKNOWN_ROBOT);
        assertThat(publisher.commands).isEmpty();
    }

    @Test
    void concurrentStopsCreateOneFollowStopCommand() throws Exception {
        transactions.executeWithoutResult(ignored -> processVoice("walk-before-two-stops"));
        Scenario starting = scenarioRepository.findAll().get(0);
        transactions.executeWithoutResult(ignored -> orchestrator.onFollowResult(
            "follow-started-event",
            starting.getId(),
            deviceId,
            starting.getFollowStartCommandId(),
            occurredAt.plusSeconds(1),
            "SUCCEEDED",
            "STARTED",
            null));
        publisher.commands.clear();

        runConcurrently(
            () -> processGuardianStop("walk-stop-one-" + UUID.randomUUID()),
            () -> processGuardianStop("walk-stop-two-" + UUID.randomUUID()));

        Scenario stopping = scenarioRepository.findById(starting.getId()).orElseThrow();
        assertThat(stopping.getFinalStatus()).isEqualTo(ScenarioStatus.STOPPING_FOLLOW);
        assertThat(stopping.getFollowStopCommandId()).isNotBlank();
        assertThat(publisher.commands)
            .extracting(RobotCommand::type)
            .containsExactly(RobotCommandType.FOLLOW_STOP);
        assertThat(receiptRepository.findAll())
            .extracting(receipt -> receipt.getDisposition())
            .containsExactlyInAnyOrder(
                WalkRequestDisposition.ACCEPTED,
                WalkRequestDisposition.ACCEPTED,
                WalkRequestDisposition.NO_OP_ALREADY_STOPPING);
    }

    @Test
    void newOrchestratorInstanceFindsPersistedWalkAndStopsSameScenario() {
        transactions.executeWithoutResult(ignored -> processVoice("walk-before-restart"));
        Scenario started = scenarioRepository.findAll().get(0);
        UUID scenarioId = started.getId();
        String startCommandId = started.getFollowStartCommandId();
        transactions.executeWithoutResult(ignored -> orchestrator.onFollowResult(
            "follow-started-before-restart",
            scenarioId,
            deviceId,
            startCommandId,
            occurredAt.plusSeconds(1),
            "SUCCEEDED",
            "STARTED",
            null));

        WalkOrchestrator afterRestart = newOrchestrator();
        transactions.executeWithoutResult(ignored -> afterRestart.handleGuardianRequest(
            "walk-stop-after-restart", deviceId, WalkAction.STOP));

        Scenario stopping = scenarioRepository.findById(scenarioId).orElseThrow();
        assertThat(stopping.getFinalStatus()).isEqualTo(ScenarioStatus.STOPPING_FOLLOW);
        assertThat(stopping.getFollowStartCommandId()).isEqualTo(startCommandId);
        assertThat(stopping.getFollowStopCommandId()).isNotBlank().isNotEqualTo(startCommandId);
        assertThat(scenarioRepository.findAll()).hasSize(1);
        assertThat(publisher.commands)
            .extracting(RobotCommand::type)
            .containsExactly(RobotCommandType.FOLLOW_START, RobotCommandType.FOLLOW_STOP);
        assertThat(publisher.commands)
            .extracting(RobotCommand::scenarioId)
            .containsOnly(scenarioId);
    }

    private WalkOrchestrator newOrchestrator() {
        return new WalkOrchestrator(
            scenarioRepository,
            receiptRepository,
            robotRepository,
            List.of(publisher),
            new ScenarioStartGuard(scenarioRepository, appUserRepository),
            new WalkTimeoutProperties(),
            clock);
    }

    private void processVoice(String requestId) {
        processVoice(requestId, deviceId);
    }

    private void processVoice(String requestId, String targetDeviceId) {
        orchestrator.handleRequest(new WalkRequest(
            WalkRequestIngress.MQTT,
            requestId,
            targetDeviceId,
            WalkAction.START,
            WalkRequestSource.VOICE,
            null,
            occurredAt));
    }

    private void processGuardian(String requestId) {
        processGuardian(requestId, deviceId);
    }

    private void processGuardian(String requestId, String targetDeviceId) {
        orchestrator.handleGuardianRequest(requestId, targetDeviceId, WalkAction.START);
    }

    private void processGuardianStop(String requestId) {
        orchestrator.handleGuardianRequest(requestId, deviceId, WalkAction.STOP);
    }

    private void runConcurrently(Runnable first, Runnable second) throws Exception {
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

    private void runWhenReleased(
        Runnable task,
        CountDownLatch ready,
        CountDownLatch start
    ) {
        ready.countDown();
        try {
            start.await();
            transactions.executeWithoutResult(ignored -> task.run());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Concurrent WALK test was interrupted", ex);
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
