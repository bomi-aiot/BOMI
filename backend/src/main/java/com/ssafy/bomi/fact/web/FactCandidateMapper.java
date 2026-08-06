package com.ssafy.bomi.fact.web;

import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.web.ConfirmationTextFactory.ConfirmationText;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** fact_candidate 엔티티 → {@link FactCandidateDto} 변환. */
@Component
public class FactCandidateMapper {

    private final ConfirmationTextFactory textFactory;

    public FactCandidateMapper(ConfirmationTextFactory textFactory) {
        this.textFactory = textFactory;
    }

    public FactCandidateDto toDto(FactCandidate c) {
        ConfirmationText text = textFactory.create(c);
        return new FactCandidateDto(
                str(c.getId()),
                str(c.getSeniorId()),
                name(c.getTargetDomain()),
                c.getFactType(),
                name(c.getOperation()),
                name(c.getStatus()),
                name(c.getRiskLevel()),
                name(c.getCoordinationStatus()),
                name(c.getSourceType()),
                str(c.getConversationId()),
                str(c.getSourceMessageId()),
                c.getProposedValue(),
                c.getConfirmedValue(),
                // 충돌(UPDATE) 시 기존 값. 대상 엔티티 조회는 후속(P0에서는 null).
                null,
                text.title(),
                text.summary(),
                text.question(),
                text.evidence(),
                str(c.getMaterializedTargetId()),
                iso(c.getCreatedAt()),
                iso(c.getConfirmedAt()),
                iso(c.getMaterializedAt()));
    }

    private static String str(UUID value) {
        return value == null ? null : value.toString();
    }

    private static String name(Enum<?> value) {
        return value == null ? null : value.name();
    }

    private static String iso(OffsetDateTime value) {
        return value == null ? null : value.toString();
    }
}
