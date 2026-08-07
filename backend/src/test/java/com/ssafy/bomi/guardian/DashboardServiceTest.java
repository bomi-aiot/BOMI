package com.ssafy.bomi.guardian;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.guardian.dto.DashboardResponse;
import com.ssafy.bomi.guardian.dto.DashboardResponse.ActivityDto;
import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryType;
import com.ssafy.bomi.memory.domain.MemoryVisibility;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.util.List;
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
}
