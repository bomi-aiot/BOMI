package com.ssafy.bomi.context.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** Bundled public-document corpus configuration. */
@Component
@ConfigurationProperties(prefix = "bomi.document-corpus")
public class DocumentCorpusProperties {

    /** The bundled, no-network corpus is on by default. */
    private boolean enabled = true;

    private String resource = "classpath:rag/welfare-corpus.json";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getResource() {
        return resource;
    }

    public void setResource(String resource) {
        this.resource = resource;
    }
}
