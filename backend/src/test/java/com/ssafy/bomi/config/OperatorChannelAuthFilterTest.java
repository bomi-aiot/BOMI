package com.ssafy.bomi.config;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.FilterChain;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class OperatorChannelAuthFilterTest {

    @Test
    void unconfiguredAuthenticationFailsClosedWithServiceUnavailable() throws Exception {
        OperatorChannelAuthProperties properties = new OperatorChannelAuthProperties();
        OperatorChannelAuthFilter filter = new OperatorChannelAuthFilter(properties);
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicBoolean continued = new AtomicBoolean();

        filter.doFilter(
            new MockHttpServletRequest(),
            response,
            (request, result) -> continued.set(true));

        assertThat(response.getStatus()).isEqualTo(503);
        assertThat(response.getContentAsString()).contains("SERVICE_UNAVAILABLE");
        assertThat(continued).isFalse();
    }

    @Test
    void invalidSecretIsUnauthorized() throws Exception {
        OperatorChannelAuthProperties properties = configuredProperties();
        OperatorChannelAuthFilter filter = new OperatorChannelAuthFilter(properties);
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(OperatorChannelAuthFilter.HEADER_NAME, "wrong");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, noOpChain());

        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getContentAsString()).contains("UNAUTHORIZED");
    }

    @Test
    void authenticatedRequestReceivesServerConfiguredOperatorIdentity() throws Exception {
        OperatorChannelAuthProperties properties = configuredProperties();
        OperatorChannelAuthFilter filter = new OperatorChannelAuthFilter(properties);
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(OperatorChannelAuthFilter.HEADER_NAME, "test-operator-secret");
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicBoolean continued = new AtomicBoolean();

        filter.doFilter(request, response, (filteredRequest, result) -> {
            continued.set(true);
            assertThat(filteredRequest.getAttribute(
                OperatorChannelAuthFilter.OPERATOR_ID_ATTRIBUTE)).isEqualTo("operator-a");
        });

        assertThat(continued).isTrue();
        assertThat(response.getStatus()).isEqualTo(200);
    }

    private static OperatorChannelAuthProperties configuredProperties() {
        OperatorChannelAuthProperties properties = new OperatorChannelAuthProperties();
        properties.setSharedSecret("test-operator-secret");
        properties.setOperatorId("operator-a");
        return properties;
    }

    private static FilterChain noOpChain() {
        return (request, response) -> { };
    }
}
