package com.ssafy.bomi.guardian;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.NotificationTier;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.guardian.dto.DashboardResponse;
import com.ssafy.bomi.guardian.dto.DashboardResponse.ActivityDto;
import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryType;
import com.ssafy.bomi.memory.domain.MemoryVisibility;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import com.ssafy.bomi.relationship.domain.CareRelationship;
import com.ssafy.bomi.relationship.domain.RelationshipPriority;
import com.ssafy.bomi.relationship.repository.CareRelationshipRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.annotation.Transactional;

/**
 * Verifies the guardian-visibility fix from S15P11E102-262 against a real PostgreSQL.
 *
 * <p>Runs on real PostgreSQL rather than H2 for the same reason
 * {@code ConversationContextServiceTest} does: the schema this reads was built by
 * Flyway and the enum/array columns behave differently under H2.</p>
 *
 * <p>Before this ticket, {@code DashboardService.buildActivities} read memories through
 * {@code MemoryRepository.findTop5BySeniorIdAndLifecycleStatusOrderByFirstObservedAtDesc},
 * which filters only by lifecycle — not visibility. A senior who answered "이건 나만
 * 알고 있을래요" (visibility stays the {@code PRIVATE} default,
 * {@link Memory#create(java.util.UUID, MemoryType, String)}) would have that memory
 * appear on the guardian's screen anyway. These tests pin the fix: PRIVATE never
 * reaches the dashboard, and both guardian-shared visibilities still do.</p>
 */
@SpringBootTest(
    properties = {
        "spring.flyway.enabled=true",
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.jpa.open-in-view=false",
        "bomi.mqtt.enabled=false"
    })
@Transactional
class DashboardServiceTest {

    private static EmbeddedPostgres postgres;

    @Autowired private DashboardService dashboardService;
    @Autowired private AppUserRepository appUserRepository;
    @Autowired private MemoryRepository memoryRepository;
    @Autowired private CareRecordRepository careRecordRepository;
    @Autowired private CareRelationshipRepository careRelationshipRepository;

    private AppUser senior;

    @BeforeAll
    static void startPostgres() throws IOException {
        postgres = EmbeddedPostgres.start();
    }

    @AfterAll
    static void stopPostgres() throws IOException {
        if (postgres != null) {
            postgres.close();
        }
    }

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> postgres.getJdbcUrl("postgres", "postgres"));
        registry.add("spring.datasource.username", () -> "postgres");
        registry.add("spring.datasource.password", () -> "");
        registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
    }

    @BeforeEach
    void setUpSenior() {
        senior = appUserRepository.save(AppUser.create("SENIOR", "김순자", null, "순자님"));
    }

    /** 완료 조건: "보호자 대시보드 조회가 PRIVATE 기억을 제외하는 것을 확인합니다". */
    @Test
    void privateMemoryNeverAppearsOnTheGuardianDashboard() {
        memoryRepository.save(Memory.create(
            senior.getId(), MemoryType.OTHER, "아무에게도 말하지 마세요"));
        memoryRepository.save(Memory.create(
            senior.getId(), MemoryType.OTHER, "보호자와 공유해도 되는 내용",
            MemoryVisibility.SHARED_WITH_GUARDIANS));

        DashboardResponse dashboard = dashboardService.getDashboard();

        List<String> summaries = dashboard.recentActivities().stream()
            .map(ActivityDto::summary)
            .toList();
        assertThat(summaries).contains("보호자와 공유해도 되는 내용");
        assertThat(summaries).doesNotContain("아무에게도 말하지 마세요");
    }

    /** PRIMARY 전용 공유 기억도 (이 대시보드가 가디언을 구분하지 않는 P0라) 여전히 보인다. */
    @Test
    void primaryOnlySharedMemoryStillAppearsOnTheDashboard() {
        memoryRepository.save(Memory.create(
            senior.getId(), MemoryType.OTHER, "주 보호자에게만 공유",
            MemoryVisibility.SHARED_WITH_PRIMARY));

        DashboardResponse dashboard = dashboardService.getDashboard();

        assertThat(dashboard.recentActivities())
            .extracting(ActivityDto::summary)
            .contains("주 보호자에게만 공유");
    }

    /** 운영 화면의 두 회귀를 함께 고정한다: PRIMARY 이름과 T1은 같은 응답에서 살아야 한다. */
    @Test
    void primaryGuardianAndEmergencyAlertAppearOnTheDashboard() {
        AppUser guardian = appUserRepository.save(
            AppUser.create("GUARDIAN", "우동균", null, null));
        careRelationshipRepository.save(CareRelationship.create(
            senior.getId(), guardian.getId(), RelationshipPriority.PRIMARY));

        CareRecord alert = CareRecord.create(
            senior.getId(),
            "GUARDIAN_ALERT",
            Map.of(
                "reason", "emergency",
                "confirmed_by", "no_reply_to_safety_check"));
        alert.markAsNotification(NotificationTier.T1, guardian.getId());
        alert.occurredAt(OffsetDateTime.now().minusMinutes(1));
        careRecordRepository.save(alert);

        DashboardResponse dashboard = dashboardService.getDashboard();

        assertThat(dashboard.guardian()).isNotNull();
        assertThat(dashboard.guardian().name()).isEqualTo("우동균");
        assertThat(dashboard.guardian().priority()).isEqualTo("PRIMARY");
        assertThat(dashboard.recentActivities())
            .filteredOn(activity -> "URGENT".equals(activity.statusLevel()))
            .extracting(ActivityDto::summary)
            .contains("몸이 불편하다고 하신 뒤 확인 질문에 답이 없으셨어요.");
        assertThat(dashboard.todayIncidentCount()).isEqualTo(1);
    }
}
