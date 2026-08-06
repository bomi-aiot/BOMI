package com.ssafy.bomi.config;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

/**
 * {@link RobotChannelAuthProperties#isUsable()} 의 blank 판정만 따로 고정한다.
 *
 * <p>Spring 컨텍스트가 필요 없는 순수 단위 테스트다. 이 판정 하나가 이 티켓의
 * 가장 중요한 완료 조건("시크릿이 비어 있으면 필터가 통과한다")의 기반이므로,
 * 무거운 통합 테스트와 별도로 값 자체를 값싸게 고정해 둔다.</p>
 */
class RobotChannelAuthPropertiesTest {

    @Test
    void blankSecretByDefaultIsNotUsable() {
        RobotChannelAuthProperties properties = new RobotChannelAuthProperties();

        assertThat(properties.isUsable()).isFalse();
    }

    @Test
    void whitespaceOnlySecretIsNotUsable() {
        RobotChannelAuthProperties properties = new RobotChannelAuthProperties();
        properties.setSharedSecret("   ");

        assertThat(properties.isUsable()).isFalse();
    }

    @Test
    void nullSecretIsTreatedAsBlank() {
        RobotChannelAuthProperties properties = new RobotChannelAuthProperties();
        properties.setSharedSecret(null);

        assertThat(properties.isUsable()).isFalse();
        assertThat(properties.getSharedSecret()).isEqualTo("");
    }

    @Test
    void nonBlankSecretIsUsable() {
        RobotChannelAuthProperties properties = new RobotChannelAuthProperties();
        properties.setSharedSecret("real-secret");

        assertThat(properties.isUsable()).isTrue();
    }

    @Test
    void secretIsTrimmed() {
        RobotChannelAuthProperties properties = new RobotChannelAuthProperties();
        properties.setSharedSecret("  real-secret  ");

        assertThat(properties.getSharedSecret()).isEqualTo("real-secret");
    }
}
