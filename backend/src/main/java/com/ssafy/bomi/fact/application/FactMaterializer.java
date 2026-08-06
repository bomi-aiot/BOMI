package com.ssafy.bomi.fact.application;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordTime;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryType;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 확정된(confirmed) FactCandidate 값을 memory / care_record 최종 테이블에 쓴다.
 *
 * <p>왜 존재하는가 — 확정(confirm)과 실체화(materialize)는 다른 단계다. 확정은
 * "어르신이 맞다고 답했다"는 확인 기록만 남기고, 실체화는 그 값을 실제
 * memory·care_record 테이블에 한 행으로 쓴다. 이 쓰기 로직이 가디언웹 경로
 * ({@code ConfirmationRequestService})에만 있고 온보딩·재질의(로봇 음성 재확인)
 * 경로에는 없어서, 두 경로로 확정한 값이 "확인됐습니다"라고 자연스럽게 넘어간
 * 채 조용히 증발하는 결함이 있었다(S15P11E102-258). 세 경로가 모두 이 컴포넌트
 * 하나만 호출하게 만들어 다시 갈라지지 않게 한다.</p>
 *
 * <p>읽는 값 confirmedValue, candidate.targetDomain / factType / seniorId 등<br>
 * 쓰는 값 memory 또는 care_record 행 하나, candidate.materialize(savedId)</p>
 *
 * <p>참고 — CLAUDE.md §8(메모리·RAG 경계), §12(계약 주도형 대화)</p>
 */
@Component
public class FactMaterializer {

    private final MemoryRepository memoryRepository;
    private final CareRecordRepository careRecordRepository;

    public FactMaterializer(MemoryRepository memoryRepository, CareRecordRepository careRecordRepository) {
        this.memoryRepository = memoryRepository;
        this.careRecordRepository = careRecordRepository;
    }

    /** 실체화된 대상의 도메인과 id. undo(되돌리기)와 감사 로그가 이 값을 필요로 한다. */
    public record MaterializedTarget(FactTargetDomain domain, UUID id) {
    }

    /**
     * candidate.getFactType() 을 memory_type / care_record.record_type 으로 그대로 쓴다.
     *
     * <p>누가 호출하는가 — 온보딩 계약(질문셋) 없이 확정되는 가디언웹, 재질의(음성
     * 재확인) 경로. 두 경로 모두 계약의 recordType 이 따로 없고, candidate.factType
     * 자체가 이미 record_type/memory_type 어휘와 같다.</p>
     */
    @Transactional
    public Optional<MaterializedTarget> materialize(FactCandidate candidate, Map<String, Object> confirmedValue) {
        return materialize(candidate, confirmedValue, candidate.getFactType());
    }

    /**
     * memory_type / care_record.record_type 을 recordType 인자로 강제한다.
     *
     * <p>왜 별도 인자인가 — 온보딩 계약의 {@code materialization.recordType}
     * (예: {@code MEDICATION_SCHEDULE})을 그대로 써야 한다. candidate.getFactType()
     * 을 대신 쓰면(가디언 경로가 하듯) 온보딩·재질의·가디언 세 채널의 record_type 이
     * 서로 갈라질 수 있다 — 같은 사실인데 채널마다 다른 이름으로 저장되는 결함
     * (S15P11E102-258 조사 중 발견).</p>
     *
     * <p>무엇을 하는가 — targetDomain 이 MEMORY 면 memory 행을, CARE_RECORD 면
     * care_record 행을 하나 만들어 저장하고, candidate 를 MATERIALIZED 로 올린다.
     * PROFILE / CARE_RELATIONSHIP 은 이 컴포넌트가 쓸 곳이 없으므로 아무것도 하지
     * 않고 {@link Optional#empty()} 를 돌려준다 — 그 경우 candidate 는 CONFIRMED 에
     * 머무는 것이 정직한 상태다.</p>
     *
     * <p>주의사항 — {@code source_candidate_id} 를 반드시 채운다. Postgres 의
     * UNIQUE 제약은 NULL 을 걸러내지 못하므로, 이 값이 비면 같은 candidate 가
     * memory/care_record 에 두 번 실체화되는 결함이 생긴다(가디언웹 경로의
     * care_record 분기에 실제로 있던 결함).</p>
     */
    @Transactional
    public Optional<MaterializedTarget> materialize(FactCandidate candidate,
        Map<String, Object> confirmedValue, String recordType) {

        if (confirmedValue == null || confirmedValue.isEmpty()) {
            throw new IllegalArgumentException("실체화할 값이 비어 있습니다.");
        }

        FactTargetDomain domain = candidate.getTargetDomain();
        if (domain == FactTargetDomain.MEMORY) {
            Memory memory = Memory.create(
                candidate.getSeniorId(), memoryType(confirmedValue, recordType), memoryContent(confirmedValue));
            memory.attachSources(candidate.getConversationId(), null, candidate.getId());
            Memory saved = memoryRepository.save(memory);
            candidate.materialize(saved.getId());
            return Optional.of(new MaterializedTarget(FactTargetDomain.MEMORY, saved.getId()));
        }
        if (domain == FactTargetDomain.CARE_RECORD) {
            CareRecord record = CareRecord.create(candidate.getSeniorId(), recordType, confirmedValue);
            // 확인된 값이 시각을 품고 있으면 그것을 쓰고, 없으면 확인한 지금이다
            // (S15P11E102-230). 어르신이 "어제 병원 다녀왔어"라고 한 것을 오늘
            // 확인했다면 값 안의 어제가 맞다 — 확인 시각은 사건 시각이 아니다.
            record.occurredAt(CareRecordTime.fromDetailsOrNow(confirmedValue, OffsetDateTime.now()));
            // source_candidate_id 를 여기서 반드시 채운다. 가디언웹 경로는 memory
            // 분기에서만 attachSources 를 불렀고 care_record 분기는 빠뜨렸었다 —
            // 그래서 같은 candidate 가 care_record 에 두 번 실체화될 수 있었다.
            record.attachSources(null, candidate.getConversationId(), candidate.getSourceMessageId(),
                candidate.getId(), candidate.getConfirmedByUserId());
            CareRecord saved = careRecordRepository.save(record);
            candidate.materialize(saved.getId());
            return Optional.of(new MaterializedTarget(FactTargetDomain.CARE_RECORD, saved.getId()));
        }
        // PROFILE / CARE_RELATIONSHIP: 이 컴포넌트가 쓸 최종 테이블이 없다.
        // candidate 는 CONFIRMED 로 남는다 — 이것이 정직한 상태다.
        return Optional.empty();
    }

    /**
     * memory_type 을 정한다. 값 안에 명시적 {@code memoryType} 키가 있으면(가디언웹이
     * 편집 화면에서 재분류하는 경우) 그것을 우선한다. 없으면 recordType(온보딩 계약의
     * recordType, 또는 candidate.factType)을 시도하고, 그마저 알 수 없는 값이면 OTHER 로
     * 떨어진다 — MemoryType 이 아닌 값을 저장 시도로 예외를 던지는 것보다, 분류를
     * 놓치더라도 값 자체는 잃지 않는 쪽이 안전하다.
     */
    private static MemoryType memoryType(Map<String, Object> value, String recordType) {
        Object explicit = value.get("memoryType");
        String raw = explicit != null ? explicit.toString() : recordType;
        if (raw == null) {
            return MemoryType.OTHER;
        }
        try {
            return MemoryType.valueOf(raw);
        } catch (IllegalArgumentException e) {
            return MemoryType.OTHER;
        }
    }

    private static String memoryContent(Map<String, Object> value) {
        Object content = value.get("content");
        if (content != null) {
            return content.toString();
        }
        Object title = value.get("title");
        return title != null ? title.toString() : "새로 저장한 기억";
    }
}
