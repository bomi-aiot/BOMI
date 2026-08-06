package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationIntent;
import com.ssafy.bomi.conversation.domain.ConversationOutcome;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.HomecomingProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
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
class HomecomingOrchestratorConcurrencyTest {

    private static final OffsetDateTime NOW =
        OffsetDateTime.parse("2026-08-06T10:00:00+09:00");
    private static final long CONCURRENCY_TIMEOUT_SECONDS = 5;

    @Autowired ScenarioRepository scenarioRepository;
    @Autowired ConversationRepository conversationRepository;
    @Autowired RobotRepository robotRepository;
    @Autowired AppUserRepository appUserRepository;
    @Autowired PlatformTransactionManager transactionManager;

    private TransactionTemplate transactions;
    private RecordingPublisher publisher;
    private HomecomingOrchestrator orchestrator;
    private UUID scenarioId;
    private UUID conversationId;
    private String deviceId;

    @BeforeEach
    void setUp() {
        transactions = new TransactionTemplate(transactionManager);
        publisher = new RecordingPublisher();
        deviceId = "homecoming-lock-order-" + UUID.randomUUID();
        Clock clock = Clock.fixed(
            Instant.parse("2026-08-06T01:00:00Z"), ZoneOffset.UTC);

        ScenarioStartGuard startGuard =
            new ScenarioStartGuard(scenarioRepository, appUserRepository);
        orchestrator = new HomecomingOrchestrator(
            scenarioRepository,
            conversationRepository,
            robotRepository,
            publisher,
            ignored -> ConversationStartResult.published(UUID.randomUUID()),
            new HomecomingProperties(),
            new ScenarioRobotStartPolicy(startGuard, robotRepository, scenarioRepository),
            clock);

        transactions.executeWithoutResult(ignored -> {
            UUID seniorId = appUserRepository.saveAndFlush(
                AppUser.create("SENIOR", "conversation lock-order senior")).getId();
            Robot robot = Robot.create(seniorId, deviceId);
            robot.changeMode(RobotMode.SCENARIO_ACTIVE);
            UUID robotId = robotRepository.saveAndFlush(robot).getId();

            Scenario scenario = Scenario.create(
                seniorId, robotId, ScenarioType.HOMECOMING, "door-lock-order-event");
            scenario.prepareConversation(
                ConversationIntent.HOMECOMING_GREETING,
                "Welcome home",
                Map.of("location", "ENTRANCE"));
            scenario.beginMovingToEntrance();
            scenario.checkInteraction();
            scenario.beginConversation();
            scenarioId = scenarioRepository.saveAndFlush(scenario).getId();

            Conversation conversation = Conversation.requestForScenario(
                seniorId, scenarioId, "ai-lock-order-command", NOW.minusMinutes(10));
            conversation.markAiStarted(NOW.minusMinutes(9));
            conversationId = conversationRepository.saveAndFlush(conversation).getId();
        });
    }

    @AfterEach
    void cleanUp() {
        transactions.executeWithoutResult(ignored -> {
            conversationRepository.deleteAll();
            scenarioRepository.deleteAll();
            robotRepository.deleteAll();
            appUserRepository.deleteAll();
        });
    }

    @Test
    void conversationEndAndTimeoutCompleteWithoutLockOrderDeadlock() throws Exception {
        runConcurrently(
            () -> orchestrator.onConversationEnded(
                scenarioId,
                conversationId,
                deviceId,
                ConversationOutcome.COMPLETED,
                null,
                NOW),
            () -> orchestrator.onConversationActiveTimedOut(conversationId));

        Scenario scenario = scenarioRepository.findById(scenarioId).orElseThrow();
        Conversation conversation = conversationRepository.findById(conversationId).orElseThrow();

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.RETURNING_TO_DEFAULT);
        assertThat(conversation.getStatus()).isNotEqualTo(ConversationStatus.OPEN);
        assertThat(publisher.commands).hasSize(1);
    }

    private void runConcurrently(Runnable first, Runnable second) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        try {
            Future<?> one = executor.submit(() -> runWhenReleased(first, ready, start));
            Future<?> two = executor.submit(() -> runWhenReleased(second, ready, start));
            assertThat(ready.await(CONCURRENCY_TIMEOUT_SECONDS, TimeUnit.SECONDS)).isTrue();
            start.countDown();
            one.get(CONCURRENCY_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            two.get(CONCURRENCY_TIMEOUT_SECONDS, TimeUnit.SECONDS);
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
            if (!start.await(CONCURRENCY_TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Concurrent lock-order test did not start");
            }
            transactions.executeWithoutResult(ignored -> task.run());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Concurrent lock-order test was interrupted", ex);
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
