package com.ssafy.bomi.fact.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.fact.application.FactMaterializer.MaterializedTarget;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.domain.FactOperation;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.fact.domain.RiskLevel;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * 같은 약속이 두 번 저장되지 않는지 검증한다 (2026-08-10).
 *
 * <p><b>무엇이 있었나.</b> 어르신이 "다음 주 화요일에 병원 간다"를 며칠에 걸쳐 여러 번
 * 말하면 발화마다 별개의 {@code fact_candidate} 가 생기고, 각각이 별개의
 * {@code care_record} 로 실체화됐다. 시연 DB 에 거의 같은 문장의 APPOINTMENT 행이
 * 9개 쌓여 있었고, 그것이 문맥 조립의 상위 5건을 통째로 차지해 정작 필요한 기록을
 * 밀어냈다.</p>
 *
 * <p><b>왜 V13 인덱스로는 못 막나.</b> 그 유니크 인덱스는
 * {@code (senior_id, source_message_id, fact_type)} 이라 '같은 발화의 재시도'만
 * 막는다. 다른 발화가 같은 약속을 말한 경우는 범위 밖이다.</p>
 */
class FactMaterializerScheduleDedupTest {

    private static final UUID SENIOR = UUID.randomUUID();
    private static final UUID CONVERSATION = UUID.randomUUID();
    private static final OffsetDateTime TUESDAY_2PM =
        OffsetDateTime.parse("2026-08-18T14:00:00+09:00");

    private CareRecordRepository careRecordRepository;
    private FactMaterializer materializer;

    @BeforeEach
    void setUp() {
        careRecordRepository = mock(CareRecordRepository.class);
        materializer = new FactMaterializer(mock(MemoryRepository.class), careRecordRepository);
    }

    private FactCandidate confirmedAppointment(Map<String, Object> value) {
        FactCandidate candidate = FactCandidate.fromConversationMessage(
            SENIOR, CONVERSATION, UUID.randomUUID(), FactTargetDomain.CARE_RECORD,
            "APPOINTMENT", FactOperation.CREATE, value, RiskLevel.NORMAL);
        candidate.confirm(value, null);
        return candidate;
    }

    /**
     * 이미 DB 에 있는 일정 한 건.
     *
     * <p>목(mock)을 쓰는 이유는 {@code id} 가 {@code @GeneratedValue} 라 저장 전에는
     * 항상 null 이기 때문이다. 중복 판정이 돌려주는 것은 '기존 행의 id' 이므로,
     * id 없는 엔티티로는 이 테스트가 검증하려는 것을 표현할 수 없다.</p>
     */
    private CareRecord alreadyStored(OffsetDateTime when) {
        CareRecord existing = mock(CareRecord.class);
        when(existing.getId()).thenReturn(UUID.randomUUID());
        when(existing.getOccurredAt()).thenReturn(when);
        return existing;
    }

    /** 저장은 id 가 붙은 행을 돌려준다 — 실제 JPA 가 하는 일이고, 후보가 그 id 를 쓴다. */
    private void stubSaveReturningAnIdentifiedRow() {
        CareRecord saved = mock(CareRecord.class);
        when(saved.getId()).thenReturn(UUID.randomUUID());
        when(careRecordRepository.save(any(CareRecord.class))).thenReturn(saved);
    }

    @Test
    void the_same_appointment_said_twice_is_stored_once() {
        CareRecord existing = alreadyStored(TUESDAY_2PM);
        when(careRecordRepository.findBySeniorIdAndRecordTypeAndStatus(
            SENIOR, "APPOINTMENT", CareRecordStatus.ACTIVE)).thenReturn(List.of(existing));

        // 문장은 다르지만 같은 시각의 같은 약속이다. 사람이 보기에도 하나다.
        FactCandidate candidate = confirmedAppointment(Map.of(
            "title", "병원 진료",
            "content", "다음 주 화요일 오후 두 시에 병원에 간다.",
            "startsAt", "2026-08-18T14:00:00+09:00"));

        Optional<MaterializedTarget> target =
            materializer.materialize(candidate, candidate.getConfirmedValue(), "APPOINTMENT");

        verify(careRecordRepository, never()).save(any(CareRecord.class));
        assertThat(target).isPresent();
        assertThat(target.get().id()).isEqualTo(existing.getId());
        // 후보는 버려지지 않는다 — 기존 행을 가리키며 MATERIALIZED 로 닫힌다.
        assertThat(candidate.getStatus()).isEqualTo(FactCandidateStatus.MATERIALIZED);
        assertThat(candidate.getMaterializedTargetId()).isEqualTo(existing.getId());
    }

    @Test
    void a_different_time_is_a_different_appointment() {
        CareRecord existing = alreadyStored(TUESDAY_2PM);
        when(careRecordRepository.findBySeniorIdAndRecordTypeAndStatus(
            SENIOR, "APPOINTMENT", CareRecordStatus.ACTIVE)).thenReturn(List.of(existing));
        stubSaveReturningAnIdentifiedRow();

        FactCandidate candidate = confirmedAppointment(Map.of(
            "title", "병원 예약", "startsAt", "2026-08-19T14:00:00+09:00"));

        materializer.materialize(candidate, candidate.getConfirmedValue(), "APPOINTMENT");

        verify(careRecordRepository).save(any(CareRecord.class));
    }

    @Test
    void the_same_instant_written_with_another_offset_is_still_one_appointment() {
        CareRecord existing = alreadyStored(TUESDAY_2PM);
        when(careRecordRepository.findBySeniorIdAndRecordTypeAndStatus(
            SENIOR, "APPOINTMENT", CareRecordStatus.ACTIVE)).thenReturn(List.of(existing));

        // 같은 순간을 UTC 로 적은 값. 표기가 다르다고 다른 약속으로 세면 안 된다.
        FactCandidate candidate = confirmedAppointment(Map.of(
            "title", "병원 예약", "startsAt", "2026-08-18T05:00:00Z"));

        materializer.materialize(candidate, candidate.getConfirmedValue(), "APPOINTMENT");

        verify(careRecordRepository, never()).save(any(CareRecord.class));
    }

    @Test
    void an_appointment_without_a_time_is_never_merged_away() {
        // 시각을 모르는 일정끼리 "둘 다 시각 없음"으로 합치면 서로 다른 약속이
        // 하나로 사라진다. 중복 하나가 소실 하나보다 낫다.
        stubSaveReturningAnIdentifiedRow();

        FactCandidate candidate = confirmedAppointment(Map.of("title", "언제인지 모르는 약속"));

        materializer.materialize(candidate, candidate.getConfirmedValue(), "APPOINTMENT");

        verify(careRecordRepository).save(any(CareRecord.class));
        // 시각이 없으면 조회 자체를 하지 않는다 — 전 일정을 훑는 낭비도 없다.
        verify(careRecordRepository, never())
            .findBySeniorIdAndRecordTypeAndStatus(any(), eq("APPOINTMENT"), any());
    }

    @Test
    void medication_is_not_deduplicated_because_a_repeat_may_be_a_change() {
        // 같은 약을 다시 말하는 것은 대개 용량·복용법의 변경이다. "이미 있다"며
        // 조용히 버리면 바뀐 처방이 반영되지 않는다 — 중복보다 위험하다.
        stubSaveReturningAnIdentifiedRow();

        Map<String, Object> value = Map.of(
            "medicationName", "혈압약", "dose", "2정",
            "scheduledAt", "2026-08-18T14:00:00+09:00");
        FactCandidate candidate = FactCandidate.fromConversationMessage(
            SENIOR, CONVERSATION, UUID.randomUUID(), FactTargetDomain.CARE_RECORD,
            "MEDICATION", FactOperation.CREATE, value, RiskLevel.HIGH);
        candidate.confirm(value, null);

        materializer.materialize(candidate, candidate.getConfirmedValue(), "MEDICATION");

        verify(careRecordRepository).save(any(CareRecord.class));
    }
}
