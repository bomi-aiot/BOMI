package com.ssafy.bomi.occupancy;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.occupancy.application.EntranceDirectionResolver;
import com.ssafy.bomi.occupancy.application.EntranceDirectionResolver.Signal;
import com.ssafy.bomi.occupancy.config.EntranceProperties;
import com.ssafy.bomi.occupancy.domain.OccupancyDirection;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * 방향 판정 — S15P11E102-226 완료 조건.
 *
 * <p>순수 로직이라 스프링 없이 돈다. 이 판정이 이 티켓의 전부이고, 여기가 틀리면
 * 귀가가 외출로 기록되어 침묵 사다리가 엉뚱하게 멈춘다.</p>
 */
class EntranceDirectionTest {

    private static final OffsetDateTime T0 = OffsetDateTime.parse("2026-08-02T09:00:00+09:00");

    private EntranceDirectionResolver resolver;
    private UUID senior;

    @BeforeEach
    void setUp() {
        EntranceProperties properties = new EntranceProperties();
        properties.setCorrelationWindow(Duration.ofSeconds(15));
        resolver = new EntranceDirectionResolver(properties);
        senior = UUID.randomUUID();
    }

    @Test
    void doorThenMotionMeansTheyCameHome() {
        assertThat(resolver.observe(senior, Signal.DOOR_OPENED, T0)).isEmpty();

        assertThat(resolver.observe(senior, Signal.MOTION, T0.plusSeconds(3)))
            .contains(OccupancyDirection.IN);
    }

    @Test
    void motionThenDoorMeansTheyLeft() {
        assertThat(resolver.observe(senior, Signal.MOTION, T0)).isEmpty();

        assertThat(resolver.observe(senior, Signal.DOOR_OPENED, T0.plusSeconds(4)))
            .contains(OccupancyDirection.OUT);
    }

    @Test
    void aDoorThatOpensWithNobodyPassingResolvesNothing() {
        /*
         * ★ 문만 열리고 아무도 지나가지 않았다.
         *
         * 창문 환기, 택배 수령, 바람. 여기서 방향을 만들어내면 아무 데도 안 가신
         * 어르신이 AWAY 가 되고 침묵 사다리가 통째로 멈춘다.
         */
        assertThat(resolver.observe(senior, Signal.DOOR_OPENED, T0)).isEmpty();
        assertThat(resolver.observe(senior, Signal.DOOR_OPENED, T0.plusSeconds(2))).isEmpty();
        assertThat(resolver.observe(senior, Signal.DOOR_OPENED, T0.plusSeconds(5))).isEmpty();
    }

    @Test
    void twoMotionsAloneResolveNothing() {
        /*
         * 같은 센서 두 번은 방향이 아니다. 복도를 서성이신 것일 수 있다.
         */
        assertThat(resolver.observe(senior, Signal.MOTION, T0)).isEmpty();
        assertThat(resolver.observe(senior, Signal.MOTION, T0.plusSeconds(3))).isEmpty();
    }

    @Test
    void signalsTooFarApartAreNotOnePassage() {
        /*
         * ★ 창이 없으면 아침에 나가신 것과 저녁에 들어오신 것이 한 통과로 묶인다.
         */
        resolver.observe(senior, Signal.DOOR_OPENED, T0);

        assertThat(resolver.observe(senior, Signal.MOTION, T0.plusSeconds(60))).isEmpty();
    }

    @Test
    void aResolvedPairIsNotReusedByTheNextSignal() {
        /*
         * ★ 짝을 소비하지 않으면 문-모션-모션 연속이 두 번 판정된다.
         *
         * 어르신은 귀가 인사를 두 번 듣게 되고, 두 번째는 아무 일도 없었는데 나온다.
         */
        assertThat(resolver.observe(senior, Signal.DOOR_OPENED, T0))
            .isEmpty();
        assertThat(resolver.observe(senior, Signal.MOTION, T0.plusSeconds(2)))
            .contains(OccupancyDirection.IN);

        assertThat(resolver.observe(senior, Signal.MOTION, T0.plusSeconds(4))).isEmpty();
    }

    @Test
    void twoSeniorsDoNotShareABuffer() {
        /*
         * 한 사람의 문 열림이 다른 사람의 모션과 짝지어지면, 두 집의 재실 상태가
         * 서로를 오염시킨다.
         */
        UUID other = UUID.randomUUID();
        resolver.observe(senior, Signal.DOOR_OPENED, T0);

        assertThat(resolver.observe(other, Signal.MOTION, T0.plusSeconds(2))).isEmpty();
    }

    @Test
    void forgettingClearsAHalfPassage() {
        /*
         * ★ 발화가 재실을 확정했을 때 쓴다.
         *
         * 남겨두면 몇 분 뒤 무관한 신호가 이 반쪽과 짝지어져 없던 방향을 만든다.
         */
        resolver.observe(senior, Signal.DOOR_OPENED, T0);
        resolver.forget(senior);

        assertThat(resolver.observe(senior, Signal.MOTION, T0.plusSeconds(2))).isEmpty();
    }
}
