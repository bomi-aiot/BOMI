package com.ssafy.bomi.fact.application;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import com.ssafy.bomi.care.domain.CareRecordTime;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryType;
import com.ssafy.bomi.memory.domain.MemoryVisibility;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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

    private static final Logger log = LoggerFactory.getLogger(FactMaterializer.class);

    /**
     * 같은 시각이면 같은 약속으로 보는 기록 유형.
     *
     * <p>{@code ConversationContextService.SCHEDULE_RECORD_TYPES} 와 같은 목록이지만
     * 일부러 복사해 둔다. 저쪽은 "동의 게이트에서 어떤 유형을 일정으로 볼지"이고
     * 이쪽은 "어떤 유형에 중복 판정을 걸지"다. 두 질문이 언젠가 갈릴 수 있고,
     * 그때 한쪽을 고치다 다른 쪽이 조용히 따라 바뀌면 안 된다.</p>
     */
    private static final Set<String> SCHEDULE_RECORD_TYPES =
        Set.of("APPOINTMENT", "PERSONAL_SCHEDULE");

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
            // ⚠️ 시연 임시 조치 (2026-08-10) — 되돌릴 것.
            //
            //   기본값은 PRIVATE 이고, 그것을 SHARED_WITH_PRIMARY 로 올리는 경로는
            //   보호자 승인 하나뿐이다(ConfirmationRequestService). 그런데 위험도
            //   NORMAL 인 사실은 자동 CONFIRMED 로 지나가 승인 요청 자체가 생기지
            //   않는다(pendingConfirmationCount=0 으로 실측). 그래서 대화에서 뽑힌
            //   기억은 만들어지자마자 PRIVATE 로 굳고, 대시보드의 4중 SHARED 필터에
            //   걸려 보호자 화면에 영원히 나타나지 않는다.
            //
            //   시연은 "대화한 내용이 화면에 뜬다"를 보여야 하므로 여기서만 공유로
            //   만든다. 이것은 T4 프라이버시 계약(CLAUDE.md §9)을 우회하는 것이다 —
            //   어르신이 승인한 적 없는 대화 파생 내용이 보호자에게 자동 공개된다.
            //   시연이 끝나면 이 커밋을 revert 한다. 제대로 된 해결은 승인 플로우를
            //   태우거나(risk_level 상향) 보호자 화면에 승인 UI 를 붙이는 것이다.
            MemoryType type = memoryType(confirmedValue, recordType);
            Memory memory = Memory.create(
                candidate.getSeniorId(), type, memoryContent(confirmedValue),
                MemoryVisibility.SHARED_WITH_PRIMARY);
            // 중요도를 여기서 정한다 (2026-08-10). 비워 두면 랭킹의 한 축이 상수로
            // 죽어(NULL→3), 방금 들어온 오인식 잔해가 최근성만으로 어르신의 인생
            // 이야기를 밀어낸다 — MemoryImportancePolicy 의 설명 참고.
            memory.setImportance(MemoryImportancePolicy.importanceFor(
                type, candidate.getConversationId() != null));
            memory.attachSources(candidate.getConversationId(), null, candidate.getId());
            Memory saved = memoryRepository.save(memory);
            candidate.materialize(saved.getId());
            return Optional.of(new MaterializedTarget(FactTargetDomain.MEMORY, saved.getId()));
        }
        if (domain == FactTargetDomain.CARE_RECORD) {
            // ★ 같은 약속은 한 번만 저장한다 (2026-08-10)
            //
            //   어르신이 "다음 주 화요일에 병원 간다"를 사흘에 걸쳐 다섯 번 말하면
            //   발화마다 별개의 fact_candidate 가 생기고, 각각이 여기서 별개의
            //   care_record 가 됐다. 실제로 시연 DB 에 거의 같은 문장의 APPOINTMENT
            //   행이 9개 쌓여 있었고, 그것이 문맥 조립의 상위 5건(careRecordLimit)을
            //   통째로 차지해 정작 필요한 기록을 밀어냈다.
            //
            //   V13 의 유니크 인덱스는 (senior_id, source_message_id, fact_type) 이라
            //   '같은 발화의 재시도'만 막는다. 다른 발화가 같은 약속을 말한 경우는
            //   그 인덱스의 범위 밖이다 — 여기서 막아야 하는 이유다.
            Optional<CareRecord> duplicate =
                existingSchedule(candidate.getSeniorId(), recordType, confirmedValue);
            if (duplicate.isPresent()) {
                UUID existingId = duplicate.get().getId();
                log.info("schedule already recorded for {} at {}; reusing care_record {} "
                        + "instead of creating a duplicate",
                    candidate.getSeniorId(), CareRecordTime.fromDetails(confirmedValue), existingId);
                candidate.materialize(existingId);
                return Optional.of(new MaterializedTarget(FactTargetDomain.CARE_RECORD, existingId));
            }

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
     * 같은 어르신·같은 시각의 일정이 이미 ACTIVE 로 있으면 그 행을 돌려준다.
     *
     * <p><b>왜 시각으로 비교하는가.</b> 문장은 매번 다르다 — "다음 주 화요일에 병원에
     * 간다", "다음 주 화요일 오후 두 시에 병원에 간다", "화요일에 병원 예약 있어".
     * 같은 약속인지 아닌지를 가르는 것은 문장이 아니라 그 약속이 열리는 시각이다.
     * 그 시각은 이미 {@link CareRecordTime#fromDetails} 가 뽑아 {@code occurred_at}
     * 으로 저장돼 있으므로, 새 후보의 시각과 그것만 맞춰 보면 된다.</p>
     *
     * <p><b>왜 복약(MEDICATION)은 대상이 아닌가.</b> 같은 약을 다시 말하는 것은
     * 대개 용량·복용법의 변경이고, 그것을 "이미 있다"며 조용히 버리면 바뀐 처방이
     * 반영되지 않는다. 그건 중복보다 위험하다. 일정은 반대다 — 같은 시각의 같은
     * 약속을 두 번 저장할 이유가 없다.</p>
     *
     * <p><b>시각을 모르면 중복 판정을 하지 않는다.</b> {@code startsAt} 이 없는
     * 일정끼리 "둘 다 시각 없음"을 근거로 합치면 서로 다른 약속이 하나로 사라진다.
     * 모르면 그대로 새 행을 만든다 — 중복 하나가 소실 하나보다 낫다.</p>
     */
    private Optional<CareRecord> existingSchedule(
        UUID seniorId, String recordType, Map<String, Object> confirmedValue) {

        if (!SCHEDULE_RECORD_TYPES.contains(recordType)) {
            return Optional.empty();
        }
        OffsetDateTime when = CareRecordTime.fromDetails(confirmedValue);
        if (when == null) {
            return Optional.empty();
        }
        return careRecordRepository
            .findBySeniorIdAndRecordTypeAndStatus(seniorId, recordType, CareRecordStatus.ACTIVE)
            .stream()
            // isEqual 은 오프셋이 달라도 같은 순간이면 참이다. "+09:00" 과 "Z" 로
            // 표기된 같은 시각을 다른 약속으로 세지 않는다.
            .filter(existing -> existing.getOccurredAt() != null
                && existing.getOccurredAt().isEqual(when))
            .findFirst();
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
