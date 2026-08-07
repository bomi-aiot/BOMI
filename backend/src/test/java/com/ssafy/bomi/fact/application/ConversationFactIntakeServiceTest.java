package com.ssafy.bomi.fact.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.domain.MessageRole;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.fact.application.FactMaterializer.MaterializedTarget;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
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
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

/**
 * {@link ConversationFactIntakeService} 단위 테스트 (S15P11E102-255).
 *
 * <p>실제 DB 대신 리포지토리를 목(mock)으로 대체한다. {@code FactMaterializer} 도
 * 목으로 대체하되, {@code materialize(...)} 스텁이 실제 구현처럼
 * {@code candidate.materialize(...)} 를 호출하도록 답을 만들어, 이 클래스가 정말
 * "확정 → 실체화 호출 → 상태 전이" 순서를 지키는지 검증한다. Memory/CareRecord
 * 저장 자체의 세부 동작은 {@code FactMaterializerTest} 의 몫이다.</p>
 */
class ConversationFactIntakeServiceTest {

    private final ConversationRepository conversationRepository = mock(ConversationRepository.class);
    private final ConversationMessageRepository conversationMessageRepository =
            mock(ConversationMessageRepository.class);
    private final FactCandidateRepository factCandidateRepository = mock(FactCandidateRepository.class);
    private final AppUserRepository appUserRepository = mock(AppUserRepository.class);
    private final KnownPersonRepository knownPersonRepository = mock(KnownPersonRepository.class);
    private final FactMaterializer factMaterializer = mock(FactMaterializer.class);

    private ConversationFactIntakeService service;

    private final UUID seniorId = UUID.randomUUID();
    private final UUID conversationId = UUID.randomUUID();
    private final UUID sourceMessageId = UUID.randomUUID();

    @BeforeEach
    void setUp() {
        service = new ConversationFactIntakeService(
                conversationRepository, conversationMessageRepository, factCandidateRepository,
                appUserRepository, knownPersonRepository, factMaterializer);

        when(conversationRepository.findById(conversationId))
                .thenReturn(Optional.of(conversationOf(seniorId)));
        when(conversationMessageRepository.findById(sourceMessageId))
                .thenReturn(Optional.of(messageIn(conversationId)));
        when(appUserRepository.findById(seniorId)).thenReturn(Optional.of(consentingSenior()));
        when(factCandidateRepository.save(any(FactCandidate.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));
        // 실제 FactMaterializer 처럼 confirm 된 candidate 를 MATERIALIZED 로 올린다.
        when(factMaterializer.materialize(any(FactCandidate.class), any(Map.class)))
                .thenAnswer(invocation -> {
                    FactCandidate candidate = invocation.getArgument(0);
                    UUID targetId = UUID.randomUUID();
                    candidate.materialize(targetId);
                    return Optional.of(new MaterializedTarget(candidate.getTargetDomain(), targetId));
                });
    }

    private Conversation conversationOf(UUID owner) {
        return Conversation.open(owner);
    }

    private ConversationMessage messageIn(UUID inConversationId) {
        return ConversationMessage.of(
                inConversationId, 0, MessageRole.SENIOR, "요즘 손자가 자주 놀러 와요", OffsetDateTime.now());
    }

    private AppUser consentingSenior() {
        AppUser senior = AppUser.create("SENIOR", "김순자");
        senior.changePersonalizationConsent(ConsentStatus.GRANTED);
        senior.changeHealthDataConsent(ConsentStatus.GRANTED);
        senior.changeScheduleConsent(ConsentStatus.GRANTED);
        return senior;
    }

    private FactCandidate intakeMemoryFact() {
        return service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.MEMORY, "family_event", FactOperation.CREATE,
                Map.of("content", "손자가 자주 놀러 온다"), RiskLevel.NORMAL);
    }

    // ---- 기존 소유권 검증 (그대로 유지) ----

    @Test
    void rejectsConversationThatBelongsToAnotherSenior() {
        UUID otherSenior = UUID.randomUUID();
        when(conversationRepository.findById(conversationId))
                .thenReturn(Optional.of(conversationOf(otherSenior)));

        assertThatThrownBy(() -> intakeMemoryFact())
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining(conversationId.toString())
                .hasMessageContaining(seniorId.toString());

        verifyNoInteractions(factCandidateRepository);
    }

    @Test
    void rejectsUnknownConversationId() {
        when(conversationRepository.findById(conversationId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> intakeMemoryFact())
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining(conversationId.toString());

        verifyNoInteractions(factCandidateRepository);
    }

    @Test
    void rejectsMessageThatBelongsToAnotherConversation() {
        UUID otherConversationId = UUID.randomUUID();
        when(conversationMessageRepository.findById(sourceMessageId))
                .thenReturn(Optional.of(messageIn(otherConversationId)));

        assertThatThrownBy(() -> intakeMemoryFact())
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining(sourceMessageId.toString())
                .hasMessageContaining(conversationId.toString());

        verifyNoInteractions(factCandidateRepository);
    }

    @Test
    void rejectsUnknownSourceMessageId() {
        when(conversationMessageRepository.findById(sourceMessageId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> intakeMemoryFact())
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining(sourceMessageId.toString());

        verifyNoInteractions(factCandidateRepository);
    }

    // ---- targetDomain 거절 (신규) ----

    @Test
    void rejectsProfileDomainOutright() {
        assertThatThrownBy(() -> service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.PROFILE, "preferred_name", FactOperation.UPDATE,
                Map.of("content", "x"), RiskLevel.NORMAL))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("PROFILE");

        verifyNoInteractions(conversationRepository, factCandidateRepository);
    }

    @Test
    void rejectsCareRelationshipDomainOutright() {
        assertThatThrownBy(() -> service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.CARE_RELATIONSHIP, "primary_guardian", FactOperation.UPDATE,
                Map.of("content", "x"), RiskLevel.NORMAL))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("CARE_RELATIONSHIP");
    }

    // ---- 중복 제출 (신규) ----

    @Test
    void returnsExistingCandidateInsteadOfDuplicatingOnRetry() {
        FactCandidate existing = FactCandidate.fromConversationMessage(seniorId, conversationId,
                sourceMessageId, FactTargetDomain.MEMORY, "family_event", FactOperation.CREATE,
                Map.of("content", "이미 받은 사실"), RiskLevel.NORMAL);
        when(factCandidateRepository.findBySeniorIdAndSourceMessageIdAndFactType(
                seniorId, sourceMessageId, "family_event"))
                .thenReturn(Optional.of(existing));

        FactCandidate result = intakeMemoryFact();

        assertThat(result).isSameAs(existing);
        verify(factCandidateRepository, never()).save(any());
        verifyNoInteractions(appUserRepository);
    }

    // ---- 동의 거부 (신규) ----

    @Test
    void rejectsWhenPersonalizationConsentNotGranted() {
        AppUser senior = AppUser.create("SENIOR", "김순자");
        senior.changePersonalizationConsent(ConsentStatus.DENIED);
        when(appUserRepository.findById(seniorId)).thenReturn(Optional.of(senior));

        FactCandidate saved = intakeMemoryFact();

        assertThat(saved.getStatus()).isEqualTo(FactCandidateStatus.REJECTED);
        verifyNoInteractions(factMaterializer);
    }

    @Test
    void rejectsHealthFactWhenHealthDataConsentNotGranted() {
        AppUser senior = AppUser.create("SENIOR", "김순자");
        senior.changePersonalizationConsent(ConsentStatus.GRANTED);
        senior.changeHealthDataConsent(ConsentStatus.DENIED);
        when(appUserRepository.findById(seniorId)).thenReturn(Optional.of(senior));

        FactCandidate saved = service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.CARE_RECORD, "MEDICATION", FactOperation.UPDATE,
                Map.of("content", "이제 아침 약 안 먹어"), RiskLevel.SENSITIVE);

        assertThat(saved.getStatus()).isEqualTo(FactCandidateStatus.REJECTED);
        verifyNoInteractions(factMaterializer);
    }

    // ---- 회피 대상 (신규) ----

    @Test
    void rejectsFactMentioningAnAvoidedPerson() {
        KnownPerson deceasedSpouse = KnownPerson.register(
                seniorId, null, "박정호", "배우자", true, "1년 전 지병으로 별세", null, null);
        when(knownPersonRepository.findBySeniorId(seniorId)).thenReturn(List.of(deceasedSpouse));

        FactCandidate saved = service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.MEMORY, "family_event", FactOperation.CREATE,
                Map.of("content", "박정호씨가 좋아하던 노래를 들었다"), RiskLevel.NORMAL);

        assertThat(saved.getStatus()).isEqualTo(FactCandidateStatus.REJECTED);
        verifyNoInteractions(factMaterializer);
    }

    @Test
    void doesNotRejectWhenTheMentionedPersonIsConfirmedAlive() {
        KnownPerson livingRelative = KnownPerson.register(
                seniorId, null, "김민수", "아들", false, null, false, "주 1회");
        when(knownPersonRepository.findBySeniorId(seniorId)).thenReturn(List.of(livingRelative));

        FactCandidate saved = service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.MEMORY, "family_event", FactOperation.CREATE,
                Map.of("content", "김민수가 놀러왔다"), RiskLevel.NORMAL);

        assertThat(saved.getStatus()).isEqualTo(FactCandidateStatus.MATERIALIZED);
    }

    // ---- 하루 상한 (신규) ----

    @Test
    void rejectsWhenDailyIntakeCapIsExceeded() {
        when(factCandidateRepository.countBySeniorIdAndSourceTypeAndCreatedAtAfter(
                org.mockito.ArgumentMatchers.eq(seniorId),
                org.mockito.ArgumentMatchers.eq(FactSourceType.CONVERSATION_MESSAGE),
                any(OffsetDateTime.class)))
                .thenReturn(50L);

        FactCandidate saved = intakeMemoryFact();

        assertThat(saved.getStatus()).isEqualTo(FactCandidateStatus.REJECTED);
        verifyNoInteractions(factMaterializer);
    }

    // ---- 위험도 분류 → 실체화 / 확인 대기 (신규, 이 티켓의 본체) ----

    @Test
    void memoryDomainFactIsAutoMaterializedAsPrivate() {
        FactCandidate saved = intakeMemoryFact();

        assertThat(saved.getStatus()).isEqualTo(FactCandidateStatus.MATERIALIZED);
        assertThat(saved.getMaterializedTargetId()).isNotNull();

        ArgumentCaptor<FactCandidate> captor = ArgumentCaptor.forClass(FactCandidate.class);
        verify(factMaterializer).materialize(captor.capture(), any(Map.class));
        assertThat(captor.getValue().getStatus()).isEqualTo(FactCandidateStatus.MATERIALIZED);
    }

    @Test
    void careRecordScheduleFactIsAutoMaterialized() {
        FactCandidate saved = service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.CARE_RECORD, "APPOINTMENT", FactOperation.CREATE,
                Map.of("content", "다음 주 화요일 병원 예약"), RiskLevel.NORMAL);

        assertThat(saved.getStatus()).isEqualTo(FactCandidateStatus.MATERIALIZED);
        verify(factMaterializer).materialize(any(FactCandidate.class), any(Map.class));
    }

    @Test
    void careRecordMedicationFactNeedsConfirmationInsteadOfAutoSave() {
        FactCandidate saved = service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.CARE_RECORD, "MEDICATION", FactOperation.UPDATE,
                Map.of("content", "이제 아침 약 안 먹어"), RiskLevel.SENSITIVE);

        assertThat(saved.getStatus()).isEqualTo(FactCandidateStatus.NEEDS_CONFIRMATION);
        verifyNoInteractions(factMaterializer);
    }

    @Test
    void careRecordUnknownFactTypeAlsoNeedsConfirmation() {
        // 목록에 없는 낯선 factType 은 안전하다고 가정하지 않는다 — 기본값은 확인 대기다.
        FactCandidate saved = service.intake(seniorId, conversationId, sourceMessageId,
                FactTargetDomain.CARE_RECORD, "SOMETHING_NEW", FactOperation.CREATE,
                Map.of("content", "x"), RiskLevel.NORMAL);

        assertThat(saved.getStatus()).isEqualTo(FactCandidateStatus.NEEDS_CONFIRMATION);
        verifyNoInteractions(factMaterializer);
    }

    @Test
    void capturesProposedValueBeforeMaterializing() {
        intakeMemoryFact();

        ArgumentCaptor<FactCandidate> captor = ArgumentCaptor.forClass(FactCandidate.class);
        verify(factCandidateRepository).save(captor.capture());
        assertThat(captor.getValue().getSourceType()).isEqualTo(FactSourceType.CONVERSATION_MESSAGE);
        assertThat(captor.getValue().getConfirmedValue()).containsEntry("content", "손자가 자주 놀러 온다");
    }
}
