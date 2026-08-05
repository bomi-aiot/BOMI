package com.ssafy.bomi.fact.web;

import com.ssafy.bomi.fact.application.ConversationFactIntakeService;
import com.ssafy.bomi.fact.domain.FactCandidate;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 로봇이 자유 대화에서 추출한 사실 후보를 제출하는 쓰기 전용 통로 (S15P11E102-255).
 *
 * <p>왜 별도 엔드포인트인가 — 온보딩 답변은 이미 {@code fact_candidate} 로 들어가는
 * 통로가 있지만(로봇 온보딩 계약), 자유 대화 중에 나온 사실은 그런 통로가 전혀 없었다.
 * 로봇(ai_chat 의 {@code fact_client})이 발화 하나에서 뽑아낸 후보를 여기로 보내면,
 * 서버는 그 conversationId 가 진짜 이 어르신 것인지 확인한 뒤 위험도·동의·회피 대상·
 * 중복을 판정해(전부 {@link ConversationFactIntakeService} 책임) 안전하면 곧장
 * 실체화하고, 아니면 확인 대기로 저장한다.</p>
 */
@RestController
@RequestMapping("/api/v1/robot/fact-candidates")
@Tag(
        name = "Robot Fact Intake",
        description = "대화 사실 후보 제출 — 로봇(ai_chat fact_client)이 호출합니다.")
public class RobotFactIntakeController {

    private final ConversationFactIntakeService service;

    public RobotFactIntakeController(ConversationFactIntakeService service) {
        this.service = service;
    }

    /** 사실 후보 하나를 받아 CAPTURED 상태로 저장하고, 저장된 id 와 status 를 돌려준다. */
    @PostMapping
    public ResponseEntity<FactCandidateIntakeResponse> intake(
            @Valid @RequestBody FactCandidateIntakeRequest request) {

        FactCandidate saved = service.intake(
                request.seniorId(),
                request.conversationId(),
                request.sourceMessageId(),
                request.targetDomain(),
                request.factType(),
                request.operation(),
                request.proposedValue(),
                request.riskLevel());

        return ResponseEntity.status(HttpStatus.CREATED).body(
                new FactCandidateIntakeResponse(saved.getId(), saved.getStatus().name()));
    }

    /**
     * 잘못된 참조는 400 이지 500 이 아니다.
     *
     * <p>로봇은 "내가 잘못 보냈다"와 "서버가 죽었다"를 구분해야 재시도할지 포기할지
     * 결정할 수 있다. 다른 senior 의 conversationId, 존재하지 않는 conversationId/
     * sourceMessageId 가 여기로 걸린다.</p>
     *
     * <p>{@code RobotConversationController} 와 마찬가지로 이 컨트롤러에만 국한한다 —
     * 이 프로젝트에는 전역 {@code @ControllerAdvice} 가 없고, 새로 추가하면 기존 모든
     * 엔드포인트의 응답 코드가 바뀐다. 그것은 이 티켓이 결정할 일이 아니다.</p>
     */
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> handleBadRequest(IllegalArgumentException error) {
        return ResponseEntity.badRequest().body(Map.of("message", error.getMessage()));
    }
}
