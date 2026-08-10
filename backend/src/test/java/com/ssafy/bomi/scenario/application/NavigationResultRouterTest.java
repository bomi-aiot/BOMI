package com.ssafy.bomi.scenario.application;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

class NavigationResultRouterTest {

    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final HomecomingOrchestrator conversationOrchestrator =
        mock(HomecomingOrchestrator.class);
    private final WakeWordCallOrchestrator wakeWordOrchestrator =
        mock(WakeWordCallOrchestrator.class);
    private final NavigationResultRouter router = new NavigationResultRouter(
        scenarioRepository, conversationOrchestrator, wakeWordOrchestrator);

    @Test
    void wakeWordResultIsDelegatedOnlyToWakeWordOrchestrator() {
        Scenario scenario = scenario(ScenarioType.WAKE_WORD_CALL);
        when(scenarioRepository.findById(scenario.getId())).thenReturn(Optional.of(scenario));

        router.route(
            scenario.getId(), "robot-01", "cmd-01", false,
            "SUCCEEDED", "ARRIVED", null);

        verify(wakeWordOrchestrator).onNavigationResult(
            scenario.getId(), "robot-01", "cmd-01", false,
            "SUCCEEDED", "ARRIVED", null);
        verifyNoInteractions(conversationOrchestrator);
    }

    @Test
    void existingConversationScenarioStillUsesExistingOrchestrator() {
        Scenario scenario = scenario(ScenarioType.WELLNESS_CHECK);
        when(scenarioRepository.findById(scenario.getId())).thenReturn(Optional.of(scenario));

        router.route(
            scenario.getId(), "robot-01", "cmd-02", false,
            "FAILED", "NOT_ARRIVED", "PATH_BLOCKED");

        verify(conversationOrchestrator).onNavigationFailed(
            scenario.getId(), "robot-01", "cmd-02", false);
        verifyNoInteractions(wakeWordOrchestrator);
    }

    @Test
    void reservedAndUnknownScenariosAreIgnored() {
        Scenario reserved = scenario(ScenarioType.FALL_RESPONSE);
        UUID unknownId = UUID.randomUUID();
        when(scenarioRepository.findById(reserved.getId())).thenReturn(Optional.of(reserved));
        when(scenarioRepository.findById(unknownId)).thenReturn(Optional.empty());

        router.route(
            reserved.getId(), "robot-01", "cmd-03", false,
            "SUCCEEDED", "ARRIVED", null);
        router.route(
            unknownId, "robot-01", "cmd-04", false,
            "SUCCEEDED", "ARRIVED", null);

        verify(conversationOrchestrator, never()).onRobotArrived(
            reserved.getId(), "robot-01", "cmd-03", false);
        verifyNoInteractions(wakeWordOrchestrator);
    }

    @Test
    void lateResultAfterOperatorCancellationIsIgnored() {
        Scenario scenario = scenario(ScenarioType.HOMECOMING);
        scenario.cancel("CANCELLED", "OPERATOR_CANCELLED");
        when(scenarioRepository.findById(scenario.getId())).thenReturn(Optional.of(scenario));

        router.route(
            scenario.getId(), "robot-01", "navigate-01", false,
            "CANCELLED", "NOT_ARRIVED", "OPERATOR_CANCELLED");

        verifyNoInteractions(conversationOrchestrator, wakeWordOrchestrator);
    }

    private static Scenario scenario(ScenarioType type) {
        Scenario scenario = Scenario.create(UUID.randomUUID(), UUID.randomUUID(), type);
        ReflectionTestUtils.setField(scenario, "id", UUID.randomUUID());
        return scenario;
    }
}
