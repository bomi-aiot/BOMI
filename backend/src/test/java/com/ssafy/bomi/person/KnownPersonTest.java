package com.ssafy.bomi.person;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ssafy.bomi.person.domain.KnownPerson;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/**
 * {@link KnownPerson#isAvoidTarget()} 의 세 값 판정을 순수 도메인 단위로 고정한다
 * (S15P11E102-260). 이 판정이 흔들리면 회피 목록 전체가 흔들린다.
 */
class KnownPersonTest {

    @Test
    void deceasedIsAnAvoidTarget() {
        KnownPerson person = KnownPerson.register(
            UUID.randomUUID(), null, "박정호", "배우자", true, null, null, null);
        assertThat(person.isAvoidTarget()).isTrue();
    }

    /** 모르는 상태(NULL)는 안전한 기본값으로 사망과 똑같이 취급한다(완료 조건). */
    @Test
    void unknownSurvivalStatusIsAnAvoidTargetToo() {
        KnownPerson person = KnownPerson.register(
            UUID.randomUUID(), null, "이영희", "친구", null, null, null, null);
        assertThat(person.isAvoidTarget()).isTrue();
    }

    @Test
    void confirmedLivingIsNotAnAvoidTarget() {
        KnownPerson person = KnownPerson.register(
            UUID.randomUUID(), null, "김민수", "아들", false, null, false, "주 1회");
        assertThat(person.isAvoidTarget()).isFalse();
    }

    @Test
    void blankDisplayNameIsRejected() {
        assertThatThrownBy(() -> KnownPerson.register(
            UUID.randomUUID(), null, "  ", "친구", null, null, null, null))
            .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void updateDetailsReplacesEveryFieldAndCanFlipSurvivalStatus() {
        KnownPerson person = KnownPerson.register(
            UUID.randomUUID(), null, "이영희", "친구", null, null, null, null);

        person.updateDetails("이영희", "친구", false, null, true, "매일");

        assertThat(person.isAvoidTarget()).isFalse();
        assertThat(person.getLivesWith()).isTrue();
        assertThat(person.getContactFrequency()).isEqualTo("매일");
    }
}
