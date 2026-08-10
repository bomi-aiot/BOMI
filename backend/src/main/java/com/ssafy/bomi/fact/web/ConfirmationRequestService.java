package com.ssafy.bomi.fact.web;

import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.fact.application.FactMaterializer;
import com.ssafy.bomi.fact.application.FactMaterializer.MaterializedTarget;
import com.ssafy.bomi.fact.domain.ClarificationReason;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import com.ssafy.bomi.fact.web.ConfirmationUndoStore.Snapshot;
import com.ssafy.bomi.memory.domain.MemoryVisibility;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * 확인요청(fact_candidate) 목록 조회 및 처리(resolve)/되돌리기(undo).
 * 확정 시 memory / care_record 로 materialize 한다.
 */
@Service
public class ConfirmationRequestService {

    private static final String SENIOR_USER_TYPE = "SENIOR";

    /** 목록에 노출할 대기 계열 상태. (P0 필드매핑 A-3) */
    private static final List<FactCandidateStatus> PENDING_STATUSES = List.of(
            FactCandidateStatus.NEEDS_CONFIRMATION,
            FactCandidateStatus.NEEDS_CLARIFICATION,
            FactCandidateStatus.COORDINATION_REQUIRED);

    private final FactCandidateRepository factCandidateRepository;
    private final MemoryRepository memoryRepository;
    private final CareRecordRepository careRecordRepository;
    private final AppUserRepository appUserRepository;
    private final FactCandidateMapper mapper;
    private final ConfirmationUndoStore undoStore;
    private final FactMaterializer materializer;

    public ConfirmationRequestService(
            FactCandidateRepository factCandidateRepository,
            MemoryRepository memoryRepository,
            CareRecordRepository careRecordRepository,
            AppUserRepository appUserRepository,
            FactCandidateMapper mapper,
            ConfirmationUndoStore undoStore,
            FactMaterializer materializer) {
        this.factCandidateRepository = factCandidateRepository;
        this.memoryRepository = memoryRepository;
        this.careRecordRepository = careRecordRepository;
        this.appUserRepository = appUserRepository;
        this.mapper = mapper;
        this.undoStore = undoStore;
        this.materializer = materializer;
    }

    @Transactional(readOnly = true)
    public List<FactCandidateDto> list() {
        UUID seniorId = appUserRepository.findFirstByUserType(SENIOR_USER_TYPE)
                .orElseThrow(() -> new IllegalStateException("등록된 어르신이 없습니다."))
                .getId();
        return factCandidateRepository
                .findBySeniorIdAndStatusInOrderByCreatedAtDesc(seniorId, PENDING_STATUSES)
                .stream()
                .map(mapper::toDto)
                .toList();
    }

    @Transactional
    public FactCandidateDto resolve(UUID id, ResolveConfirmationRequest request) {
        FactCandidate candidate = load(id);
        FactCandidateStatus previousStatus = candidate.getStatus();
        String resolution = request.resolution() == null ? "" : request.resolution().toUpperCase();

        Snapshot snapshot = switch (resolution) {
            case "CONFIRM" -> confirmAndMaterialize(candidate, candidate.getProposedValue(), previousStatus);
            case "EDIT" -> confirmAndMaterialize(candidate, request.editedValue(), previousStatus);
            case "REJECT" -> {
                candidate.reject();
                yield new Snapshot(previousStatus, null, null);
            }
            case "REASK" -> {
                candidate.needsClarification(ClarificationReason.AMBIGUOUS_VALUE, candidate.getMissingFields());
                yield new Snapshot(previousStatus, null, null);
            }
            default -> throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "지원하지 않는 resolution: " + request.resolution());
        };

        factCandidateRepository.save(candidate);
        undoStore.save(id, snapshot);
        return mapper.toDto(candidate);
    }

    @Transactional
    public FactCandidateDto undo(UUID id) {
        FactCandidate candidate = load(id);
        Snapshot snapshot = undoStore.pop(id);
        if (snapshot == null) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "되돌릴 수 있는 처리가 없습니다.");
        }

        // materialize 로 생성된 대상 제거
        if (snapshot.targetId() != null && snapshot.targetDomain() != null) {
            if ("MEMORY".equals(snapshot.targetDomain())) {
                memoryRepository.deleteById(snapshot.targetId());
            } else if ("CARE_RECORD".equals(snapshot.targetDomain())) {
                careRecordRepository.deleteById(snapshot.targetId());
            }
        }

        // 상태 복원: 대기 계열은 NEEDS_CONFIRMATION 으로 되돌린다(P0 단순화).
        // confirmed_value 는 도메인 API 상 직접 초기화 수단이 없어 남겨두되, 재처리 시 덮어써진다.
        candidate.needsConfirmation();
        factCandidateRepository.save(candidate);
        return mapper.toDto(candidate);
    }

    // --- 내부 ---------------------------------------------------------------

    private Snapshot confirmAndMaterialize(
            FactCandidate candidate, Map<String, Object> value, FactCandidateStatus previousStatus) {
        if (value == null || value.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "반영할 값이 비어 있습니다.");
        }
        candidate.confirm(value, null);

        // 실제 memory/care_record 쓰기는 공용 컴포넌트가 한다(S15P11E102-258). 온보딩·
        // 재질의 경로도 같은 컴포넌트를 호출하므로 세 경로의 실체화 규칙이 갈라지지 않는다.
        Optional<MaterializedTarget> materialized = materializer.materialize(candidate, value);

        // 보호자가 승인한 기억은 보호자에게 보인다.
        //
        //   FactMaterializer 는 visibility 인자 없는 Memory.create 를 부르고, 그 기본값은
        //   PRIVATE 다(Memory.java:87 — CLAUDE.md §9 T4 "이건 나만 알고 있을래요"를 만드는
        //   값이라 기본값 자체는 옳다). 문제는 이 경로다: 보호자가 웹에서 직접 "저장할까요"에
        //   예라고 누른 값까지 PRIVATE 로 떨어져, 승인한 본인의 화면에서 영원히 사라졌다.
        //
        //   자동 승인(ConversationFactIntakeService)·재질의(RobotClarificationService) 경로는
        //   일부러 건드리지 않는다 — 그쪽은 사람이 공개에 동의한 적이 없다. 그래서
        //   FactMaterializer 를 고치지 않고 이 호출부에서만 승격한다.
        materialized
                .filter(target -> target.domain() == FactTargetDomain.MEMORY)
                .ifPresent(target -> memoryRepository.findById(target.id())
                        .ifPresent(memory -> memory.changeVisibility(MemoryVisibility.SHARED_WITH_PRIMARY)));

        return materialized
                .map(target -> new Snapshot(previousStatus, target.domain().name(), target.id()))
                // PROFILE / CARE_RELATIONSHIP: 이 티켓 범위에서는 materialize 대상 없음 →
                // CONFIRMED 로만 둔다.
                .orElseGet(() -> new Snapshot(previousStatus, null, null));
    }

    private FactCandidate load(UUID id) {
        return factCandidateRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "확인요청을 찾을 수 없습니다: " + id));
    }
}
