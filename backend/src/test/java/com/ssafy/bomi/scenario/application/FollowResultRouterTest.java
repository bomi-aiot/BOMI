package com.ssafy.bomi.scenario.application;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * 두 시나리오가 FOLLOW_START 를 공유하므로 결과의 주인을 골라 줘야 한다.
 *
 * <p>가장 중요한 것은 산책 시나리오가 영향을 받지 않는 것이다 — 보미야 호출만
 * 새 경로로 가고 나머지는 전부 기존 경로 그대로여야 한다.</p>
 */
class FollowResultRouterTest {

    private static final OffsetDateTime OCCURRED_AT =
        OffsetDateTime.parse("2026-08-06T16:00:00+09:00");

    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final WakeWordCallOrchestrator wakeWordOrchestrator =
        mock(WakeWordCallOrchestrator.class);
    private final HomecomingOrchestrator homecomingOrchestrator =
        mock(HomecomingOrchestrator.class);
    private final WalkOrchestrator walkOrchestrator = mock(WalkOrchestrator.class);
    private final FollowResultRouter router = new FollowResultRouter(
        scenarioRepository, wakeWordOrchestrator, homecomingOrchestrator, walkOrchestrator);

    @Test
    void wakeWordFollowResultGoesOnlyToTheWakeWordOrchestrator() {
        Scenario scenario = scenario(ScenarioType.WAKE_WORD_CALL);
        when(scenarioRepository.findById(scenario.getId())).thenReturn(Optional.of(scenario));

        router.route(
            "evt-01", scenario.getId(), "robot-01", "cmd-01", OCCURRED_AT,
            "SUCCEEDED", "STARTED", null);

        verify(wakeWordOrchestrator).onFollowResult(
            scenario.getId(), "robot-01", "cmd-01", false,
            "SUCCEEDED", "STARTED", null);
        verifyNoInteractions(walkOrchestrator);
    }

    @Test
    void walkFollowResultStillGoesToTheWalkOrchestrator() {
        Scenario scenario = scenario(ScenarioType.WALK);
        when(scenarioRepository.findById(scenario.getId())).thenReturn(Optional.of(scenario));

        router.route(
            "evt-02", scenario.getId(), "robot-01", "cmd-02", OCCURRED_AT,
            "FAILED", "STOPPED", "PERSON_LOST");

        verify(walkOrchestrator).onFollowResult(
            "evt-02", scenario.getId(), "robot-01", "cmd-02", OCCURRED_AT,
            "FAILED", "STOPPED", "PERSON_LOST");
        verifyNoInteractions(wakeWordOrchestrator);
    }

    @Test
    void homecomingFollowResultGoesOnlyToTheHomecomingOrchestrator() {
        Scenario scenario = scenario(ScenarioType.HOMECOMING);
        when(scenarioRepository.findById(scenario.getId())).thenReturn(Optional.of(scenario));

        router.route(
            "evt-home", scenario.getId(), "robot-01", "cmd-home", OCCURRED_AT,
            "SUCCEEDED", "STARTED", null);

        verify(homecomingOrchestrator).onFollowResult(
            "evt-home", scenario.getId(), "robot-01", "cmd-home", OCCURRED_AT,
            "SUCCEEDED", "STARTED", null);
        verifyNoInteractions(wakeWordOrchestrator, walkOrchestrator);
    }

    @Test
    void unknownScenarioKeepsThePreviousBehaviour() {
        // 라우터를 넣기 전에는 모르는 시나리오도 산책 오케스트레이터가 받아
        // 로그를 남겼다. 그 동작을 바꾸지 않는다.
        UUID unknownId = UUID.randomUUID();
        when(scenarioRepository.findById(unknownId)).thenReturn(Optional.empty());

        router.route(
            "evt-03", unknownId, "robot-01", "cmd-03", OCCURRED_AT,
            "SUCCEEDED", "STOPPED", null);

        verify(walkOrchestrator).onFollowResult(
            "evt-03", unknownId, "robot-01", "cmd-03", OCCURRED_AT,
            "SUCCEEDED", "STOPPED", null);
        verifyNoInteractions(wakeWordOrchestrator);
    }

    private static Scenario scenario(ScenarioType type) {
        Scenario scenario = Scenario.create(UUID.randomUUID(), UUID.randomUUID(), type);
        ReflectionTestUtils.setField(scenario, "id", UUID.randomUUID());
        return scenario;
    }
}
