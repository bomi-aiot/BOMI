package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.mqtt.inbound.MqttContractViolationException;
import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.WalkTimeoutProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.domain.WalkAction;
import com.ssafy.bomi.scenario.domain.WalkRequestDisposition;
import com.ssafy.bomi.scenario.domain.WalkRequestIngress;
import com.ssafy.bomi.scenario.domain.WalkRequestReceipt;
import com.ssafy.bomi.scenario.domain.WalkRequestSource;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.scenario.repository.WalkRequestReceiptRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.test.util.ReflectionTestUtils;

class WalkOrchestratorTest {

    private static final OffsetDateTime NOW =
        OffsetDateTime.parse("2026-08-05T16:00:00+09:00");

    @Test
    void startCreatesOneWalkAndPublishesEmptyFollowStartCommand() {
        Fixture fixture = new Fixture();
        UUID conversationId = UUID.randomUUID();

        WalkRequestResult result = fixture.orchestrator.handleRequest(
            fixture.voice("walk-start-01", WalkAction.START, conversationId, NOW));

        Scenario scenario = fixture.onlyScenario();
        assertThat(result.accepted()).isTrue();
        assertThat(result.duplicate()).isFalse();
        assertThat(result.scenarioId()).isEqualTo(scenario.getId());
        assertThat(result.status()).isEqualTo(ScenarioStatus.STARTING_FOLLOW);
        assertThat(scenario.getScenarioType()).isEqualTo(ScenarioType.WALK);
        assertThat(scenario.getExternalEventId()).isEqualTo("walk-start-01");
        assertThat(scenario.getTriggerContext())
            .containsEntry("ingress", "MQTT")
            .containsEntry("source", "VOICE")
            .containsEntry("conversationId", conversationId.toString())
            .containsEntry("occurredAt", NOW.toString());
        assertThat(fixture.robot.getCurrentMode()).isEqualTo(RobotMode.SCENARIO_ACTIVE);
        assertThat(fixture.receipts).hasSize(1);

        assertThat(fixture.publisher.commands).singleElement().satisfies(command -> {
            assertThat(command.type()).isEqualTo(RobotCommandType.FOLLOW_START);
            assertThat(command.scenarioId()).isEqualTo(scenario.getId());
            assertThat(command.robotId()).isEqualTo(fixture.deviceId);
            assertThat(command.commandId()).isEqualTo(scenario.getFollowStartCommandId());
            assertThat(command.payload()).isEmpty();
            assertThat(command.occurredAt()).isEqualTo(NOW);
            assertThat(command.expiresAt()).isEqualTo(NOW.plusSeconds(10));
        });
    }

    @Test
    void startedResultMovesSameScenarioToFollowingAndKeepsStartCorrelation() {
        Fixture fixture = new Fixture();
        Scenario scenario = fixture.startWalk();
        String startCommandId = scenario.getFollowStartCommandId();

        fixture.started(scenario, "evt-started-01");

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.FOLLOWING);
        assertThat(scenario.getFollowStartCommandId()).isEqualTo(startCommandId);
        assertThat(scenario.getFollowStopCommandId()).isNull();
        assertThat(scenario.getLastFollowResultEventId()).isEqualTo("evt-started-01");
        assertThat(scenario.getLastFollowResultCode()).isEqualTo("STARTED");
        assertThat(scenario.getFollowingStartedAt()).isEqualTo(NOW);
        assertThat(fixture.publisher.commands).hasSize(1);
    }

    @Test
    void stopUsesSameScenarioAndDistinctCommandThenStoppedCompletesIdle() {
        Fixture fixture = new Fixture();
        Scenario scenario = fixture.startWalk();
        fixture.started(scenario, "evt-started-stop-flow");
        String startCommandId = scenario.getFollowStartCommandId();

        WalkRequestResult stop = fixture.orchestrator.handleRequest(
            fixture.voice("walk-stop-01", WalkAction.STOP, null, NOW.plusMinutes(10)));

        assertThat(stop.accepted()).isTrue();
        assertThat(stop.scenarioId()).isEqualTo(scenario.getId());
        assertThat(stop.status()).isEqualTo(ScenarioStatus.STOPPING_FOLLOW);
        assertThat(scenario.getFollowStopCommandId())
            .isNotBlank()
            .isNotEqualTo(startCommandId);
        assertThat(fixture.publisher.commands).extracting(RobotCommand::type)
            .containsExactly(RobotCommandType.FOLLOW_START, RobotCommandType.FOLLOW_STOP);
        assertThat(fixture.publisher.commands.get(1).scenarioId()).isEqualTo(scenario.getId());
        assertThat(fixture.publisher.commands.get(1).payload()).isEmpty();

        fixture.result(
            scenario,
            "evt-stopped-01",
            scenario.getFollowStopCommandId(),
            "SUCCEEDED",
            "STOPPED",
            null);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(scenario.getCompletionResultCode()).isEqualTo("STOPPED");
        assertThat(fixture.robot.getCurrentMode()).isEqualTo(RobotMode.IDLE);
        assertThat(scenario.getFollowStartCommandId()).isEqualTo(startCommandId);
        assertThat(scenario.getFollowStopCommandId()).isNotNull();
        assertThat(fixture.publisher.commands).hasSize(2);
    }

    @Test
    void stopBeforeStartedPublishesOnceAndLateStartedCannotRestoreFollowing() {
        Fixture fixture = new Fixture();
        Scenario scenario = fixture.startWalk();
        String startCommandId = scenario.getFollowStartCommandId();

        fixture.orchestrator.handleRequest(
            fixture.voice("walk-stop-before-started", WalkAction.STOP, null, NOW.plusSeconds(1)));
        String stopCommandId = scenario.getFollowStopCommandId();
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.STOPPING_FOLLOW);
        assertThat(fixture.publisher.commands)
            .extracting(RobotCommand::type)
            .containsExactly(RobotCommandType.FOLLOW_START);

        fixture.result(
            scenario, "evt-late-started", startCommandId,
            "SUCCEEDED", "STARTED", null);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.STOPPING_FOLLOW);
        assertThat(scenario.getLastFollowResultEventId()).isEqualTo("evt-late-started");
        assertThat(scenario.getFollowingStartedAt()).isNotNull();
        assertThat(fixture.publisher.commands).hasSize(2);
        assertThat(fixture.publisher.commands.get(1).type())
            .isEqualTo(RobotCommandType.FOLLOW_STOP);
        assertThat(fixture.publisher.commands.get(1).commandId()).isEqualTo(stopCommandId);

        fixture.result(
            scenario, "evt-late-started", startCommandId,
            "SUCCEEDED", "STARTED", null);
        assertThat(fixture.publisher.commands).hasSize(2);

        fixture.result(
            scenario, "evt-stop-after-race", stopCommandId,
            "SUCCEEDED", "STOPPED", null);
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
    }

    @Test
    void selfStoppedWhileStoppingWinsAndLateExplicitStopResultIsIgnored() {
        Fixture fixture = new Fixture();
        Scenario scenario = fixture.startWalk();
        fixture.started(scenario, "evt-started-self-race");
        fixture.orchestrator.handleRequest(
            fixture.voice("stop-before-self-stop", WalkAction.STOP, null, NOW.plusMinutes(1)));
        String startCommandId = scenario.getFollowStartCommandId();
        String stopCommandId = scenario.getFollowStopCommandId();

        fixture.result(
            scenario, "evt-self-stop-wins", startCommandId,
            "SUCCEEDED", "STOPPED", null);
        fixture.result(
            scenario, "evt-explicit-stop-late", stopCommandId,
            "SUCCEEDED", "STOPPED", null);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(scenario.getLastFollowResultEventId()).isEqualTo("evt-self-stop-wins");
        assertThat(scenario.getLastFollowCommandId()).isEqualTo(startCommandId);
        assertThat(fixture.robot.getCurrentMode()).isEqualTo(RobotMode.IDLE);
    }

    @Test
    void unchangedIsAnIdempotentSuccessForBothStartAndStopCommands() {
        Fixture fixture = new Fixture();
        Scenario scenario = fixture.startWalk();

        fixture.result(
            scenario, "evt-start-unchanged", scenario.getFollowStartCommandId(),
            "SUCCEEDED", "UNCHANGED", null);
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.FOLLOWING);

        fixture.orchestrator.handleRequest(
            fixture.voice("stop-for-unchanged", WalkAction.STOP, null, NOW.plusMinutes(1)));
        fixture.result(
            scenario, "evt-stop-unchanged", scenario.getFollowStopCommandId(),
            "SUCCEEDED", "UNCHANGED", null);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(scenario.getCompletionResultCode()).isEqualTo("UNCHANGED");
        assertThat(fixture.robot.getCurrentMode()).isEqualTo(RobotMode.IDLE);
    }

    @Test
    void robotSelfStoppedUsesStartCommandAndCompletesWithoutFollowStop() {
        Fixture fixture = new Fixture();
        Scenario scenario = fixture.startWalk();
        fixture.started(scenario, "evt-started-self-stop");

        fixture.result(
            scenario,
            "evt-self-stopped",
            scenario.getFollowStartCommandId(),
            "SUCCEEDED",
            "STOPPED",
            null);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(scenario.getFollowStopCommandId()).isNull();
        assertThat(scenario.getLastFollowCommandId())
            .isEqualTo(scenario.getFollowStartCommandId());
        assertThat(fixture.robot.getCurrentMode()).isEqualTo(RobotMode.IDLE);
        assertThat(fixture.publisher.commands).hasSize(1);
    }

    @ParameterizedTest
    @CsvSource({
        "FAILED,PERSON_LOST,FAILED",
        "CANCELLED,SAFETY_STOP,CANCELLED",
        "TIMED_OUT,EXECUTION_TIMEOUT,TIMED_OUT"
    })
    void selfTerminationMapsRobotOutcomeExactly(
        String outcome,
        String reasonCode,
        ScenarioStatus expectedStatus
    ) {
        Fixture fixture = new Fixture();
        Scenario scenario = fixture.startWalk();
        fixture.started(scenario, "evt-started-terminal-map");

        fixture.result(
            scenario,
            "evt-self-terminal-" + outcome,
            scenario.getFollowStartCommandId(),
            outcome,
            "STOPPED",
            reasonCode);

        assertThat(scenario.getFinalStatus()).isEqualTo(expectedStatus);
        assertThat(scenario.getCompletionResultCode()).isEqualTo("STOPPED");
        assertThat(scenario.getCompletionReasonCode()).isEqualTo(reasonCode);
        assertThat(fixture.robot.getCurrentMode()).isEqualTo(RobotMode.SAFE_STOP);
    }

    @Test
    void failedExplicitStopEndsFailedAndSafeStop() {
        Fixture fixture = new Fixture();
        Scenario scenario = fixture.startWalk();
        fixture.started(scenario, "evt-started-explicit-failure");
        fixture.orchestrator.handleRequest(
            fixture.voice("walk-stop-failure", WalkAction.STOP, null, NOW.plusMinutes(1)));

        fixture.result(
            scenario,
            "evt-stop-failed",
            scenario.getFollowStopCommandId(),
            "FAILED",
            "UNCHANGED",
            "INTERNAL_ERROR");

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.FAILED);
        assertThat(scenario.getCompletionReasonCode()).isEqualTo("INTERNAL_ERROR");
        assertThat(fixture.robot.getCurrentMode()).isEqualTo(RobotMode.SAFE_STOP);
    }

    @Test
    void stopRemainsAllowedAfterRobotEntersSafeStopAndDoesNotClearItOnSuccess() {
        Fixture fixture = new Fixture();
        Scenario scenario = fixture.startWalk();
        fixture.started(scenario, "evt-started-before-external-safe-stop");
        fixture.robot.changeMode(RobotMode.SAFE_STOP);

        WalkRequestResult result = fixture.orchestrator.handleRequest(
            fixture.voice("stop-in-safe-stop", WalkAction.STOP, null, NOW.plusMinutes(1)));

        assertThat(result.accepted()).isTrue();
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.STOPPING_FOLLOW);
        assertThat(fixture.publisher.commands).extracting(RobotCommand::type)
            .containsExactly(RobotCommandType.FOLLOW_START, RobotCommandType.FOLLOW_STOP);

        fixture.result(
            scenario, "evt-stopped-in-safe-stop", scenario.getFollowStopCommandId(),
            "SUCCEEDED", "STOPPED", null);
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(fixture.robot.getCurrentMode()).isEqualTo(RobotMode.SAFE_STOP);
    }

    @Test
    void wrongRobotAndWrongCommandAreRejectedWithoutStateChange() {
        Fixture fixture = new Fixture();
        Scenario scenario = fixture.startWalk();

        assertThatThrownBy(() -> fixture.orchestrator.onFollowResult(
            "evt-wrong-robot",
            scenario.getId(),
            "different-robot",
            scenario.getFollowStartCommandId(),
            NOW.plusSeconds(1),
            "SUCCEEDED",
            "STARTED",
            null))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("robotId");
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.STARTING_FOLLOW);

        assertThatThrownBy(() -> fixture.result(
            scenario,
            "evt-wrong-command",
            "wrong-command-id",
            "SUCCEEDED",
            "STARTED",
            null))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("commandId");
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.STARTING_FOLLOW);
    }

    @Test
    void terminalWalkStillRejectsUncorrelatedLateResult() {
        Fixture fixture = new Fixture();
        Scenario scenario = fixture.startWalk();
        fixture.started(scenario, "evt-started-before-terminal-validation");
        fixture.result(
            scenario,
            "evt-terminal-completion",
            scenario.getFollowStartCommandId(),
            "SUCCEEDED",
            "STOPPED",
            null);

        assertThatThrownBy(() -> fixture.result(
            scenario,
            "evt-terminal-wrong-command",
            "wrong-command-id",
            "SUCCEEDED",
            "STOPPED",
            null))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("commandId");
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(scenario.getLastFollowResultEventId())
            .isEqualTo("evt-terminal-completion");
    }

    @Test
    void unknownScenarioIsIgnoredAndNonWalkScenarioIsRejected() {
        Fixture fixture = new Fixture();
        assertThatCode(() -> fixture.orchestrator.onFollowResult(
            "evt-unknown-scenario",
            UUID.randomUUID(),
            fixture.deviceId,
            "unknown-command",
            NOW,
            "SUCCEEDED",
            "STARTED",
            null)).doesNotThrowAnyException();

        Scenario homecoming = Scenario.create(
            fixture.seniorId, fixture.robotId, ScenarioType.HOMECOMING, "door-event");
        ReflectionTestUtils.setField(homecoming, "id", UUID.randomUUID());
        fixture.scenarios.put(homecoming.getId(), homecoming);

        assertThatThrownBy(() -> fixture.orchestrator.onFollowResult(
            "evt-non-walk",
            homecoming.getId(),
            fixture.deviceId,
            "command",
            NOW,
            "SUCCEEDED",
            "STARTED",
            null))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("not WALK");
    }

    @Test
    void duplicateStartStopAndResultsNeverCreateAnotherCommand() {
        Fixture fixture = new Fixture();
        WalkRequest startRequest = fixture.voice(
            "walk-start-duplicate", WalkAction.START, null, NOW);
        WalkRequestResult firstStart = fixture.orchestrator.handleRequest(startRequest);
        WalkRequestResult duplicateStart = fixture.orchestrator.handleRequest(startRequest);
        Scenario scenario = fixture.onlyScenario();

        assertThat(firstStart.accepted()).isTrue();
        assertThat(duplicateStart.accepted()).isTrue();
        assertThat(duplicateStart.duplicate()).isTrue();
        assertThat(duplicateStart.scenarioId()).isEqualTo(scenario.getId());
        assertThat(fixture.publisher.commands).hasSize(1);

        fixture.started(scenario, "evt-started-duplicate");
        fixture.started(scenario, "evt-started-duplicate");
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.FOLLOWING);

        WalkRequest stopRequest = fixture.voice(
            "walk-stop-duplicate", WalkAction.STOP, null, NOW.plusMinutes(1));
        WalkRequestResult firstStop = fixture.orchestrator.handleRequest(stopRequest);
        WalkRequestResult duplicateStop = fixture.orchestrator.handleRequest(stopRequest);

        assertThat(firstStop.accepted()).isTrue();
        assertThat(duplicateStop.accepted()).isTrue();
        assertThat(duplicateStop.duplicate()).isTrue();
        assertThat(fixture.publisher.commands).hasSize(2);

        fixture.result(
            scenario, "evt-stopped-duplicate", scenario.getFollowStopCommandId(),
            "SUCCEEDED", "STOPPED", null);
        fixture.result(
            scenario, "evt-stopped-duplicate", scenario.getFollowStopCommandId(),
            "SUCCEEDED", "STOPPED", null);
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(fixture.publisher.commands).hasSize(2);
    }

    @Test
    void differentStopWhileAlreadyStoppingIsAcceptedNoOpWithoutNewCommand() {
        Fixture fixture = new Fixture();
        Scenario scenario = fixture.startWalk();
        fixture.started(scenario, "evt-started-already-stopping");
        fixture.orchestrator.handleRequest(
            fixture.voice("stop-first", WalkAction.STOP, null, NOW.plusMinutes(1)));

        WalkRequestResult second = fixture.orchestrator.handleRequest(
            fixture.voice("stop-second", WalkAction.STOP, null, NOW.plusMinutes(2)));

        assertThat(second.accepted()).isTrue();
        assertThat(second.disposition())
            .isEqualTo(WalkRequestDisposition.NO_OP_ALREADY_STOPPING);
        assertThat(second.scenarioId()).isEqualTo(scenario.getId());
        assertThat(fixture.publisher.commands).hasSize(2);
    }

    @ParameterizedTest
    @CsvSource({
        "SAFE_STOP,REJECTED_SAFE_STOP",
        "REST_GUARD,REJECTED_REST_GUARD",
        "SCENARIO_ACTIVE,REJECTED_BUSY_MODE"
    })
    void startRejectsUnsafeOrBusyRobotModes(
        RobotMode mode,
        WalkRequestDisposition expected
    ) {
        Fixture fixture = new Fixture();
        fixture.robot.changeMode(mode);

        WalkRequestResult result = fixture.orchestrator.handleRequest(
            fixture.voice("start-mode-" + mode, WalkAction.START, null, NOW));

        assertThat(result.accepted()).isFalse();
        assertThat(result.disposition()).isEqualTo(expected);
        assertThat(fixture.scenarios).isEmpty();
        assertThat(fixture.publisher.commands).isEmpty();
    }

    @Test
    void startRejectsUnknownInactiveUnassignedAndActiveScenarioPolicies() {
        Fixture unknown = new Fixture();
        when(unknown.robotRepository.findByDeviceId(unknown.deviceId))
            .thenReturn(Optional.empty());
        assertThat(unknown.orchestrator.handleRequest(
            unknown.voice("start-unknown", WalkAction.START, null, NOW)).disposition())
            .isEqualTo(WalkRequestDisposition.REJECTED_UNKNOWN_ROBOT);

        Fixture inactive = new Fixture();
        inactive.robot.deactivate();
        assertThat(inactive.orchestrator.handleRequest(
            inactive.voice("start-inactive", WalkAction.START, null, NOW)).disposition())
            .isEqualTo(WalkRequestDisposition.REJECTED_INACTIVE_ROBOT);

        Fixture unassigned = new Fixture();
        unassigned.robot.unassignSenior();
        assertThat(unassigned.orchestrator.handleRequest(
            unassigned.voice("start-unassigned", WalkAction.START, null, NOW)).disposition())
            .isEqualTo(WalkRequestDisposition.REJECTED_UNASSIGNED_ROBOT);

        Fixture blocked = new Fixture();
        when(blocked.startGuard.check(
                blocked.seniorId, ScenarioType.WALK, java.time.Duration.ZERO))
            .thenReturn(Optional.of(ScenarioStartGuard.BlockReason.ACTIVE_SCENARIO_EXISTS));
        assertThat(blocked.orchestrator.handleRequest(
            blocked.voice("start-blocked", WalkAction.START, null, NOW)).disposition())
            .isEqualTo(WalkRequestDisposition.REJECTED_ACTIVE_SCENARIO);
    }

    @Test
    void noActiveWalkStopIsDurableNoOpAndCannotStopLaterWalkOnRetry() {
        Fixture fixture = new Fixture();
        WalkRequest oldStop = fixture.voice(
            "stop-without-walk", WalkAction.STOP, null, NOW);

        WalkRequestResult first = fixture.orchestrator.handleRequest(oldStop);
        assertThat(first.accepted()).isFalse();
        assertThat(first.disposition())
            .isEqualTo(WalkRequestDisposition.REJECTED_NO_ACTIVE_WALK);

        Scenario laterWalk = fixture.startWalk("later-walk-start");
        WalkRequestResult duplicate = fixture.orchestrator.handleRequest(oldStop);

        assertThat(duplicate.duplicate()).isTrue();
        assertThat(duplicate.disposition())
            .isEqualTo(WalkRequestDisposition.REJECTED_NO_ACTIVE_WALK);
        assertThat(laterWalk.getFinalStatus()).isEqualTo(ScenarioStatus.STARTING_FOLLOW);
        assertThat(fixture.publisher.commands).hasSize(1);
    }

    private static final class Fixture {
        private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
        private final WalkRequestReceiptRepository receiptRepository =
            mock(WalkRequestReceiptRepository.class);
        private final RobotRepository robotRepository = mock(RobotRepository.class);
        private final ScenarioStartGuard startGuard = mock(ScenarioStartGuard.class);
        private final RecordingPublisher publisher = new RecordingPublisher();
        private final WalkTimeoutProperties properties = new WalkTimeoutProperties();
        private final Clock clock = Clock.fixed(
            Instant.parse("2026-08-05T07:00:00Z"), ZoneOffset.UTC);
        private final UUID seniorId = UUID.randomUUID();
        private final UUID robotId = UUID.randomUUID();
        private final String deviceId = "robot-" + UUID.randomUUID();
        private final Robot robot = Robot.create(seniorId, deviceId);
        private final Map<UUID, Scenario> scenarios = new LinkedHashMap<>();
        private final Map<String, WalkRequestReceipt> receipts = new LinkedHashMap<>();
        private final WalkOrchestrator orchestrator;

        private Fixture() {
            ReflectionTestUtils.setField(robot, "id", robotId);
            when(robotRepository.findByDeviceId(deviceId)).thenReturn(Optional.of(robot));
            when(robotRepository.findByDeviceIdForUpdate(deviceId)).thenReturn(Optional.of(robot));
            when(robotRepository.findByIdForUpdate(robotId)).thenReturn(Optional.of(robot));
            when(robotRepository.save(any(Robot.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

            when(startGuard.check(eq(seniorId), eq(ScenarioType.WALK), any()))
                .thenReturn(Optional.empty());
            when(startGuard.lockSenior(seniorId)).thenReturn(true);

            when(scenarioRepository.saveAndFlush(any(Scenario.class)))
                .thenAnswer(invocation -> saveScenario(invocation.getArgument(0)));
            when(scenarioRepository.save(any(Scenario.class)))
                .thenAnswer(invocation -> saveScenario(invocation.getArgument(0)));
            when(scenarioRepository.findByIdForUpdate(any(UUID.class)))
                .thenAnswer(invocation -> Optional.ofNullable(
                    scenarios.get(invocation.getArgument(0))));
            when(scenarioRepository.findActiveWalkByRobotId(
                    eq(robotId), anyCollection()))
                .thenAnswer(invocation -> activeWalk());
            when(scenarioRepository.findActiveWalkByRobotIdForUpdate(
                    eq(robotId), anyCollection()))
                .thenAnswer(invocation -> activeWalk());

            when(receiptRepository.findByIngressAndRequestId(
                    any(WalkRequestIngress.class), anyString()))
                .thenAnswer(invocation -> Optional.ofNullable(receipts.get(receiptKey(
                    invocation.getArgument(0), invocation.getArgument(1)))));
            when(receiptRepository.insertIfAbsent(
                    any(UUID.class), anyString(), anyString(), anyString(), anyString(),
                    anyString(), nullable(UUID.class), any(OffsetDateTime.class)))
                .thenAnswer(invocation -> {
                    WalkRequestIngress ingress = WalkRequestIngress.valueOf(
                        invocation.getArgument(1));
                    String requestId = invocation.getArgument(2);
                    String key = receiptKey(ingress, requestId);
                    if (receipts.containsKey(key)) {
                        return 0;
                    }
                    WalkRequestReceipt receipt = WalkRequestReceipt.receive(
                        ingress,
                        requestId,
                        invocation.getArgument(3),
                        WalkAction.valueOf(invocation.getArgument(4)),
                        WalkRequestSource.valueOf(invocation.getArgument(5)),
                        invocation.getArgument(6),
                        invocation.getArgument(7));
                    ReflectionTestUtils.setField(receipt, "id", invocation.getArgument(0));
                    receipts.put(key, receipt);
                    return 1;
                });
            when(receiptRepository.saveAndFlush(any(WalkRequestReceipt.class)))
                .thenAnswer(invocation -> {
                    WalkRequestReceipt receipt = invocation.getArgument(0);
                    if (receipt.getId() == null) {
                        ReflectionTestUtils.setField(receipt, "id", UUID.randomUUID());
                    }
                    receipts.put(receiptKey(receipt.getIngress(), receipt.getRequestId()), receipt);
                    return receipt;
                });

            orchestrator = new WalkOrchestrator(
                scenarioRepository,
                receiptRepository,
                robotRepository,
                List.of(publisher),
                startGuard,
                properties,
                clock);
        }

        private WalkRequest voice(
            String requestId,
            WalkAction action,
            UUID conversationId,
            OffsetDateTime occurredAt
        ) {
            return new WalkRequest(
                WalkRequestIngress.MQTT,
                requestId,
                deviceId,
                action,
                WalkRequestSource.VOICE,
                conversationId,
                occurredAt);
        }

        private Scenario startWalk() {
            return startWalk("walk-start-" + UUID.randomUUID());
        }

        private Scenario startWalk(String requestId) {
            orchestrator.handleRequest(voice(requestId, WalkAction.START, null, NOW));
            return onlyScenario();
        }

        private void started(Scenario scenario, String eventId) {
            result(
                scenario,
                eventId,
                scenario.getFollowStartCommandId(),
                "SUCCEEDED",
                "STARTED",
                null);
        }

        private void result(
            Scenario scenario,
            String eventId,
            String commandId,
            String outcome,
            String resultCode,
            String reasonCode
        ) {
            orchestrator.onFollowResult(
                eventId,
                scenario.getId(),
                deviceId,
                commandId,
                NOW.plusSeconds(2),
                outcome,
                resultCode,
                reasonCode);
        }

        private Scenario onlyScenario() {
            assertThat(scenarios).hasSize(1);
            return scenarios.values().iterator().next();
        }

        private Scenario saveScenario(Scenario scenario) {
            if (scenario.getId() == null) {
                ReflectionTestUtils.setField(scenario, "id", UUID.randomUUID());
            }
            scenarios.put(scenario.getId(), scenario);
            return scenario;
        }

        private Optional<Scenario> activeWalk() {
            return scenarios.values().stream()
                .filter(scenario -> scenario.getScenarioType() == ScenarioType.WALK)
                .filter(scenario -> !scenario.isTerminated())
                .findFirst();
        }

        private static String receiptKey(WalkRequestIngress ingress, String requestId) {
            return ingress.name() + ":" + requestId;
        }
    }

    private static final class RecordingPublisher implements RobotCommandPublisher {
        private final List<RobotCommand> commands = new ArrayList<>();

        @Override
        public void publish(RobotCommand command) {
            commands.add(command);
        }
    }
}
