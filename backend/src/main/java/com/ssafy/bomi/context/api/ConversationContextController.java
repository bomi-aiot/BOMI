package com.ssafy.bomi.context.api;

import com.ssafy.bomi.context.application.ConversationContextService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * The context-assembly seam between the backend and the robot (MVP ERD §9).
 *
 * <p>One endpoint, one round trip, six kinds of context. It exists so the robot never
 * performs retrieval itself: this side owns facts and search, the robot owns timing and
 * delivery (CLAUDE.md §5). A single call also matters for latency — a voice turn has
 * roughly two seconds for everything, and six calls would not fit.</p>
 */
@RestController
@RequestMapping("/api/v1/seniors/{seniorId}/conversation-context")
@Tag(
        name = "Conversation Context",
        description = "대화 문맥 조립 — 로봇(ai_chat context_client)이 호출합니다. 로봇 전용 이음새입니다.")
public class ConversationContextController {

    private final ConversationContextService contextService;

    public ConversationContextController(ConversationContextService contextService) {
        this.contextService = contextService;
    }

    /**
     * Assembles context for one turn.
     *
     * <p>{@code POST} for a read is deliberate. The request carries the senior's own
     * utterance, and personal or health-related speech must not travel in a URL where
     * access logs, proxies, and metrics would capture it by default. The trade is losing
     * HTTP caching, which this endpoint could not use anyway — the answer changes with
     * every new message.</p>
     */
    @PostMapping
    @Operation(
        summary = "한 턴의 대화 문맥을 조립한다",
        description = """
            프로필·오늘 상태·최근 Raw·요약·장기 기억·동의된 돌봄 기록을 한 번에 돌려준다.
            선필터(senior, ACTIVE, REJECTED 제외, visibility)와 재정렬(유사도 × 중요도 ×
            최근성)은 서버가 수행한다. 로봇은 벡터 검색을 직접 하지 않는다.

            프로필·복약·일정·회피 주제는 정확 조회 대상이며 의미 검색을 거치지 않는다.
            "혈압약"과 "혈당약"은 임베딩상 거의 동일해서 엉뚱한 값이 나오기 때문이다.

            documents 는 info 인텐트에서만 true 로 보낸다. 잡담에 문서를 검색하면
            지연 예산을 낭비하고 프롬프트를 오염시킨다.

            availability 는 기능 가용성, retrieval 은 이번 요청의 실제 검색 실행 여부·
            폴백 사유·hit 수·지연이다. 목록이 비어 있는 것, 검색하지 않은 것, 검색에
            실패한 것은 서로 다른 상태이며 로봇은 retrieval 을 로그와 응답 안전성에
            반영해야 한다.
            """)
    public ResponseEntity<ConversationContextResponse> assemble(
        @PathVariable UUID seniorId,
        @Valid @RequestBody ConversationContextRequest request
    ) {
        return ResponseEntity.ok(contextService.assemble(seniorId, request));
    }
}
