package com.ssafy.bomi.fact.application;

import com.ssafy.bomi.fact.domain.ClarificationReason;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.domain.RiskLevel;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Serves the robot exactly one pending fact to ask about, and takes the answer.
 *
 * <h2>Why the server picks, and picks only one</h2>
 *
 * <p>"한 대화는 활성 후보 하나만 질의한다" is an ERD contract rule. If the robot held a queue,
 * a senior who says "안녕" could be met with three interrogations about pending medication
 * fields. The robot would still be following its own rules; the contract would be broken
 * anyway. So the queue lives here and the robot receives at most one item.</p>
 *
 * <h2>What the robot gets, and what it must do with it</h2>
 *
 * <p>{@code missingFields} carries <b>field names</b>, not question text. Turning
 * {@code "dose"} into a short spoken question is the robot's job — reading a field name
 * aloud is the kind of thing that makes a care companion sound like a form. The reason
 * code selects the phrasing, and LOW_RECOGNITION_CONFIDENCE in particular must sound like
 * an ordinary re-ask, not an error message.</p>
 */
@Service
public class RobotClarificationService {

    private static final Logger log = LoggerFactory.getLogger(RobotClarificationService.class);

    /** Statuses that mean "the senior still owes us something on this fact". */
    private static final List<FactCandidateStatus> OPEN = List.of(
        FactCandidateStatus.NEEDS_CLARIFICATION,
        FactCandidateStatus.NEEDS_CONFIRMATION);

    private final FactCandidateRepository candidateRepository;
    private final FactMaterializer materializer;

    public RobotClarificationService(FactCandidateRepository candidateRepository,
        FactMaterializer materializer) {
        this.candidateRepository = candidateRepository;
        this.materializer = materializer;
    }

    /**
     * The one candidate to raise in this conversation, if any.
     *
     * <p>Ordering: riskier first, then oldest. A sensitive medication ambiguity should be
     * resolved before a preference, and within the same risk the oldest goes first so
     * nothing starves behind a stream of new ones.</p>
     *
     * <p>Returns empty rather than an empty list. The caller answers 204 — "nothing to
     * ask" is a normal and frequent outcome, and it must not look like an error, or the
     * robot's log fills with failures on every quiet turn.</p>
     */
    @Transactional(readOnly = true)
    public Optional<FactCandidate> activeCandidate(UUID seniorId) {
        List<FactCandidate> open = candidateRepository
            .findBySeniorIdAndStatusInOrderByCreatedAtAsc(seniorId, OPEN);

        if (open.size() > 1) {
            // 감사를 위해 남긴다. 로봇에게는 여전히 하나만 간다.
            log.info("senior {} has {} open candidates; serving one (contract: one per conversation)",
                seniorId, open.size());
        }

        return open.stream()
            .min(Comparator
                .comparingInt((FactCandidate c) -> -riskRank(c.getRiskLevel()))
                .thenComparing(FactCandidate::getCreatedAt));
    }

    private int riskRank(RiskLevel level) {
        return level == null ? 0 : level.ordinal();
    }

    /**
     * The single field to ask about right now.
     *
     * <p>The column is a list because a candidate can be short several fields, but the
     * robot must ask about one. Truncating here rather than in the DTO keeps the rule in
     * one place — a second caller cannot accidentally expose the whole list.</p>
     */
    public List<String> fieldToAsk(FactCandidate candidate) {
        List<String> missing = candidate.getMissingFields();
        if (missing == null || missing.isEmpty()) {
            return List.of();
        }
        return List.of(missing.get(0));
    }

    /** What the robot should do next with this candidate. */
    public enum Outcome {
        /** Still short a field. Ask about the one returned. */
        NEEDS_CLARIFICATION,
        /** Complete but sensitive. Read the whole value back and get an explicit yes. */
        NEEDS_CONFIRMATION,
        /** Confirmed. Nothing more to ask about this fact. */
        CONFIRMED
    }

    /** The result of answering a clarification. */
    public record ClarificationResult(
        Outcome outcome,
        UUID factCandidateId,
        List<String> missingFields,
        ClarificationReason clarificationReason,
        Map<String, Object> valueToConfirm
    ) {
    }

    /**
     * Records what the senior said about the pending field.
     *
     * <p>Merges the supplied fields into the proposed value, then re-evaluates: still
     * missing something → ask the next single field; complete → read it back for
     * confirmation; confirmed → done.</p>
     *
     * @param confirmed the senior explicitly confirmed the full value after hearing it
     *     read back. Silence, a topic change, "글쎄", "아마도", unclear STT, or an answer to
     *     a <b>different</b> question do not count. The robot judges that first; this
     *     side refuses to confirm without the flag, so the two checks stack rather than
     *     one trusting the other.
     */
    @Transactional
    public ClarificationResult answer(UUID candidateId, Map<String, Object> fieldValues,
        boolean confirmed, UUID conversationId, UUID sourceMessageId) {

        FactCandidate candidate = candidateRepository.findById(candidateId)
            .orElseThrow(() -> new IllegalArgumentException("no fact candidate " + candidateId));

        if (!OPEN.contains(candidate.getStatus())) {
            throw new IllegalStateException(
                "candidate " + candidateId + " is " + candidate.getStatus()
                    + "; it is not awaiting an answer");
        }

        Map<String, Object> merged = new HashMap<>(candidate.getProposedValue());
        if (fieldValues != null) {
            fieldValues.forEach((field, value) -> {
                if (value != null && !value.toString().isBlank()) {
                    merged.put(field, value);
                }
            });
        }
        candidate.updateProposedValue(merged);
        // 근거를 남긴다. 나중에 "이 값이 어디서 왔는가"를 되짚을 수 있어야 한다.
        candidate.recordEvidence(conversationId, sourceMessageId);

        List<String> stillMissing = candidate.getMissingFields().stream()
            .filter(field -> {
                Object value = merged.get(field);
                return value == null || value.toString().isBlank();
            })
            .toList();

        if (!stillMissing.isEmpty()) {
            // 남은 것을 전부 저장하고, 돌려주는 것은 하나. FactCandidate.needsClarification 참고.
            ClarificationReason reason = candidate.getClarificationReason() == null
                ? ClarificationReason.MISSING_REQUIRED_FIELD
                : candidate.getClarificationReason();
            candidate.needsClarification(reason, stillMissing);
            return new ClarificationResult(Outcome.NEEDS_CLARIFICATION, candidateId,
                List.of(stillMissing.get(0)), reason, null);
        }

        if (isSensitive(candidate) && !confirmed) {
            candidate.needsConfirmation();
            return new ClarificationResult(Outcome.NEEDS_CONFIRMATION, candidateId, List.of(),
                ClarificationReason.SENSITIVE_INFORMATION_CONFIRMATION, merged);
        }

        candidate.confirm(merged, candidate.getSeniorId());
        log.info("candidate {} confirmed via the robot channel", candidateId);

        // 확정만 하고 memory/care_record 에 쓰지 않으면, 음성으로 확정한 값이 다음 날
        // 로봇 인사 시나리오에 아무 흔적도 남기지 못한 채 증발한다(S15P11E102-258).
        // 가디언웹(ConfirmationRequestService)이 쓰는 것과 같은 공용 컴포넌트를 호출해
        // candidate.materialize(savedRowId) 까지 연결한다.
        materializer.materialize(candidate, merged);
        return new ClarificationResult(Outcome.CONFIRMED, candidateId, List.of(), null, merged);
    }

    /**
     * Sensitive values get read back in full even when unambiguous.
     *
     * <p>Health, medication, schedule and guardian-notification facts are confirmed
     * explicitly (design note §2). Getting this wrong writes a misheard dose, which is
     * the one failure this whole flow exists to prevent.</p>
     */
    private boolean isSensitive(FactCandidate candidate) {
        return candidate.getRiskLevel() == RiskLevel.SENSITIVE
            || candidate.getRiskLevel() == RiskLevel.HIGH;
    }
}
