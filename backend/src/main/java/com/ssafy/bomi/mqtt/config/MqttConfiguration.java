package com.ssafy.bomi.mqtt.config;

import com.ssafy.bomi.mqtt.topic.MqttTopics;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.util.StringUtils;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(BomiMqttProperties.class)
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class MqttConfiguration {

    @Bean
    MqttConnectOptions mqttConnectOptions(BomiMqttProperties properties) {
        MqttConnectOptions options = new MqttConnectOptions();
        options.setServerURIs(new String[] {properties.getBrokerUrl()});
        options.setAutomaticReconnect(true);
        options.setCleanSession(false);
        options.setConnectionTimeout(toPositiveSeconds(properties.getConnectionTimeout()));

        if (StringUtils.hasText(properties.getUsername())) {
            options.setUserName(properties.getUsername());
        }
        if (StringUtils.hasText(properties.getPassword())) {
            options.setPassword(properties.getPassword().toCharArray());
        }
        return options;
    }

    @Bean
    MqttPahoClientFactory mqttClientFactory(MqttConnectOptions mqttConnectOptions) {
        DefaultMqttPahoClientFactory factory = new DefaultMqttPahoClientFactory();
        factory.setConnectionOptions(mqttConnectOptions);
        return factory;
    }

    @Bean(name = MqttChannels.INBOUND)
    MessageChannel mqttInboundChannel() {
        return new DirectChannel();
    }

    @Bean
    MqttPahoMessageDrivenChannelAdapter mqttInboundAdapter(
        BomiMqttProperties properties,
        MqttPahoClientFactory mqttClientFactory,
        @Qualifier(MqttChannels.INBOUND) MessageChannel mqttInboundChannel
    ) {
        String[] topics = MqttTopics.inboundSubscriptions();
        MqttPahoMessageDrivenChannelAdapter adapter =
            new MqttPahoMessageDrivenChannelAdapter(
                properties.getClientIdPrefix() + "-inbound",
                mqttClientFactory,
                topics
            );
        adapter.setOutputChannel(mqttInboundChannel);
        adapter.setQos(repeat(properties.getQos(), topics.length));
        adapter.setManualAcks(true);
        adapter.setCompletionTimeout(properties.getCompletionTimeout().toMillis());

        DefaultPahoMessageConverter converter =
            new DefaultPahoMessageConverter(properties.getQos(), false);
        converter.setPayloadAsBytes(false);
        adapter.setConverter(converter);
        return adapter;
    }

    @Bean(name = MqttChannels.OUTBOUND)
    MessageChannel mqttOutboundChannel() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = MqttChannels.OUTBOUND)
    MessageHandler mqttOutboundHandler(
        BomiMqttProperties properties,
        MqttPahoClientFactory mqttClientFactory
    ) {
        MqttPahoMessageHandler handler =
            new MqttPahoMessageHandler(
                properties.getClientIdPrefix() + "-outbound",
                mqttClientFactory
            );
        handler.setAsync(false);
        handler.setDefaultQos(properties.getQos());
        handler.setDefaultRetained(false);
        handler.setCompletionTimeout(properties.getCompletionTimeout().toMillis());
        return handler;
    }

    private static int toPositiveSeconds(java.time.Duration duration) {
        long seconds = duration.toSeconds();
        if (seconds < 1 || seconds > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "bomi.mqtt.connection-timeout must be between 1 second and "
                    + Integer.MAX_VALUE + " seconds"
            );
        }
        return (int) seconds;
    }

    private static int[] repeat(int value, int count) {
        int[] values = new int[count];
        java.util.Arrays.fill(values, value);
        return values;
    }
}
