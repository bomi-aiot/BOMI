package com.ssafy.bomi.scenario.repository;

import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ScenarioRepository extends JpaRepository<Scenario, UUID> {

    /**
     * 이 어르신에게 주어진 상태들 중 하나인 시나리오가 존재하는가.
     *
     * <p>{@code statuses}에 {@link ScenarioStatus#activeStatuses()}를 넘기면
     * "지금 돌고 있는 시나리오가 있는가"가 된다. 새 시나리오 시작 전의 교통정리
     * ({@code ScenarioStartGuard})가 사용한다.</p>
     */
    boolean existsBySeniorIdAndFinalStatusIn(UUID seniorId, Collection<ScenarioStatus> statuses);

    /**
     * 이 어르신에게 같은 타입의 시나리오가 주어진 상태로 {@code after} 이후에
     * 갱신된 적이 있는가.
     *
     * <p>{@code finalStatus=COMPLETED}, {@code after=now-쿨다운}으로 부르면
     * "최근에 같은 시나리오를 이미 끝냈는가"(쿨다운 판정)가 된다. updated_at 은
     * 마지막 상태 전이 시각이므로 터미널 상태 행에서는 종료 시각을 뜻한다.</p>
     */
    boolean existsBySeniorIdAndScenarioTypeAndFinalStatusAndUpdatedAtAfter(
        UUID seniorId, ScenarioType scenarioType, ScenarioStatus finalStatus, OffsetDateTime after);
}
