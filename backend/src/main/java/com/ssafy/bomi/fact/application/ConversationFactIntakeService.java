package com.ssafy.bomi.fact.application;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactOperation;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.fact.domain.RiskLevel;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 로봇이 자유 대화에서 추출한 사실 후보를 받아 {@code fact_candidate} 큐에 쌓는다
 * (S15P11E102-255).
 *
 * <p>왜 존재하는가 — 지금까지 대화에서 나온 이야기를 기억으로 남기는 통로가 전혀
 * 없었다. 온보딩 답변만 {@link FactCandidate#fromOnboardingAnswer} 로 후보가 됐고,
 * 자유 대화에서 나온 말은 어디에도 쓰이지 않고 증발했다. 이 서비스가 그 두 번째
 * 통로 — {@link FactCandidate#fromConversationMessage} — 의 유일한 진입점이다.</p>
 *
 * <p>일부러 하지 않는 것 — 위험도에 따른 자동저장/확인대기 분기, 동의 여부 확인,
 * 회피 대상 화제 필터링, 중복 억제는 이 서비스의 몫이 아니다. 여기서는 오직
 * "이 conversationId 가 정말 이 어르신의 것인가"만 검증하고 CAPTURED 상태로 쌓는다.
 * 나머지는 후속 처리(위험도 분류·자동 수용)가 별도로 담당한다 — 같은 판단을 두
 * 곳에 흩어 놓지 않기 위해서다.</p>
 *
 * <p>클래스 이름을 {@code FactIntake...} 로 붙인 이유 — 같은 fact 패키지에 이미
 * {@link FactMaterializer} 가 있다. 이 서비스는 확정된 값을 최종 테이블에 쓰는
 * {@code FactMaterializer} 와 반대편 끝(원시 추출 → 큐 적재)을 다루므로, 이름이
 * 겹치면 "무엇을 확정하는 코드"와 "무엇을 큐에 쌓는 코드"가 혼동된다.</p>
 */
@Service
public class ConversationFactIntakeService {

    private final ConversationRepository conversationRepository;
    private final ConversationMessageRepository conversationMessageRepository;
    private final FactCandidateRepository factCandidateRepository;

    public ConversationFactIntakeService(
            ConversationRepository conversationRepository,
            ConversationMessageRepository conversationMessageRepository,
            FactCandidateRepository factCandidateRepository) {
        this.conversationRepository = conversationRepository;
        this.conversationMessageRepository = conversationMessageRepository;
        this.factCandidateRepository = factCandidateRepository;
    }

    /**
     * 대화 한 발화에서 나온 사실 후보 하나를 큐에 쌓는다.
     *
     * <p>무엇을 하는가 — conversationId 가 seniorId 의 것인지, sourceMessageId 가
     * 그 conversationId 에 속하는지 확인한 뒤 {@link FactCandidate#fromConversationMessage}
     * 로 CAPTURED 상태의 행을 만들어 저장한다.</p>
     *
     * <p>왜 두 검증 모두 필요한가 — conversationId 검증만으로는 부족하다.
     * sourceMessageId 는 {@code fact_candidate.source_message_id} 의 물리 FK 대상이고,
     * 다른 대화의 메시지 id 를 실수로 넣으면 근거 발화가 없는(또는 남의) 사실이 이
     * 어르신의 이름으로 저장된다 — conversationId 만 맞고 메시지가 안 맞는 경우를
     * 놓치면 검증이 반쪽이 된다.</p>
     *
     * <p>반환값 — 저장된 {@link FactCandidate}. 컨트롤러가 id 와 status 만 뽑아
     * 응답으로 돌려준다.</p>
     *
     * <p>주의사항 — 잘못된 참조는 {@link IllegalArgumentException} 으로 던진다.
     * 로봇은 "내가 뭔가 잘못 보냈다"와 "서버가 죽었다"를 구분해야 재시도 여부를
     * 결정할 수 있다({@code fact_client.py} 는 실패 시 예외를 던지는 계약이다).</p>
     */
    @Transactional
    public FactCandidate intake(UUID seniorId, UUID conversationId, UUID sourceMessageId,
            FactTargetDomain targetDomain, String factType, FactOperation operation,
            Map<String, Object> proposedValue, RiskLevel riskLevel) {

        Conversation conversation = conversationRepository.findById(conversationId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "unknown conversationId: " + conversationId));
        if (!conversation.getSeniorId().equals(seniorId)) {
            // 다른 어르신의 대화를 조용히 받아들이면 그 사람의 발화가 이 어르신의
            // 기억으로 새어 들어간다. 크게, 즉시 실패한다.
            throw new IllegalArgumentException(
                    "conversation " + conversationId + " does not belong to senior " + seniorId);
        }

        ConversationMessage sourceMessage = conversationMessageRepository.findById(sourceMessageId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "unknown sourceMessageId: " + sourceMessageId));
        if (!sourceMessage.getConversationId().equals(conversationId)) {
            throw new IllegalArgumentException(
                    "message " + sourceMessageId + " does not belong to conversation " + conversationId);
        }

        FactCandidate candidate = FactCandidate.fromConversationMessage(
                seniorId, conversationId, sourceMessageId, targetDomain, factType, operation,
                proposedValue, riskLevel);
        return factCandidateRepository.save(candidate);
    }
}
