package com.ssafy.bomi.config;

import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

/** Registers the operator authentication boundary without affecting existing API channels. */
@Configuration
@SecurityScheme(
    name = OperatorChannelAuthFilterConfig.SECURITY_SCHEME_NAME,
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = OperatorChannelAuthFilter.HEADER_NAME,
    description = "운영자 안전 복구 API 전용 공유 비밀"
)
public class OperatorChannelAuthFilterConfig {

    public static final String SECURITY_SCHEME_NAME = "operatorSharedSecret";

    @Bean
    public FilterRegistrationBean<OperatorChannelAuthFilter> operatorChannelAuthFilter(
        OperatorChannelAuthProperties properties
    ) {
        FilterRegistrationBean<OperatorChannelAuthFilter> registration =
            new FilterRegistrationBean<>();
        registration.setFilter(new OperatorChannelAuthFilter(properties));
        registration.setName("operatorChannelAuthFilter");
        registration.addUrlPatterns("/api/v1/operator/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }
}
