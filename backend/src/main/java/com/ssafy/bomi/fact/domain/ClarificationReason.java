package com.ssafy.bomi.fact.domain;

/**
 * Reason a {@link FactCandidate} needs re-clarification (§6, §10).
 *
 * <p>Only one field is re-clarified at a time.</p>
 */
public enum ClarificationReason {
    MISSING_REQUIRED_FIELD,
    AMBIGUOUS_VALUE,
    LOW_RECOGNITION_CONFIDENCE,
    CONFLICT_WITH_EXISTING_DATA,
    SENSITIVE_INFORMATION_CONFIRMATION
}
