package com.ssafy.bomi.onboarding.web;

import com.ssafy.bomi.onboarding.application.QuestionDefinition;
import com.ssafy.bomi.onboarding.application.RobotOnboardingService;
import com.ssafy.bomi.onboarding.domain.OnboardingSession;
import com.ssafy.bomi.onboarding.repository.OnboardingSessionRepository;
import com.ssafy.bomi.onboarding.web.RobotOnboardingDtos.NextQuestionResponse;
import com.ssafy.bomi.onboarding.web.RobotOnboardingDtos.SessionResponse;
import com.ssafy.bomi.onboarding.web.RobotOnboardingDtos.StartSessionRequest;
import com.ssafy.bomi.onboarding.web.RobotOnboardingDtos.SubmitAnswerRequest;
import com.ssafy.bomi.onboarding.web.RobotOnboardingDtos.SubmitAnswerResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.Optional;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

/**
 * The robot's side of the onboarding contract (S15P11E102-227).
 *
 * <p>Three calls, and none of them lets the robot decide anything: start or resume,
 * ask for the next question, hand back what was heard. The state machine is on the
 * server because the rules it enforces depend on data the robot does not have — consent
 * in {@code app_user}, the session that the app may have started — and because a rule
 * held by a device version is a rule nobody can audit (CLAUDE.md §12).</p>
 *
 * <p>Robot-facing, not guardian-facing. {@code /api/v1/confirmation-requests} is the
 * guardian's confirmation surface and is a different flow with different authority.</p>
 */
@RestController
@RequestMapping("/api/v1/robot/onboarding")
@Tag(
        name = "Robot Onboarding",
        description = "로봇 채널 온보딩(계약 주도형 대화) — 로봇(ai_chat contract_client)이 호출합니다.")
public class RobotOnboardingController {

    private final RobotOnboardingService onboardingService;
    private final OnboardingSessionRepository sessionRepository;

    public RobotOnboardingController(RobotOnboardingService onboardingService,
        OnboardingSessionRepository sessionRepository) {
        this.onboardingService = onboardingService;
        this.sessionRepository = sessionRepository;
    }

    @PostMapping("/sessions")
    @Operation(
        summary = "온보딩 세션을 시작하거나 진행 중인 세션을 이어받는다",
        description = """
            한 어르신의 진행 중 세션은 하나다. 이미 있으면 그것을 돌려주며,
            started_channel 은 바뀌지 않는다 — 앱에서 시작한 세션을 음성으로 이어받을 때
            최초 채널은 APP 으로 남고 개별 답변만 ROBOT 이 된다.

            새 세션을 만들 때만 robotId 가 필요하다.
            """)
    public SessionResponse startOrResume(@Valid @RequestBody StartSessionRequest request) {
        OnboardingSession session = onboardingService.startOrResume(
            request.seniorId(), request.robotId());
        return SessionResponse.of(session, onboardingService.questionSetVersion());
    }

    @GetMapping("/sessions/{sessionId}/next")
    @Operation(
        summary = "다음에 물을 질문 하나",
        description = """
            한 번에 한 질문이다. 로봇이 순서를 정하지 않는다.

            선행 동의가 아직 없으면 그 동의 질문을 먼저 내려준다. 동의를 거절했으면 그에
            딸린 질문은 아예 내려가지 않는다 — 건강정보 동의 전 복약 질문은 계약 위반이다.

            민감 항목(sensitive=true)은 값이 명확해도 전체를 읽어주고 명시적 확인을 받은
            뒤에 보내야 한다. 확인 없이 보낸 답변은 다시 이 목록에 나타난다.

            더 물을 것이 없으면 questionCode 가 null 이고 status 가 COMPLETED 다.
            """)
    public NextQuestionResponse next(@PathVariable UUID sessionId) {
        Optional<QuestionDefinition> question = onboardingService.nextQuestion(sessionId);
        OnboardingSession session = sessionRepository.findById(sessionId)
            .orElseThrow(() -> notFound("onboarding session", sessionId));
        String version = onboardingService.questionSetVersion();

        return question
            .map(q -> NextQuestionResponse.of(sessionId, session.getStatus().name(), q, version))
            .orElseGet(() ->
                NextQuestionResponse.finished(sessionId, session.getStatus().name(), version));
    }

    @PostMapping("/sessions/{sessionId}/answers")
    @Operation(
        summary = "답변을 제출한다",
        description = """
            응답의 outcome 이 다음 행동을 정한다.

              ACCEPTED             다음 질문으로.
              NEEDS_CLARIFICATION  missingFields 의 '한' 필드만 다시 묻는다.
                                   필드명을 소리내어 읽지 말고 사람의 질문으로 바꾼다.
              NEEDS_CONFIRMATION   valueToConfirm 전체를 읽어주고 명시적 확인을 받는다.

            confirmed 는 어르신이 값을 듣고 명시적으로 확인했을 때만 true 다. 침묵,
            주제 변경, "글쎄", "아마도", 불명확한 STT, 다른 질문에 대한 답변은
            확인이 아니다.
            """)
    public SubmitAnswerResponse submitAnswer(@PathVariable UUID sessionId,
        @Valid @RequestBody SubmitAnswerRequest request) {
        return SubmitAnswerResponse.of(onboardingService.submitAnswer(
            sessionId,
            request.questionCode(),
            request.answerValue(),
            request.confirmed(),
            request.conversationId(),
            request.sourceMessageId()));
    }

    private ResponseStatusException notFound(String what, UUID id) {
        return new ResponseStatusException(HttpStatus.NOT_FOUND, "no " + what + " " + id);
    }

    /**
     * Turns a bad request into 400 instead of 500.
     *
     * <p>Scoped to this controller on purpose. A project-wide advice would change the
     * status of every existing endpoint, and that is not this ticket's call to make.</p>
     */
    @org.springframework.web.bind.annotation.ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> badRequest(IllegalArgumentException error) {
        return ResponseEntity.badRequest().body(error.getMessage());
    }
}
