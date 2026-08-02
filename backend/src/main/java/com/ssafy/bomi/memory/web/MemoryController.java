package com.ssafy.bomi.memory.web;

import com.ssafy.bomi.memory.web.dto.MemoryDto;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 가디언 웹 기억(대화 정보) API. 단일 어르신 전제(P0)라 경로에 elderId 없음.
 * 접두: {@code /api/v1/memories} (FE API_ENDPOINTS.conversationPreferences 와 일치).
 */
@RestController
@RequestMapping("/api/v1/memories")
public class MemoryController {

    private final MemoryQueryService service;

    public MemoryController(MemoryQueryService service) {
        this.service = service;
    }

    @GetMapping
    public List<MemoryDto> list() {
        return service.getConversationMemories();
    }
}
