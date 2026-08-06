package com.ssafy.bomi.fact.web;

import java.util.Map;

/**
 * POST /confirmation-requests/{id}/resolve 요청 본문.
 * {@code resolution} = CONFIRM | EDIT | REJECT | REASK.
 * {@code editedValue} 는 EDIT 일 때만 사용(보호자가 고친 값).
 */
public record ResolveConfirmationRequest(
        String resolution,
        Map<String, Object> editedValue,
        String note) {
}
