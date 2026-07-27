package com.ssafy.bomi.scenario;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
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
}
