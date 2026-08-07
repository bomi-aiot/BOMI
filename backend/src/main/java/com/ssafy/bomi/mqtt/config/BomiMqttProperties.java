package com.ssafy.bomi.mqtt.config;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * BOMI MQTT client settings.
 *
 * <p>The integration is disabled by default so the skeleton cannot consume and
 * acknowledge production messages before business handlers are connected.</p>
 */
@Validated
@ConfigurationProperties(prefix = "bomi.mqtt")
public class BomiMqttProperties {

    private boolean enabled;

    @NotBlank
    @Pattern(regexp = "^(tcp|ssl|ws|wss)://.+")
    private String brokerUrl = "tcp://localhost:1883";

    @NotBlank
    @Size(max = 48)
    private String clientIdPrefix = "bomi-backend";

    private String username = "";

    private String password = "";

    @Min(1)
    @Max(1)
    private int qos = 1;

    @NotNull
    private Duration connectionTimeout = Duration.ofSeconds(10);

    @NotNull
    private Duration completionTimeout = Duration.ofSeconds(5);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getBrokerUrl() {
        return brokerUrl;
    }

    public void setBrokerUrl(String brokerUrl) {
        this.brokerUrl = brokerUrl;
    }

    public String getClientIdPrefix() {
        return clientIdPrefix;
    }

    public void setClientIdPrefix(String clientIdPrefix) {
        this.clientIdPrefix = clientIdPrefix;
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public int getQos() {
        return qos;
    }

    public void setQos(int qos) {
        this.qos = qos;
    }

    public Duration getConnectionTimeout() {
        return connectionTimeout;
    }

    public void setConnectionTimeout(Duration connectionTimeout) {
        this.connectionTimeout = connectionTimeout;
    }

    public Duration getCompletionTimeout() {
        return completionTimeout;
    }

    public void setCompletionTimeout(Duration completionTimeout) {
        this.completionTimeout = completionTimeout;
    }

    @AssertTrue(message = "connectionTimeout and completionTimeout must be at least 1 second")
    public boolean isTimeoutsValid() {
        return isPositive(connectionTimeout) && isPositive(completionTimeout);
    }

    private static boolean isPositive(Duration duration) {
        return duration != null && duration.compareTo(Duration.ofSeconds(1)) >= 0;
    }

}
