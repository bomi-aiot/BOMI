package com.ssafy.bomi.scenario.repository;

import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ScenarioRepository extends JpaRepository<Scenario, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select s from Scenario s where s.id = :id")
    java.util.Optional<Scenario> findByIdForUpdate(@Param("id") UUID id);

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

    /**
     * 이 타입의 시나리오가 주어진 외부 이벤트 키로 이미 만들어진 적이 있는가.
     *
     * <p>복약 알림의 "같은 슬롯 하루 1회" 판정에 쓴다. 슬롯 키가 곧 알림 이력이므로
     * 별도 테이블 없이 재시작에도 안전하다 (키 형식은 {@code ScenarioType} 참고).</p>
     */
    boolean existsByScenarioTypeAndExternalEventId(ScenarioType scenarioType, String externalEventId);

    /**
     * 주어진 상태들에 머물러 있으면서 {@code before} 이전에 마지막으로 갱신된 시나리오.
     *
     * <p>{@link ScenarioStatus#activeStatuses()}를 넘기면 "너무 오래 멈춰 있는 진행 중
     * 시나리오"가 된다. {@code updated_at}은 마지막 상태 전이 시각이므로, 이 값이 오래됐다는
     * 것은 그 상태에서 다음으로 넘어가는 이벤트가 한참 오지 않았다는 뜻이다.
     * {@code ScenarioTimeoutWatchdog}가 안전망으로 사용한다 — 대화 핸드오프가 아직 로깅
     * 스텁이거나 이벤트가 유실돼도, 그 어르신의 다음 시나리오가 영원히 막히지 않게 한다.</p>
    */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select s from Scenario s
        where s.finalStatus in :statuses and s.updatedAt < :before
        order by s.id
        """)
    List<Scenario> findByFinalStatusInAndUpdatedAtBefore(
        @Param("statuses") Collection<ScenarioStatus> statuses,
        @Param("before") OffsetDateTime before);
}
