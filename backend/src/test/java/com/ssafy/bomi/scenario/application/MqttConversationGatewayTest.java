package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationIntent;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.mqtt.outbound.AiConversationCommand;
import com.ssafy.bomi.mqtt.outbound.AiConversationCommandPublisher;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.AiConversationProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

class MqttConversationGatewayTest {

    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final ConversationRepository conversationRepository = mock(ConversationRepository.class);
    private final RobotRepository robotRepository = mock(RobotRepository.class);
    private final AiConversationCommandPublisher publisher = mock(AiConversationCommandPublisher.class);
    private final Clock clock = Clock.fixed(
        Instant.parse("2026-08-05T01:00:00Z"), ZoneOffset.UTC);

    private MqttConversationGateway gateway;
    private Scenario scenario;
    private Robot robot;

    @BeforeEach
    void setUp() {
        UUID seniorId = UUID.randomUUID();
        UUID robotId = UUID.randomUUID();
        scenario = Scenario.create(seniorId, robotId, ScenarioType.HOMECOMING);
        scenario.prepareConversation(
            ConversationIntent.HOMECOMING_GREETING,
            "다녀오셨어요? 오늘 외출은 어떠셨어요?",
            Map.of("sourceId", "door-01", "location", "ENTRANCE"));
        ReflectionTestUtils.setField(scenario, "id", UUID.randomUUID());
        robot = Robot.create(seniorId, "robot-01");
        ReflectionTestUtils.setField(robot, "id", robotId);

        when(scenarioRepository.findById(scenario.getId())).thenReturn(Optional.of(scenario));
        when(robotRepository.findById(robotId)).thenReturn(Optional.of(robot));
        when(conversationRepository.findByScenarioId(scenario.getId())).thenReturn(Optional.empty());
        when(conversationRepository.save(any(Conversation.class))).thenAnswer(invocation -> {
            Conversation conversation = invocation.getArgument(0);
            if (conversation.getId() == null) {
                ReflectionTestUtils.setField(conversation, "id", UUID.randomUUID());
            }
            return conversation;
        });
        gateway = new MqttConversationGateway(
            scenarioRepository,
            conversationRepository,
            robotRepository,
            publisher,
            new AiConversationProperties(),
            clock);
    }

    @Test
    void savesConversationBeforePublishingCorrelatedAiCommand() {
        ConversationStartResult result = gateway.startConversation(scenario.getId());

        assertThat(result.published()).isTrue();
        ArgumentCaptor<AiConversationCommand> commandCaptor =
            ArgumentCaptor.forClass(AiConversationCommand.class);
        verify(publisher).publish(commandCaptor.capture());
        AiConversationCommand command = commandCaptor.getValue();
        assertThat(command.scenarioId()).isEqualTo(scenario.getId());
        assertThat(command.conversationId()).isEqualTo(result.conversationId());
        assertThat(command.robotId()).isEqualTo("robot-01");
        assertThat(command.payload().intent()).isEqualTo(ConversationIntent.HOMECOMING_GREETING);
        assertThat(command.expiresAt()).isEqualTo(command.occurredAt().plusSeconds(10));
    }

    @Test
    void recordsFailureWhenMqttPublisherRejectsCommand() {
        doThrow(new IllegalStateException("broker unavailable"))
            .when(publisher).publish(any(AiConversationCommand.class));

        ConversationStartResult result = gateway.startConversation(scenario.getId());

        assertThat(result.published()).isFalse();
        ArgumentCaptor<Conversation> conversationCaptor =
            ArgumentCaptor.forClass(Conversation.class);
        verify(conversationRepository, org.mockito.Mockito.atLeast(2))
            .save(conversationCaptor.capture());
        Conversation failed = conversationCaptor.getAllValues().get(
            conversationCaptor.getAllValues().size() - 1);
        assertThat(failed.getStatus()).isEqualTo(ConversationStatus.FAILED);
        assertThat(failed.getReasonCode())
            .isEqualTo(MqttConversationGateway.REASON_AI_COMMAND_PUBLISH_FAILED);
    }

    @Test
    void doesNotPublishSecondCommandForExistingOpenConversation() {
        Conversation existing = Conversation.requestForScenario(
            scenario.getSeniorId(), scenario.getId(), "existing-command",
            java.time.OffsetDateTime.now(clock));
        ReflectionTestUtils.setField(existing, "id", UUID.randomUUID());
        when(conversationRepository.findByScenarioId(scenario.getId()))
            .thenReturn(Optional.of(existing));

        ConversationStartResult result = gateway.startConversation(scenario.getId());

        assertThat(result.conversationId()).isEqualTo(existing.getId());
        verify(publisher, never()).publish(any());
    }
}
