package com.ssafy.bomi.fact.web;

import java.util.List;
import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 가디언 웹 확인요청 API. 단일 어르신 전제(P0)라 경로에 elderId 가 없다.
 * 전체 경로 접두: {@code /api/v1/confirmation-requests} (FE API_BASE_URL 기본값 "/api").
 */
@RestController
@RequestMapping("/api/v1/confirmation-requests")
public class ConfirmationRequestController {

    private final ConfirmationRequestService service;

    public ConfirmationRequestController(ConfirmationRequestService service) {
        this.service = service;
    }

    @GetMapping
    public List<FactCandidateDto> list() {
        return service.list();
    }

    @PostMapping("/{id}/resolve")
    public FactCandidateDto resolve(
            @PathVariable UUID id, @RequestBody ResolveConfirmationRequest request) {
        return service.resolve(id, request);
    }

    @PostMapping("/{id}/undo")
    public FactCandidateDto undo(@PathVariable UUID id) {
        return service.undo(id);
    }
}
