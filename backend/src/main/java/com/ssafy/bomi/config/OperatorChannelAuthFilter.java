package com.ssafy.bomi.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

/** Fail-closed shared-secret authentication for {@code /api/v1/operator/**}. */
public class OperatorChannelAuthFilter extends OncePerRequestFilter {

    public static final String HEADER_NAME = "X-Operator-Shared-Secret";
    public static final String OPERATOR_ID_ATTRIBUTE =
        "com.ssafy.bomi.config.OperatorChannelAuthFilter.operatorId";

    private final OperatorChannelAuthProperties properties;

    public OperatorChannelAuthFilter(OperatorChannelAuthProperties properties) {
        this.properties = properties;
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        if (!properties.isUsable()) {
            writeError(
                response,
                HttpServletResponse.SC_SERVICE_UNAVAILABLE,
                "SERVICE_UNAVAILABLE",
                "operator authentication is not configured");
            return;
        }

        String provided = request.getHeader(HEADER_NAME);
        if (provided == null || !secretMatches(provided)) {
            writeError(
                response,
                HttpServletResponse.SC_UNAUTHORIZED,
                "UNAUTHORIZED",
                "missing or invalid " + HEADER_NAME + " header");
            return;
        }

        request.setAttribute(OPERATOR_ID_ATTRIBUTE, properties.getOperatorId());
        filterChain.doFilter(request, response);
    }

    private boolean secretMatches(String provided) {
        byte[] expected = properties.getSharedSecret().getBytes(StandardCharsets.UTF_8);
        byte[] actual = provided.getBytes(StandardCharsets.UTF_8);
        return MessageDigest.isEqual(expected, actual);
    }

    private static void writeError(
        HttpServletResponse response,
        int status,
        String error,
        String message
    ) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write(
            "{\"error\":\"" + error + "\",\"message\":\"" + message + "\"}");
    }
}
