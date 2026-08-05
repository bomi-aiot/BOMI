package com.ssafy.bomi.conversation.web;

import com.ssafy.bomi.conversation.application.ConversationLifecycleService;
import com.ssafy.bomi.conversation.application.RobotConversationService;
import com.ssafy.bomi.conversation.application.RobotConversationService.RecordedTurn;
import com.ssafy.bomi.conversation.domain.Conversation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Robot-facing write path for conversation turns (S15P11E102-211).
 *
 * <p>Separate from the guardian and app controllers on purpose. The robot writes turns as
 * they happen and needs the server to assign ordering; the app reads transcripts. Sharing
 * one endpoint would mean one of the two callers always carries fields it has no business
 * setting.</p>
 */
@RestController
@RequestMapping("/api/v1/robot/conversation-events")
@Tag(
        name = "Robot Conversation",
        description = "대화 턴 기록 — 로봇(ai_chat conversation_client)이 호출합니다.")
public class RobotConversationController {

    private final RobotConversationService service;
    private final ConversationLifecycleService lifecycleService;

    public RobotConversationController(
        RobotConversationService service, ConversationLifecycleService lifecycleService) {
        this.service = service;
        this.lifecycleService = lifecycleService;
    }

    /**
     * Records one utterance.
     *
     * <p>Returns the conversation id even when the robot supplied one, so a robot that
     * started without one can keep using the same conversation for the rest of the
     * exchange.</p>
     */
    @PostMapping
    public ResponseEntity<RecordTurnResponse> record(@Valid @RequestBody RecordTurnRequest request) {
        OffsetDateTime occurredAt =
            request.occurredAt() == null ? OffsetDateTime.now() : request.occurredAt();

        RecordedTurn recorded = service.record(
            request.seniorId(),
            request.conversationId(),
            request.role(),
            request.content(),
            occurredAt,
            request.triggerType(),
            request.priority(),
            request.orientationQuestion());

        return ResponseEntity.status(HttpStatus.CREATED).body(
            new RecordTurnResponse(
                recorded.conversationId(), recorded.messageId(), recorded.sequenceNo()));
    }

    /**
     * Applies a conversation-end decision the robot already made
     * (S15P11E102-254; CLAUDE.md §6 {@code note_interaction}/{@code _conversation_boundary}).
     *
     * <p>The robot never asks permission here — it reports a fact, the same shape as
     * {@link #record}. This is deliberately a different endpoint rather than a status
     * field on {@code record}: ending a conversation carries no utterance, and folding it
     * into the turn endpoint would make {@code content} optional there for one caller
     * only.</p>
     */
    @PostMapping("/{id}/end")
    public ResponseEntity<EndConversationResponse> end(
        @PathVariable("id") UUID conversationId,
        @Valid @RequestBody EndConversationRequest request) {

        Conversation ended = lifecycleService.end(
            conversationId, request.seniorId(), request.status(), request.sealed());

        return ResponseEntity.ok(new EndConversationResponse(
            ended.getId(), ended.getStatus().name(), ended.getEndedAt(),
            ended.getRawMessagesExpiresAt()));
    }

    /**
     * Bad references become 400, not 500.
     *
     * <p>The robot must be able to tell "I sent something wrong" from "the server is
     * broken". It retries the second and never the first — retrying a bad conversation id
     * forever would keep a turn from ever being recorded while looking like an outage.</p>
     *
     * <p>Scoped to this controller rather than global: this project has no
     * {@code @ControllerAdvice}, and adding one would change the response codes of every
     * existing endpoint. That is not this ticket's call to make.</p>
     */
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> handleBadRequest(IllegalArgumentException error) {
        return ResponseEntity.badRequest().body(Map.of("message", error.getMessage()));
    }
}
