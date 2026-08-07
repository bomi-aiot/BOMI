package com.ssafy.bomi.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/** Server-owned credentials for the operator-only mutation channel. */
@Component
@ConfigurationProperties(prefix = "bomi.operator-channel")
public class OperatorChannelAuthProperties {

    /** Empty configuration keeps the operator endpoint fail-closed. */
    private String sharedSecret = "";

    /** Stable audit identity assigned by the server, never accepted from the request. */
    private String operatorId = "";

    public String getSharedSecret() {
        return sharedSecret;
    }

    public void setSharedSecret(String sharedSecret) {
        this.sharedSecret = normalize(sharedSecret);
    }

    public String getOperatorId() {
        return operatorId;
    }

    public void setOperatorId(String operatorId) {
        this.operatorId = normalize(operatorId);
    }

    /** Both values are mandatory because the endpoint mutates a safety-critical mode. */
    public boolean isUsable() {
        return !sharedSecret.isBlank() && !operatorId.isBlank() && operatorId.length() <= 100;
    }

    private static String normalize(String value) {
        return value == null ? "" : value.trim();
    }
}
