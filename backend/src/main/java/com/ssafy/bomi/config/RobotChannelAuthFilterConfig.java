package com.ssafy.bomi.config;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

/**
 * {@link RobotChannelAuthFilter} 를 서블릿 컨테이너에 등록한다 (S15P11E102-307).
 *
 * <p><b>무엇을 하는가.</b> {@code FilterRegistrationBean} 은 스프링이 순수
 * {@code jakarta.servlet.Filter} 를 서블릿 컨테이너에 "이 URL 패턴에서만 돌아라"
 * 라고 알려주는 방법이다. 필터 클래스 자체에는 URL 조건을 걸 수 없어서(서블릿
 * 스펙이 그렇다), 등록하는 쪽에서 지정한다.</p>
 *
 * <p><b>왜 별도 설정 클래스인가.</b> {@link RobotChannelAuthFilter} 를
 * {@code @Component} 로 직접 스캔하게 두면 이 프로젝트의 {@code @WebMvcTest}
 * 슬라이스 테스트가 컨트롤러 레이어만 좁게 띄우면서도 {@code Filter} 구현체는
 * 함께 끌어들여, 그 필터가 요구하는 {@link RobotChannelAuthProperties} 빈이
 * 없어 컨텍스트 로딩에 실패한다(실제로 HealthControllerTest 가 이렇게
 * 깨졌다). 평범한 {@code @Configuration} 안에서 수동으로 만들면 슬라이스
 * 테스트의 타입 필터가 이 클래스 자체를 스캔 대상에서 제외하므로 문제가
 * 사라진다.</p>
 *
 * <p><b>URL 패턴은 서블릿 스펙 문법이다.</b> springdoc 그룹 설정이 쓰는
 * {@code /api/v1/robot/**} (Ant 스타일)과 달리, 서블릿 컨테이너의 접두사
 * 매핑은 {@code /api/v1/robot/*} (별표 하나)로 쓴다. 의미는 같다 — 그 아래
 * 모든 하위 경로에 걸린다.</p>
 */
@Configuration
public class RobotChannelAuthFilterConfig {

    @Bean
    public FilterRegistrationBean<RobotChannelAuthFilter> robotChannelAuthFilter(
        RobotChannelAuthProperties properties
    ) {
        FilterRegistrationBean<RobotChannelAuthFilter> registration = new FilterRegistrationBean<>();
        registration.setFilter(new RobotChannelAuthFilter(properties));
        registration.setName("robotChannelAuthFilter");
        // springdoc bomi-robot 그룹(application.yml)과 같은 두 접두사.
        registration.addUrlPatterns("/api/v1/robot/*", "/api/v1/seniors/*");
        // 다른 필터보다 먼저 돌아야 한다 — 인증 전에 어떤 로직도 실행되면 안 된다.
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }
}
