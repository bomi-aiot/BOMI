package com.ssafy.bomi.user;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.ConsentStatus;
import com.ssafy.bomi.user.domain.OnboardingStatus;
import com.ssafy.bomi.user.domain.UserStatus;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.ActiveProfiles;

@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class AppUserRepositoryTest {

    @Autowired AppUserRepository appUserRepository;
    @Autowired TestEntityManager em;

    @Test
    void persistsUuidEnumsJsonAndAuditTimestamps() {
        AppUser user = AppUser.create("SENIOR", "김보미", "bomi@example.com", "보미");
        user.updateConversationPreferences(Map.of("tone", "warm", "speed", 2));

        AppUser saved = appUserRepository.saveAndFlush(user);
        UUID id = saved.getId();
        em.clear();

        AppUser found = appUserRepository.findById(id).orElseThrow();
        assertThat(found.getId()).isNotNull();
        assertThat(found.getUserType()).isEqualTo("SENIOR");
        assertThat(found.getName()).isEqualTo("김보미");
        assertThat(found.getOnboardingStatus()).isEqualTo(OnboardingStatus.NOT_STARTED);
        assertThat(found.getStatus()).isEqualTo(UserStatus.ACTIVE);
        assertThat(found.getPersonalizationConsentStatus()).isEqualTo(ConsentStatus.NOT_REQUESTED);
        assertThat(found.getTimeZone()).isEqualTo("Asia/Seoul");
        assertThat(found.getConversationPreferences()).containsEntry("tone", "warm");
        assertThat(found.getCreatedAt()).isNotNull();
        assertThat(found.getUpdatedAt()).isNotNull();
    }

    @Test
    void enumIsStoredAsString() {
        AppUser user = AppUser.create("GUARDIAN", "이보호");
        user.changeStatus(UserStatus.INACTIVE);
        AppUser saved = appUserRepository.saveAndFlush(user);
        em.clear();

        Object raw = em.getEntityManager()
            .createNativeQuery("select status from app_user where id = ?1")
            .setParameter(1, saved.getId())
            .getSingleResult();
        assertThat(raw.toString()).isEqualTo("INACTIVE");
    }
}
