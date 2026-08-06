package com.ssafy.bomi.person;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.person.domain.KnownPerson;
import com.ssafy.bomi.person.repository.KnownPersonRepository;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.ActiveProfiles;

/**
 * H2 slice test — nullable {@code is_deceased} 세 값이 저장·조회를 왕복해도
 * 그대로 남는지, 그리고 {@code findBySeniorId} 가 다른 어르신의 행을 섞지 않는지
 * 확인한다(S15P11E102-260).
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class KnownPersonRepositoryTest {

    @Autowired KnownPersonRepository knownPersonRepository;
    @Autowired TestEntityManager em;

    @Test
    void persistsNullableFieldsAsGiven() {
        UUID guardianId = UUID.randomUUID();
        KnownPerson saved = knownPersonRepository.saveAndFlush(
            KnownPerson.register(UUID.randomUUID(), guardianId, "박정호", "배우자",
                true, "1년 전 지병으로 별세", null, null));
        em.clear();

        KnownPerson found = knownPersonRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getDisplayName()).isEqualTo("박정호");
        assertThat(found.getGuardianUserId()).isEqualTo(guardianId);
        assertThat(found.getIsDeceased()).isTrue();
        assertThat(found.getLivesWith()).isNull();
        assertThat(found.getCreatedAt()).isNotNull();
    }

    @Test
    void findBySeniorIdReturnsOnlyThatSeniorsRows() {
        UUID seniorA = UUID.randomUUID();
        UUID seniorB = UUID.randomUUID();
        knownPersonRepository.saveAndFlush(
            KnownPerson.register(seniorA, null, "박정호", "배우자", true, null, null, null));
        knownPersonRepository.saveAndFlush(
            KnownPerson.register(seniorB, null, "다른명부", "친구", null, null, null, null));

        assertThat(knownPersonRepository.findBySeniorId(seniorA))
            .extracting(KnownPerson::getDisplayName)
            .containsExactly("박정호");
    }
}
