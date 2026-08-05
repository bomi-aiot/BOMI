package com.ssafy.bomi.person.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

/**
 * 어르신 주변의 사람 한 명(맵핑 테이블 {@code known_person}).
 *
 * <p>회피 대상("돌아가신 배우자") 판정을 여기로 옮기는 것이 이 엔티티가 존재하는
 * 이유다(S15P11E102-260). 예전에는 {@code app_user.conversation_preferences} 의
 * {@code avoid_topics} 라는 자유 문자열 목록 하나뿐이었고, 이 목록을 채우는
 * 코드가 저장소 어디에도 없어 한 번도 작동한 적이 없었다. 이름·관계·생존 여부를
 * 컬럼으로 분리하면 로봇은 살아 있는 사람 이야기는 자연스럽게 잇고("민수는 잘
 * 있대요?"), 돌아가신 분은 결정론적으로 피할 수 있다(CLAUDE.md §8, §17.5).</p>
 *
 * <p><strong>이 테이블은 {@code memory} 로 가지 않는다.</strong> 벡터 검색 대상이
 * 되는 순간 확률적 필터가 되어 §8 의 결정론적 강제 원칙을 어긴다.</p>
 */
@Entity
@Table(name = "known_person")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class KnownPerson {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "senior_id", nullable = false)
    private UUID seniorId;

    /** 이 사람을 등록한 보호자. 논리 참조이며, 온보딩 등 다른 경로로도 채워질 수 있어 nullable. */
    @Column(name = "guardian_user_id")
    private UUID guardianUserId;

    @Column(name = "display_name", nullable = false, length = 100)
    private String displayName;

    @Column(name = "relationship", length = 50)
    private String relationship;

    /**
     * 생존 여부. {@code null} 은 "모른다"이며, {@code TRUE} 와 똑같이 회피 대상으로
     * 취급된다 — "모르니까 언급해도 된다"는 이 제품에서 가장 위험한 판단이다.
     * 자세한 세 값의 의미는 V10 마이그레이션 주석을 본다.
     */
    @Column(name = "is_deceased")
    private Boolean isDeceased;

    /**
     * 보호자용 내부 메모. <strong>절대 프롬프트에 그대로 노출하지 않는다.</strong>
     * 회피 문구는 정보가 아니라 금지문으로만 전달한다
     * ({@code ConversationContextService} 참고, CLAUDE.md §8).
     */
    @Column(name = "deceased_note", length = 500)
    private String deceasedNote;

    /** 함께 사는지. {@code null} 은 모름이며 {@code FALSE}(따로 산다)와 다르다. */
    @Column(name = "lives_with")
    private Boolean livesWith;

    @Column(name = "contact_frequency", length = 50)
    private String contactFrequency;

    /**
     * 로봇이 이 사람을 마지막으로 거론한 시각. 이 티켓은 컬럼만 만든다 — 자동
     * 갱신은 로봇 쪽 자연스러운 이어짐 기능(CLAUDE.md §17.2)이 붙을 때의 몫이다.
     */
    @Column(name = "last_mentioned_at")
    private OffsetDateTime lastMentionedAt;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    private KnownPerson(UUID seniorId, UUID guardianUserId, String displayName, String relationship,
        Boolean isDeceased, String deceasedNote, Boolean livesWith, String contactFrequency) {
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.guardianUserId = guardianUserId;
        this.displayName = requireText(displayName, "displayName");
        this.relationship = relationship;
        this.isDeceased = isDeceased;
        this.deceasedNote = deceasedNote;
        this.livesWith = livesWith;
        this.contactFrequency = contactFrequency;
    }

    /** 보호자 앱이 사람 한 명을 명부에 등록한다. */
    public static KnownPerson register(UUID seniorId, UUID guardianUserId, String displayName,
        String relationship, Boolean isDeceased, String deceasedNote, Boolean livesWith,
        String contactFrequency) {
        return new KnownPerson(seniorId, guardianUserId, displayName, relationship, isDeceased,
            deceasedNote, livesWith, contactFrequency);
    }

    /** 명부 항목의 필드를 전부 갱신한다(부분 갱신은 지원하지 않는다 — 호출부가 현재 값을 채워 보낸다). */
    public void updateDetails(String displayName, String relationship, Boolean isDeceased,
        String deceasedNote, Boolean livesWith, String contactFrequency) {
        this.displayName = requireText(displayName, "displayName");
        this.relationship = relationship;
        this.isDeceased = isDeceased;
        this.deceasedNote = deceasedNote;
        this.livesWith = livesWith;
        this.contactFrequency = contactFrequency;
    }

    /**
     * 이 사람을 지금 회피 대상으로 취급해야 하는지.
     *
     * <p>{@code TRUE}(사망) 이거나 {@code null}(모름)이면 회피 대상이다. 오직
     * {@code FALSE}(생존 확인됨)만 회피 대상이 아니다.</p>
     */
    public boolean isAvoidTarget() {
        return !Boolean.FALSE.equals(isDeceased);
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value;
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }
}
