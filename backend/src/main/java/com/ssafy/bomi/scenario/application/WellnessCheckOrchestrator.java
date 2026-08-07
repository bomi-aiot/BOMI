package com.ssafy.bomi.scenario.application;

import com.fasterxml.jackson.databind.JsonNode;
import com.ssafy.bomi.conversation.domain.ConversationIntent;
import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.observation.application.ObservationContract;
import com.ssafy.bomi.observation.config.ObservationProperties;
import com.ssafy.bomi.observation.config.WellnessProperties;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * WELLNESS_CHECK 시나리오의 시작만 담당한다: 온습도 관측이 임계값을 넘으면
 * 어르신 위치(LIVING_ROOM)로 이동해 안부를 묻는다.
 *
 * <p><b>시작 이후는 이 클래스의 일이 아니다.</b> 도착·대화 종료·복귀·실패 처리는
 * scenarioId 기준이라 시나리오 타입과 무관하고, 기존
 * {@link HomecomingOrchestrator#onRobotArrived}/{@code onConversationEnded}/
 * {@code onNavigationFailed} 가 그대로 이 시나리오도 끌고 간다. 상태 경로도
 * HOMECOMING 과 같은 선형 경로를 공유한다.</p>
 *
 * <p>온습도는 연속 신호라("더운 방은 5분 뒤에도 덥다") 같은 이유로 시나리오가
 * 무한 생성될 수 있다. {@link ScenarioStartGuard}에 쿨다운을 걸어 막는다 —
 * 문 열림(이산 사건)과 달리 이 시나리오는 쿨다운이 필수다.</p>
 */
@Service
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class WellnessCheckOrchestrator {

    private static final Logger log = LoggerFactory.getLogger(WellnessCheckOrchestrator.class);
    private static final Duration COMMAND_TTL = Duration.ofMinutes(2);

    /** 임계값 초과 시 안부 문구. 원인(더위/습함)을 특정하지 않는 중립 문장. */
    static final String DEFAULT_PROMPT = "어르신, 방 안 공기가 심상치 않네요. 좀 어떠세요?";

    private final ScenarioRepository scenarioRepository;
    private final RobotRepository robotRepository;
    private final RobotCommandPublisher commandPublisher;
    private final ScenarioRobotStartPolicy startPolicy;
    private final ObservationProperties observationProperties;
    private final WellnessProperties wellnessProperties;

    public WellnessCheckOrchestrator(
        ScenarioRepository scenarioRepository,
        RobotRepository robotRepository,
        RobotCommandPublisher commandPublisher,
        ScenarioRobotStartPolicy startPolicy,
        ObservationProperties observationProperties,
        WellnessProperties wellnessProperties
    ) {
        this.scenarioRepository = scenarioRepository;
        this.robotRepository = robotRepository;
        this.commandPublisher = commandPublisher;
        this.startPolicy = startPolicy;
        this.observationProperties = observationProperties;
        this.wellnessProperties = wellnessProperties;
    }

    /**
     * 온습도 관측 수신 시 호출된다 ({@code AmbientObservedHandler}, 기록 이후).
     *
     * <p>임계값 미만이면 아무 일도 하지 않는다 — 관측 기록 자체는 이미
     * {@code RobotObservationService}가 끝냈고, 여기는 "행동할 것인가"만 판단한다.</p>
     */
    @Transactional
    public void onAmbientObserved(String sensorId, JsonNode body) {
        JsonNode payload = ObservationContract.payload(body);
        BigDecimal temperature =
            ObservationContract.optionalDecimal(payload, ObservationContract.TEMPERATURE_KEY);
        BigDecimal humidity =
            ObservationContract.optionalDecimal(payload, ObservationContract.HUMIDITY_KEY);

        if (!exceedsThreshold(temperature, humidity)) {
            return;
        }

        UUID seniorId = observationProperties.findSenior(sensorId).orElse(null);
        if (seniorId == null) {
            // 매핑 누락은 기록 단계(RobotObservationService)에서 이미 경고했다.
            return;
        }

        var admission = startPolicy.admitBySenior(
            seniorId,
            ScenarioType.WELLNESS_CHECK,
            wellnessProperties.cooldown(),
            ScenarioRobotStartPolicy.ModePolicy.IDLE_ONLY);
        if (!admission.allowed()) {
            log.info("Wellness check suppressed ({}): seniorId={}, temp={}, humidity={}",
                admission.blockReason(), seniorId, temperature, humidity);
            return;
        }

        Robot robot = admission.robot();
        if (robot == null) {
            // 예외를 던지면 ack 가 생략되어 브로커가 무한 재전송한다(A-3과 같은 원리).
            // 로봇 미배정은 재전송으로 해결되는 문제가 아니므로 경고 후 폐기한다.
            log.warn("No robot assigned to senior; dropping wellness check: seniorId={}", seniorId);
            return;
        }

        Scenario scenario = Scenario.create(
            seniorId, robot.getId(), ScenarioType.WELLNESS_CHECK, sensorId);
        scenario.prepareConversation(
            ConversationIntent.WELLNESS_CHECK,
            DEFAULT_PROMPT,
            conversationContext(sensorId, temperature, humidity));
        scenario.beginMovingToEntrance(); // "시나리오 목적지로 이동 중"의 범용 의미 (ScenarioType 참고)
        String navigationCommandId = UUID.randomUUID().toString();
        scenario.expectNavigationResult(
            navigationCommandId, HomecomingContract.TARGET_LIVING_ROOM);
        scenarioRepository.save(scenario);

        robot.changeMode(RobotModePolicy.forScenario(scenario.getFinalStatus()));
        robotRepository.save(robot);

        // 대화 요청은 위에서 시나리오에 보존하고, 목적지 도착이 확인된 뒤
        // HomecomingOrchestrator가 START_CONVERSATION으로 AI Chat에 전달한다.
        publish(navigationCommandId, scenario.getId(), robot, RobotCommandType.NAVIGATE,
            Map.of(HomecomingContract.NAV_TARGET_KEY, HomecomingContract.TARGET_LIVING_ROOM));

        log.info("Wellness check started: scenarioId={}, seniorId={}, temp={}, humidity={}",
            scenario.getId(), seniorId, temperature, humidity);
    }

    /** null 은 "측정값 없음"이며 임계값 비교에 참여하지 않는다. */
    private boolean exceedsThreshold(BigDecimal temperature, BigDecimal humidity) {
        boolean tooHot = temperature != null
            && temperature.compareTo(wellnessProperties.getTemperatureThresholdC()) >= 0;
        boolean tooHumid = humidity != null
            && humidity.compareTo(wellnessProperties.getHumidityThresholdPercent()) >= 0;
        return tooHot || tooHumid;
    }

    private static Map<String, Object> conversationContext(
        String sensorId,
        BigDecimal temperature,
        BigDecimal humidity
    ) {
        Map<String, Object> context = new LinkedHashMap<>();
        context.put("sourceId", sensorId);
        context.put("location", HomecomingContract.TARGET_LIVING_ROOM);
        if (temperature != null) {
            context.put(ObservationContract.TEMPERATURE_KEY, temperature);
        }
        if (humidity != null) {
            context.put(ObservationContract.HUMIDITY_KEY, humidity);
        }
        return context;
    }

    private void publish(
        String commandId,
        UUID scenarioId,
        Robot robot,
        RobotCommandType type,
        Map<String, Object> payload
    ) {
        if (robot.getDeviceId() == null) {
            throw new IllegalStateException("Robot has no deviceId; cannot address command: " + robot.getId());
        }
        OffsetDateTime now = OffsetDateTime.now();
        commandPublisher.publish(new RobotCommand(
            commandId, scenarioId, robot.getDeviceId(),
            type, now, now.plus(COMMAND_TTL), payload));
    }
}
