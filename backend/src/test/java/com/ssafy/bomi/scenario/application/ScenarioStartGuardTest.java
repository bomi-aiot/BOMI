package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.scenario.application.ScenarioStartGuard.BlockReason;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class ScenarioStartGuardTest {

    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final ScenarioStartGuard guard = new ScenarioStartGuard(scenarioRepository);

    private final UUID seniorId = UUID.randomUUID();

    @Test
    void allowsWhenNothingActiveAndNoRecentCompletion() {
        Optional<BlockReason> blocked =
            guard.check(seniorId, ScenarioType.HOMECOMING, Duration.ofMinutes(30));

        assertThat(blocked).isEmpty();
    }

    @Test
    void blocksWhenAnotherScenarioIsActive() {
        when(scenarioRepository.existsBySeniorIdAndFinalStatusIn(eq(seniorId), anyCollection()))
            .thenReturn(true);

        Optional<BlockReason> blocked =
            guard.check(seniorId, ScenarioType.HOMECOMING, Duration.ZERO);

        assertThat(blocked).contains(BlockReason.ACTIVE_SCENARIO_EXISTS);
    }

    @Test
    void blocksWhenSameTypeCompletedWithinCooldown() {
        when(scenarioRepository.existsBySeniorIdAndScenarioTypeAndFinalStatusAndUpdatedAtAfter(
            eq(seniorId), eq(ScenarioType.HOMECOMING), eq(ScenarioStatus.COMPLETED),
            any(OffsetDateTime.class)))
            .thenReturn(true);

        Optional<BlockReason> blocked =
            guard.check(seniorId, ScenarioType.HOMECOMING, Duration.ofMinutes(30));

        assertThat(blocked).contains(BlockReason.COOLDOWN_ACTIVE);
    }

    @Test
    void zeroCooldownSkipsTheCooldownQueryEntirely() {
        // 문 열림 같은 이산 트리거는 쿨다운이 없다. Duration.ZERO 면 쿨다운 쿼리
        // 자체를 부르지 않아야 한다 (불필요한 DB 왕복 방지 + 의미의 명확성).
        Optional<BlockReason> blocked =
            guard.check(seniorId, ScenarioType.HOMECOMING, Duration.ZERO);

        assertThat(blocked).isEmpty();
        verify(scenarioRepository, never())
            .existsBySeniorIdAndScenarioTypeAndFinalStatusAndUpdatedAtAfter(
                any(), any(), any(), any());
    }
}
