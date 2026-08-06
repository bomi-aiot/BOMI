package com.ssafy.bomi.docs;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Makes the documentation pages reachable by their directory URLs.
 *
 * <p>Spring Boot serves {@code static/index.html} for {@code /}, but it does not do the
 * same for nested directories — {@code /docs/} would 404 while {@code /docs/index.html}
 * works. The published entry points are directory URLs, and a link that only works with
 * the filename spelled out is a link people will get wrong.</p>
 */
@Configuration
public class DocsWebConfig implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        forwardIndex(registry, "/docs");
        forwardIndex(registry, "/asyncapi/mqtt");
        forwardIndex(registry, "/asyncapi/websocket");
    }

    /**
     * Serves {@code {base}/index.html} for both {@code {base}} and {@code {base}/}.
     *
     * <p>The no-slash form forwards rather than redirects so a copied link works on the
     * first request instead of costing a round trip.</p>
     */
    private void forwardIndex(ViewControllerRegistry registry, String base) {
        String target = "forward:" + base + "/index.html";
        registry.addViewController(base).setViewName(target);
        registry.addViewController(base + "/").setViewName(target);
    }
}
