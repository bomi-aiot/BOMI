package com.ssafy.bomi.scenario;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.ActiveProfiles;

@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class ScenarioRepositoryTest {

    @Autowired ScenarioRepository scenarioRepository;
    @Autowired TestEntityManager em;

    @Test
    void persistsEnumsWithDefaultStatus() {
        Scenario scenario = Scenario.create(
            UUID.randomUUID(), UUID.randomUUID(), ScenarioType.HOMECOMING, "door-open-01");
        Scenario saved = scenarioRepository.saveAndFlush(scenario);
        em.clear();

        Scenario found = scenarioRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getScenarioType()).isEqualTo(ScenarioType.HOMECOMING);
        assertThat(found.getFinalStatus()).isEqualTo(ScenarioStatus.RECEIVED);
        assertThat(found.getExternalEventId()).isEqualTo("door-open-01");
    }

    @Test
    void persistsAdvancedStatusAsString() {
        Scenario scenario = Scenario.create(
            UUID.randomUUID(), UUID.randomUUID(), ScenarioType.HOMECOMING);
        scenario.beginMovingToEntrance();
        Scenario saved = scenarioRepository.saveAndFlush(scenario);
        em.clear();

        Object raw = em.getEntityManager()
            .createNativeQuery("select final_status from scenario where id = ?1")
            .setParameter(1, saved.getId())
            .getSingleResult();
        assertThat(raw.toString()).isEqualTo("MOVING_TO_ENTRANCE");
    }

    @Test
    void findsActiveScenariosStuckPastCutoffButNotFreshOrTerminalOnes() {
        UUID seniorId = UUID.randomUUID();
        UUID robotId = UUID.randomUUID();

        // H2(datajpa 프로필)와 Postgres 모두에서 동작해야 하므로 SQL 함수로
        // 날짜를 계산하지 않는다 — now() - interval '1 hour' 는 Postgres 전용
        // 문법이라 H2 에서는 파라미터를 잘못 해석해 NPE 로 죽는다. 자바에서 계산한
        // OffsetDateTime 을 그대로 바인딩한다.
        OffsetDateTime oneHourAgo = OffsetDateTime.now().minusHours(1);

        // 오래 멈춘 CONVERSING: 컷오프보다 이전에 갱신됐다 → 워치독 대상.
        Scenario stuck = Scenario.create(seniorId, robotId, ScenarioType.HOMECOMING);
        stuck.beginMovingToEntrance();
        stuck.checkInteraction();
        stuck.beginConversation();
        scenarioRepository.saveAndFlush(stuck);
        em.getEntityManager()
            .createNativeQuery("update scenario set updated_at = ?2 where id = ?1")
            .setParameter(1, stuck.getId())
            .setParameter(2, oneHourAgo)
            .executeUpdate();

        // 방금 시작된 시나리오: 최근에 갱신됐다 → 대상이 아니다.
        Scenario fresh = Scenario.create(seniorId, robotId, ScenarioType.HOMECOMING);
        scenarioRepository.saveAndFlush(fresh);

        // 이미 끝난 시나리오: 오래됐어도 activeStatuses에 없으니 대상이 아니다.
        Scenario completed = Scenario.create(seniorId, robotId, ScenarioType.HOMECOMING);
        completed.beginMovingToEntrance();
        completed.checkInteraction();
        completed.beginConversation();
        completed.decideReturn();
        completed.returnToDefault();
        completed.complete();
        scenarioRepository.saveAndFlush(completed);
        em.getEntityManager()
            .createNativeQuery("update scenario set updated_at = ?2 where id = ?1")
            .setParameter(1, completed.getId())
            .setParameter(2, oneHourAgo)
            .executeUpdate();
        em.clear();

        List<Scenario> stale = scenarioRepository.findByFinalStatusInAndUpdatedAtBefore(
            ScenarioStatus.activeStatuses(), OffsetDateTime.now().minusMinutes(20));

        assertThat(stale).extracting(Scenario::getId).containsExactly(stuck.getId());
    }

}
