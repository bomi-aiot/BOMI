package com.ssafy.bomi.scenario;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.conversation.domain.ConversationIntent;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.domain.WakeWordTriggerDisposition;
import com.ssafy.bomi.scenario.domain.WakeWordTriggerReceipt;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.scenario.repository.WakeWordTriggerReceiptRepository;
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
    @Autowired WakeWordTriggerReceiptRepository receiptRepository;
    @Autowired TestEntityManager em;

    @Test
    void persistsEnumsWithDefaultStatus() {
        Scenario scenario = Scenario.create(
            UUID.randomUUID(), UUID.randomUUID(), ScenarioType.HOMECOMING, "door-open-01");
        scenario.prepareConversation(
            ConversationIntent.HOMECOMING_GREETING,
            "어서 오세요. 오늘 외출은 어떠셨어요?",
            java.util.Map.of("sourceId", "door-open-01", "location", "ENTRANCE"));
        Scenario saved = scenarioRepository.saveAndFlush(scenario);
        em.clear();

        Scenario found = scenarioRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getScenarioType()).isEqualTo(ScenarioType.HOMECOMING);
        assertThat(found.getFinalStatus()).isEqualTo(ScenarioStatus.RECEIVED);
        assertThat(found.getExternalEventId()).isEqualTo("door-open-01");
        assertThat(found.requirePreparedConversation().intent())
            .isEqualTo(ConversationIntent.HOMECOMING_GREETING);
        assertThat(found.requirePreparedConversation().triggerContext())
            .containsEntry("location", "ENTRANCE");
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
    void persistsWakeWordTriggerNavigationCorrelationAndTerminalResult() {
        OffsetDateTime occurredAt = OffsetDateTime.parse("2026-08-05T10:00:00+09:00");
        Scenario scenario = Scenario.create(
            UUID.randomUUID(), UUID.randomUUID(), ScenarioType.WAKE_WORD_CALL, "wake-event-01");
        scenario.recordTriggerContext(java.util.Map.of(
            "robotId", "robot-01",
            "occurredAt", occurredAt.toString(),
            "keyword", "보미야",
            "confidence", 0.92));
        scenario.beginNavigation();
        scenario.expectNavigationResult("wake-command-01", "LIVING_ROOM");
        UUID scenarioId = scenarioRepository.saveAndFlush(scenario).getId();
        em.clear();

        Scenario navigating = scenarioRepository.findById(scenarioId).orElseThrow();
        assertThat(navigating.getFinalStatus()).isEqualTo(ScenarioStatus.NAVIGATING);
        assertThat(navigating.getExternalEventId()).isEqualTo("wake-event-01");
        assertThat(navigating.getTriggerContext())
            .containsEntry("keyword", "보미야")
            .containsEntry("confidence", 0.92);
        assertThat(navigating.getActiveNavigationCommandId()).isEqualTo("wake-command-01");
        assertThat(navigating.getActiveNavigationTarget()).isEqualTo("LIVING_ROOM");

        navigating.complete("ARRIVED", null);
        scenarioRepository.saveAndFlush(navigating);
        em.clear();

        Scenario completed = scenarioRepository.findById(scenarioId).orElseThrow();
        assertThat(completed.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(completed.getCompletionResultCode()).isEqualTo("ARRIVED");
        assertThat(completed.getCompletionReasonCode()).isNull();
        assertThat(completed.getActiveNavigationCommandId()).isNull();
        assertThat(completed.getActiveNavigationTarget()).isNull();
    }

    @Test
    void persistsRejectedWakeWordReceiptForRestartSafeIdempotency() {
        OffsetDateTime occurredAt = OffsetDateTime.parse("2026-08-05T10:00:00+09:00");
        WakeWordTriggerReceipt receipt = WakeWordTriggerReceipt.receive(
            "wake-rejected-01", "robot-01", occurredAt, "보미야", null);
        receipt.reject(WakeWordTriggerDisposition.REJECTED_ACTIVE_SCENARIO);
        receiptRepository.saveAndFlush(receipt);
        em.clear();

        WakeWordTriggerReceipt found = receiptRepository.findById("wake-rejected-01")
            .orElseThrow();
        assertThat(found.getDisposition())
            .isEqualTo(WakeWordTriggerDisposition.REJECTED_ACTIVE_SCENARIO);
        assertThat(found.getScenarioId()).isNull();
        assertThat(found.describes("robot-01", occurredAt, "보미야", null)).isTrue();
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
