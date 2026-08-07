package com.ssafy.bomi.care;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import java.util.Map;
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
class CareRecordRepositoryTest {

    @Autowired CareRecordRepository careRecordRepository;
    @Autowired TestEntityManager em;

    @Test
    void persistsJsonDetailsAndDefaultStatus() {
        CareRecord record = CareRecord.create(
            UUID.randomUUID(), "MEDICATION", Map.of("drug", "타이레놀", "dose", "500mg"));
        record.updateRecurrence(Map.of("frequency", "DAILY"));
        CareRecord saved = careRecordRepository.saveAndFlush(record);
        em.clear();

        CareRecord found = careRecordRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getRecordType()).isEqualTo("MEDICATION");
        assertThat(found.getStatus()).isEqualTo(CareRecordStatus.ACTIVE);
        assertThat(found.getDetails()).containsEntry("dose", "500mg");
        assertThat(found.getRecurrence()).containsEntry("frequency", "DAILY");
    }

    @Test
    void supersedeCreatesChildAndMarksParent() {
        UUID seniorId = UUID.randomUUID();
        CareRecord parent = careRecordRepository.saveAndFlush(
            CareRecord.create(seniorId, "APPOINTMENT", Map.of("at", "2026-08-01T10:00")));

        CareRecord child = parent.supersedeWith("APPOINTMENT", Map.of("at", "2026-08-02T10:00"));
        careRecordRepository.saveAndFlush(parent);
        CareRecord savedChild = careRecordRepository.saveAndFlush(child);
        em.clear();

        CareRecord foundParent = careRecordRepository.findById(parent.getId()).orElseThrow();
        CareRecord foundChild = careRecordRepository.findById(savedChild.getId()).orElseThrow();
        assertThat(foundParent.getStatus()).isEqualTo(CareRecordStatus.SUPERSEDED);
        assertThat(foundChild.getParentRecordId()).isEqualTo(parent.getId());
        assertThat(foundChild.getDetails()).containsEntry("at", "2026-08-02T10:00");
    }
}
