package com.ssafy.bomi.fact.web;

import com.ssafy.bomi.fact.application.RobotClarificationService;
import com.ssafy.bomi.fact.application.RobotClarificationService.ClarificationResult;
import com.ssafy.bomi.fact.domain.ClarificationReason;
import com.ssafy.bomi.fact.domain.FactCandidate;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * The robot's side of the {@code fact_candidate} re-ask flow (S15P11E102-227).
 *
 * <p>Two calls: what should I ask about, and here is what I heard. The server serves
 * <b>at most one</b> candidate — "한 대화는 활성 후보 하나만 질의한다" is an ERD contract rule,
 * and a robot holding a queue would greet a senior with three interrogations while
 * faithfully following its own rules.</p>
 *
 * <p>Distinct from {@code /api/v1/confirmation-requests}, which is the guardian's
 * surface on the same table. Different actor, different authority: a guardian confirming
 * on the senior's behalf needs an ACTIVE PRIMARY relationship with permission; the senior
 * answering by voice does not.</p>
 */
@RestController
@RequestMapping("/api/v1/robot/clarifications")
@Tag(
        name = "Robot Clarification",
        description = "fact_candidate 재질의 — 로봇(ai_chat)이 호출합니다. 가디언웹용 확인요청 API와 같은 테이블을 다루지만 호출 주체와 권한이 다릅니다.")
public class RobotClarificationController {

    private final RobotClarificationService clarificationService;

    public RobotClarificationController(RobotClarificationService clarificationService) {
        this.clarificationService = clarificationService;
    }

    /**
     * The one candidate to raise now, or 204.
     *
     * <p>204 rather than an empty body with 200: "nothing to ask" is the common case on a
     * quiet turn, and it must be trivially distinguishable from "something went wrong" so
     * the robot's logs do not fill with non-events.</p>
     */
    @GetMapping("/active")
    public ResponseEntity<ActiveClarificationResponse> active(@RequestParam UUID seniorId) {
        return clarificationService.activeCandidate(seniorId)
            .map(candidate -> ResponseEntity.ok(ActiveClarificationResponse.of(
                candidate, clarificationService.fieldToAsk(candidate))))
            .orElseGet(() -> ResponseEntity.noContent().build());
    }

    @PostMapping("/{candidateId}/answer")
    public ClarificationAnswerResponse answer(@PathVariable UUID candidateId,
        @Valid @RequestBody ClarificationAnswerRequest request) {
        return ClarificationAnswerResponse.of(clarificationService.answer(
            candidateId,
            request.fieldValues(),
            request.confirmed(),
            request.conversationId(),
            request.sourceMessageId()));
    }

    /**
     * The pending fact, described in field names rather than sentences.
     *
     * @param missingFields exactly one field name. Turning it into a short spoken
     *     question is the robot's job — reading {@code "dose"} aloud makes a care
     *     companion sound like a form.
     * @param clarificationReason selects the phrasing. LOW_RECOGNITION_CONFIDENCE must
     *     sound like an ordinary re-ask, never like an error message.
     */
    public record ActiveClarificationResponse(
        UUID factCandidateId,
        ClarificationReason clarificationReason,
        List<String> missingFields,
        String targetDomain,
        String factType,
        String riskLevel,
        int clarificationCount,

        /** The value so far. Read back in full when the reason is a confirmation. */
        Map<String, Object> proposedValue
    ) {
        public static ActiveClarificationResponse of(FactCandidate candidate,
            List<String> fieldToAsk) {
            return new ActiveClarificationResponse(
                candidate.getId(),
                candidate.getClarificationReason(),
                fieldToAsk,
                candidate.getTargetDomain().name(),
                candidate.getFactType(),
                candidate.getRiskLevel().name(),
                candidate.getClarificationCount(),
                candidate.getProposedValue());
        }
    }

    /**
     * What the senior said about the pending field.
     *
     * @param confirmed true only when the senior explicitly confirmed the full value
     *     after hearing it read back. Silence, a topic change, "글쎄", "아마도", unclear
     *     STT, or an answer to a different question are not confirmations.
     */
    public record ClarificationAnswerRequest(
        @NotNull Map<String, Object> fieldValues,
        boolean confirmed,
        UUID conversationId,
        UUID sourceMessageId
    ) {
    }

    public record ClarificationAnswerResponse(
        String outcome,
        UUID factCandidateId,
        List<String> missingFields,
        ClarificationReason clarificationReason,
        Map<String, Object> valueToConfirm
    ) {
        public static ClarificationAnswerResponse of(ClarificationResult result) {
            return new ClarificationAnswerResponse(
                result.outcome().name(),
                result.factCandidateId(),
                result.missingFields(),
                result.clarificationReason(),
                result.valueToConfirm());
        }
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> badRequest(IllegalArgumentException error) {
        return ResponseEntity.badRequest().body(error.getMessage());
    }

    /** Answering a candidate that is already settled is a conflict, not a server fault. */
    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<String> conflict(IllegalStateException error) {
        return ResponseEntity.status(409).body(error.getMessage());
    }
}
