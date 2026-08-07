package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationOutcome;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.mqtt.outbound.AiConversationCommand;
import com.ssafy.bomi.mqtt.outbound.AiConversationCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.AiConversationCommandType;
import com.ssafy.bomi.mqtt.outbound.StartConversationPayload;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.AiConversationProperties;
import com.ssafy.bomi.scenario.domain.PreparedConversation;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** Persists a scenario conversation and publishes its MQTT command to AI Chat. */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class MqttConversationGateway implements ConversationGateway {

    public static final String REASON_AI_COMMAND_PUBLISH_FAILED = "AI_COMMAND_PUBLISH_FAILED";

    private static final Logger log = LoggerFactory.getLogger(MqttConversationGateway.class);

    private final ScenarioRepository scenarioRepository;
    private final ConversationRepository conversationRepository;
    private final RobotRepository robotRepository;
    private final AiConversationCommandPublisher commandPublisher;
    private final AiConversationProperties properties;
    private final Clock clock;

    public MqttConversationGateway(
        ScenarioRepository scenarioRepository,
        ConversationRepository conversationRepository,
        RobotRepository robotRepository,
        AiConversationCommandPublisher commandPublisher,
        AiConversationProperties properties,
        Clock clock
    ) {
        this.scenarioRepository = scenarioRepository;
        this.conversationRepository = conversationRepository;
        this.robotRepository = robotRepository;
        this.commandPublisher = commandPublisher;
        this.properties = properties;
        this.clock = clock;
    }

    @Override
    @Transactional
    public ConversationStartResult startConversation(UUID scenarioId) {
        Scenario scenario = scenarioRepository.findById(scenarioId)
            .orElseThrow(() -> new IllegalArgumentException("Unknown scenario: " + scenarioId));
        PreparedConversation prepared = scenario.requirePreparedConversation();
        Robot robot = robotRepository.findById(scenario.getRobotId())
            .orElseThrow(() -> new IllegalStateException(
                "Scenario references unknown robot: " + scenario.getRobotId()));
        if (robot.getDeviceId() == null || robot.getDeviceId().isBlank()) {
            throw new IllegalStateException("Robot has no deviceId: " + robot.getId());
        }

        var existing = conversationRepository.findByScenarioId(scenarioId);
        if (existing.isPresent()) {
            Conversation conversation = existing.get();
            if (conversation.isOpen()) {
                log.info("Conversation already requested; not publishing twice: scenarioId={}, "
                    + "conversationId={}", scenarioId, conversation.getId());
                return ConversationStartResult.published(conversation.getId());
            }
            String reason = conversation.getReasonCode() == null
                ? REASON_AI_COMMAND_PUBLISH_FAILED : conversation.getReasonCode();
            return ConversationStartResult.failed(conversation.getId(), reason);
        }

        OffsetDateTime now = OffsetDateTime.now(clock);
        String commandId = UUID.randomUUID().toString();
        Conversation conversation = conversationRepository.save(
            Conversation.requestForScenario(
                scenario.getSeniorId(), scenario.getId(), commandId, now));

        AiConversationCommand command = new AiConversationCommand(
            commandId,
            scenario.getId(),
            conversation.getId(),
            robot.getDeviceId(),
            AiConversationCommandType.START_CONVERSATION,
            now,
            now.plus(properties.getStartTimeout()),
            new StartConversationPayload(
                scenario.getSeniorId(),
                prepared.intent(),
                prepared.text(),
                prepared.triggerContext())
        );

        try {
            commandPublisher.publish(command);
            return ConversationStartResult.published(conversation.getId());
        } catch (RuntimeException ex) {
            conversation.end(
                ConversationOutcome.FAILED,
                REASON_AI_COMMAND_PUBLISH_FAILED,
                OffsetDateTime.now(clock));
            conversationRepository.save(conversation);
            log.warn("AI conversation command publish failed; scenario will return to DEFAULT: "
                + "scenarioId={}, conversationId={}", scenarioId, conversation.getId(), ex);
            return ConversationStartResult.failed(
                conversation.getId(), REASON_AI_COMMAND_PUBLISH_FAILED);
        }
    }
}
