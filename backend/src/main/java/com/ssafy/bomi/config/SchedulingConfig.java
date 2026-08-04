package com.ssafy.bomi.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 스프링 내장 스케줄러 활성화 (S15P11E102 시나리오 ②).
 *
 * <p>이 프로젝트 최초의 {@code @Scheduled} 사용이다. 시간 트리거가 필요한 작업
 * (복약 알림, 추후 시나리오 타임아웃 워치독)은 모두 이 스위치에 기댄다.</p>
 */
@Configuration
@EnableScheduling
public class SchedulingConfig {

    /**
     * 시각 판단이 필요한 빈은 {@code now()}를 직접 부르지 말고 이 Clock 을 주입받는다.
     * 테스트에서 시계를 고정할 수 있어야 "아침 8시 알림"을 8시까지 기다리지 않고 검증한다.
     */
    @Bean
    public Clock clock() {
        return Clock.systemDefaultZone();
    }
}
