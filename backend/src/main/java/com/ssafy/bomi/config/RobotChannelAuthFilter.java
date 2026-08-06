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

/**
 * 로봇 채널 인증 필터 — 로봇(ai_chat)만 {@code /api/v1/robot/**}, {@code /api/v1/seniors/**}
 * 를 호출할 수 있게 막는다 (S15P11E102-307).
 *
 * <p><b>왜 Spring Security 가 아니라 서블릿 필터인가.</b> 스타터를 넣으면 기본
 * 필터체인이 켜져 actuator·swagger·정적 문서 경로까지 규칙을 다시 써야 하고,
 * 기존 MockMvc 테스트가 한꺼번에 401로 돈다. 지금 필요한 것은 "이 두 경로에
 * 헤더 하나가 맞는지"뿐이라 {@link OncePerRequestFilter} 하나로 충분하다. 이
 * 클래스는 서블릿 필터가 무엇인지 처음 보는 사람을 위한 것이다 — 매 요청마다
 * 컨트롤러보다 먼저 실행되어 통과시키거나(doFilter 호출) 여기서 응답을 끝낸다.</p>
 *
 * <p><b>경로는 이 클래스가 정하지 않는다.</b> 어떤 경로에 이 필터가 걸리는지는
 * {@link RobotChannelAuthFilterConfig} 가 {@code FilterRegistrationBean} 으로
 * 등록할 때 정한다 — springdoc 그룹 설정(application.yml 의
 * {@code springdoc.group-configs})이 이미 "로봇·AI 채널"의 경계로 선언해 둔
 * {@code /api/v1/robot/**}, {@code /api/v1/seniors/**} 와 같은 접두사다. 새 경로
 * 규칙을 여기서 발명하지 않는다.</p>
 *
 * <p><b>왜 이 클래스에 {@code @Component} 를 붙이지 않는가.</b> 붙이면
 * {@code @WebMvcTest} 슬라이스 테스트(예: HealthControllerTest)가 컨트롤러
 * 레이어만 좁게 띄우면서도 {@code jakarta.servlet.Filter} 구현체는 자동으로
 * 함께 스캔해 포함시킨다. 그러면 이 필터의 생성자가 요구하는
 * {@link RobotChannelAuthProperties} 빈이 그 좁은 컨텍스트에는 없어
 * {@code NoSuchBeanDefinitionException} 으로 기존 테스트가 깨진다. 등록을
 * {@link RobotChannelAuthFilterConfig} 의 평범한 {@code @Bean} 메서드로 옮기면
 * 슬라이스 테스트의 타입 필터가 그 설정 클래스 자체를 제외하므로 문제가
 * 사라진다 (실제로 이 문제를 겪고 나서 이 구조로 고쳤다).</p>
 *
 * <p><b>시크릿이 비어 있으면 무조건 통과.</b> {@link RobotChannelAuthProperties#isUsable()}
 * 이 false 면 이 필터는 아무 요청도 막지 않는다 — 로컬 개발과 기존 테스트가
 * 시크릿 설정 없이도 그대로 통과해야 하는 것이 이 티켓의 가장 중요한 완료
 * 조건이다.</p>
 */
public class RobotChannelAuthFilter extends OncePerRequestFilter {

    /**
     * 로봇이 보내는 헤더 이름. 로봇(ai_chat) 쪽 구현과 정확히 맞아야 하므로
     * 임의로 바꾸지 않는다 (S15P11E102-307 티켓 명세).
     */
    public static final String HEADER_NAME = "X-Robot-Shared-Secret";

    private final RobotChannelAuthProperties properties;

    public RobotChannelAuthFilter(RobotChannelAuthProperties properties) {
        this.properties = properties;
    }

    /**
     * 시크릿이 비어 있으면(게이트 꺼짐) 이 필터 자체를 건너뛴다.
     *
     * <p>경로는 이미 {@link RobotChannelAuthFilterConfig} 의 url pattern 등록이
     * 걸러 주므로, 여기서는 켜져 있는지만 본다.</p>
     */
    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !properties.isUsable();
    }

    /**
     * 헤더를 시크릿과 비교하고, 틀리면 401 을 본문과 함께 돌려준다.
     *
     * <p>완료 조건이 "상태 코드만이 아니라 응답 본문으로 확인"이라고 명시하므로
     * 빈 401 이 아니라 최소한의 JSON 본문을 써 준다.</p>
     */
    @Override
    protected void doFilterInternal(
        HttpServletRequest request, HttpServletResponse response, FilterChain filterChain
    ) throws ServletException, IOException {
        String provided = request.getHeader(HEADER_NAME);

        if (provided == null || !secretMatches(provided)) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.getWriter().write(
                "{\"error\":\"UNAUTHORIZED\",\"message\":\"missing or invalid "
                    + HEADER_NAME + " header\"}");
            return;
        }

        filterChain.doFilter(request, response);
    }

    /**
     * 타이밍 공격을 피하려고 바이트 단위 상수 시간 비교를 쓴다.
     *
     * <p>{@code String.equals} 는 첫 불일치 문자에서 바로 반환하므로, 응답 시간
     * 차이로 시크릿을 한 글자씩 추측당할 수 있다 — 굳이 여기서 그 위험을 남겨 둘
     * 이유가 없다.</p>
     */
    private boolean secretMatches(String provided) {
        byte[] expected = properties.getSharedSecret().getBytes(StandardCharsets.UTF_8);
        byte[] actual = provided.getBytes(StandardCharsets.UTF_8);
        return MessageDigest.isEqual(expected, actual);
    }
}
