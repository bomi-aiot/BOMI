package com.ssafy.bomi.fact.application;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactOperation;
import com.ssafy.bomi.fact.domain.FactSourceType;
import com.ssafy.bomi.fact.domain.FactTargetDomain;
import com.ssafy.bomi.fact.domain.RiskLevel;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import com.ssafy.bomi.person.domain.KnownPerson;
import com.ssafy.bomi.person.repository.KnownPersonRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.ConsentStatus;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 로봇이 자유 대화에서 추출한 사실 후보를 받아 위험도에 따라 갈라 처리한다
 * (S15P11E102-255).
 *
 * <p>왜 존재하는가 — 지금까지 대화에서 나온 이야기를 기억으로 남기는 통로가 전혀
 * 없었다. 온보딩 답변만 {@link FactCandidate#fromOnboardingAnswer} 로 후보가 됐고,
 * 자유 대화에서 나온 말은 어디에도 쓰이지 않고 증발했다. 이 서비스가 그 두 번째
 * 통로 — {@link FactCandidate#fromConversationMessage} — 의 유일한 진입점이다.</p>
 *
 * <p>무엇을 새로 하는가(S15P11E102-255 위험도 분류 후속 작업) — 처음 배선했을 때는
 * "이 conversationId 가 정말 이 어르신의 것인가"만 검증하고 전부 CAPTURED 로 쌓았다.
 * 그 상태로는 "요즘 손자가 놀러 온다"와 "이제 아침 약 안 먹어"가 똑같이 취급돼,
 * 후자가 확인 없이 반영될 위험이 있었다. 지금은 입구에서 네 가지를 순서대로
 * 확인한다 — (1) targetDomain 이 이 경로가 다룰 수 있는 것인가, (2) 같은 발화·같은
 * factType 을 이미 받은 적이 있는가(재시도 중복), (3) 동의·회피 대상·하루 상한을
 * 통과하는가, (4) {@link FactRiskPolicy} 가 안전하다고 보는가 — 안전하면
 * {@link FactMaterializer} 로 곧장 실체화하고, 아니면 NEEDS_CONFIRMATION 으로 남겨
 * 재질의·가디언웹 확인을 기다린다.</p>
 *
 * <p>클래스 이름을 {@code FactIntake...} 로 붙인 이유 — 같은 fact 패키지에 이미
 * {@link FactMaterializer} 가 있다. 이 서비스는 원시 추출을 받아 안전 여부까지
 * 판정하는 입구이고, {@code FactMaterializer} 는 확정된 값을 최종 테이블에 쓰는
 * 도구다. 이름이 겹치면 "무엇을 판정하는 코드"와 "무엇을 쓰는 코드"가 혼동된다.</p>
 */
@Service
public class ConversationFactIntakeService {

    /**
     * 하루 저장 건수 상한(S15P11E102-255 작업 내용 #6). 추출 프롬프트가 오작동해
     * 같은 대화에서 수십 건을 뽑아내는 사고를 막는 마지막 안전판이다 — 정상적인
     * 하루 대화량으로는 절대 닿지 않을 값으로 넉넉히 잡았다.
     */
    private static final int DAILY_INTAKE_CAP = 50;

    private final ConversationRepository conversationRepository;
    private final ConversationMessageRepository conversationMessageRepository;
    private final FactCandidateRepository factCandidateRepository;
    private final AppUserRepository appUserRepository;
    private final KnownPersonRepository knownPersonRepository;
    private final FactMaterializer factMaterializer;

    public ConversationFactIntakeService(
            ConversationRepository conversationRepository,
            ConversationMessageRepository conversationMessageRepository,
            FactCandidateRepository factCandidateRepository,
            AppUserRepository appUserRepository,
            KnownPersonRepository knownPersonRepository,
            FactMaterializer factMaterializer) {
        this.conversationRepository = conversationRepository;
        this.conversationMessageRepository = conversationMessageRepository;
        this.factCandidateRepository = factCandidateRepository;
        this.appUserRepository = appUserRepository;
        this.knownPersonRepository = knownPersonRepository;
        this.factMaterializer = factMaterializer;
    }

    /**
     * 대화 한 발화에서 나온 사실 후보 하나를 받아 처리한다.
     *
     * <p>무엇을 하는가 — conversationId·sourceMessageId 소유권을 검증한 뒤, 안전하지
     * 않은 targetDomain 은 즉시 400 으로 거절한다. 이미 받은 적 있는 (발화, factType)
     * 조합이면 새 행을 만들지 않고 기존 행을 그대로 돌려준다(재시도 안전). 그다음
     * 동의·회피 대상·하루 상한을 확인해 위반하면 REJECTED 로 저장한다. 전부 통과하면
     * {@link FactRiskPolicy} 로 안전 여부를 판정해 안전하면 곧장 실체화(MATERIALIZED),
     * 아니면 확인 대기(NEEDS_CONFIRMATION)로 저장한다.</p>
     *
     * <p>왜 거절도 저장하는가 — REJECTED 행 자체가 감사 기록이다. "이 사실이 왜
     * 반영되지 않았는지"를 나중에 되짚을 수 있어야 하고, 다음 flush 가 같은 발화를
     * 또 보내와도 dedup 조회가 이 행을 찾아 조용히 넘어갈 수 있다.</p>
     *
     * <p>왜 targetDomain 거절만 예외를 던지는가 — PROFILE/CARE_RELATIONSHIP 은
     * {@link FactMaterializer} 가 애초에 쓸 최종 테이블이 없다고 밝히고 있다(항상
     * {@code Optional.empty()}). 대화 추출이 이 도메인을 제안하는 것 자체가 호출부
     * (로봇 프롬프트) 설계 오류이지, 정상적으로 일어날 수 있는 비즈니스 상황이
     * 아니다 — 그래서 로봇이 "내가 잘못 보냈다"를 즉시 알 수 있도록 400 으로 끊는다.
     * 반면 동의 거부·회피 대상·하루 상한 초과는 정상적인 운영 중에도 일어나는
     * 합법적인 거절이라, 200번대로 응답하고 상태로만 구분한다 — 안 그러면 재시도
     * 없는 flush 루프가 매번 같은 오류를 반복해서 받는다(§18 큐 재시도 설계와 같은
     * 이유).</p>
     *
     * <p>반환값 — 저장된(또는 이미 있던) {@link FactCandidate}. 컨트롤러가 id 와
     * status 만 뽑아 응답으로 돌려준다.</p>
     */
    @Transactional
    public FactCandidate intake(UUID seniorId, UUID conversationId, UUID sourceMessageId,
            FactTargetDomain targetDomain, String factType, FactOperation operation,
            Map<String, Object> proposedValue, RiskLevel riskLevel) {

        if (targetDomain == FactTargetDomain.PROFILE || targetDomain == FactTargetDomain.CARE_RELATIONSHIP) {
            throw new IllegalArgumentException(
                    "targetDomain " + targetDomain + " is not accepted from conversation extraction");
        }

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

        return factCandidateRepository
                .findBySeniorIdAndSourceMessageIdAndFactType(seniorId, sourceMessageId, factType)
                .orElseGet(() -> captureAndClassify(seniorId, conversationId, sourceMessageId,
                        targetDomain, factType, operation, proposedValue, riskLevel));
    }

    private FactCandidate captureAndClassify(UUID seniorId, UUID conversationId, UUID sourceMessageId,
            FactTargetDomain targetDomain, String factType, FactOperation operation,
            Map<String, Object> proposedValue, RiskLevel riskLevel) {

        AppUser senior = appUserRepository.findById(seniorId)
                .orElseThrow(() -> new IllegalArgumentException("unknown seniorId: " + seniorId));

        FactCandidate candidate = FactCandidate.fromConversationMessage(
                seniorId, conversationId, sourceMessageId, targetDomain, factType, operation,
                proposedValue, riskLevel);

        if (!isConsentGranted(senior, factType)
                || mentionsAvoidedPerson(seniorId, proposedValue)
                || exceedsDailyCap(seniorId)) {
            candidate.reject();
            return factCandidateRepository.save(candidate);
        }

        if (FactRiskPolicy.isSafeForAutoMaterialization(targetDomain, factType)) {
            candidate.confirm(proposedValue, null);
            factMaterializer.materialize(candidate, proposedValue);
        } else {
            candidate.needsConfirmation();
        }
        return factCandidateRepository.save(candidate);
    }

    /**
     * 개인화 동의가 기본 전제고, 건강·일정류 factType 은 각각의 세부 동의도
     * 요구한다 — {@code ConversationContextService.isGranted} 와 같은 "명시적
     * GRANTED 만 통과, 나머지는 전부 막는다"는 원칙을 따른다(읽기 경로와 쓰기 경로가
     * 다른 기준으로 동의를 판단하면 둘 중 하나는 반드시 어긋난다).
     */
    private boolean isConsentGranted(AppUser senior, String factType) {
        if (senior.getPersonalizationConsentStatus() != ConsentStatus.GRANTED) {
            return false;
        }
        if (FactRiskPolicy.requiresHealthConsent(factType)) {
            return senior.getHealthDataConsentStatus() == ConsentStatus.GRANTED;
        }
        if (FactRiskPolicy.requiresScheduleConsent(factType)) {
            return senior.getScheduleConsentStatus() == ConsentStatus.GRANTED;
        }
        return true;
    }

    /**
     * proposedValue 의 서술 텍스트가 회피 대상 인물의 이름을 담고 있는지 본다.
     *
     * <p>{@code ConversationContextService.extractAvoidTopics} 를 그대로 재사용하지
     * 않은 이유 — 그 메서드는 "회피 문구 목록"을 만들지만, 여기서 필요한 것은 "이
     * 특정 제안값이 회피 대상을 언급하는가"라는 다른 질문이다. {@code known_person}
     * 이 하나도 없는 어르신은(아직 아무도 등록 안 됨) 걸러낼 대상 자체가 없으므로
     * 통과시킨다 — jsonb 호환 폴백은 여기서 다루지 않는다. 이 게이트가 놓치는
     * 것보다 문맥 조립(읽기 경로) 쪽 결정론적 필터가 최종 방어선이기 때문이다.</p>
     */
    private boolean mentionsAvoidedPerson(UUID seniorId, Map<String, Object> proposedValue) {
        List<KnownPerson> registered = knownPersonRepository.findBySeniorId(seniorId);
        if (registered.isEmpty()) {
            return false;
        }
        String text = extractText(proposedValue);
        if (text.isBlank()) {
            return false;
        }
        String lowered = text.toLowerCase(Locale.ROOT);
        return registered.stream()
                .filter(KnownPerson::isAvoidTarget)
                .anyMatch(person -> lowered.contains(person.getDisplayName().toLowerCase(Locale.ROOT)));
    }

    private static String extractText(Map<String, Object> proposedValue) {
        Object content = proposedValue.get("content");
        return content != null ? content.toString() : "";
    }

    private boolean exceedsDailyCap(UUID seniorId) {
        long countToday = factCandidateRepository.countBySeniorIdAndSourceTypeAndCreatedAtAfter(
                seniorId, FactSourceType.CONVERSATION_MESSAGE, OffsetDateTime.now().minusDays(1));
        return countToday >= DAILY_INTAKE_CAP;
    }
}
