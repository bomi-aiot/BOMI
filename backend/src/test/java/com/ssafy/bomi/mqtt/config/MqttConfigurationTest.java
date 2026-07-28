package com.ssafy.bomi.mqtt.config;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.mqtt.topic.MqttTopics;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;

class MqttConfigurationTest {

    private final MqttConfiguration configuration = new MqttConfiguration();

    @Test
    void createsPersistentAutomaticallyReconnectingConnectionOptions() {
        BomiMqttProperties properties = new BomiMqttProperties();
        properties.setBrokerUrl("tcp://broker:1883");
        properties.setUsername("backend");
        properties.setPassword("secret");

        MqttConnectOptions options = configuration.mqttConnectOptions(properties);

        assertThat(options.getServerURIs()).containsExactly("tcp://broker:1883");
        assertThat(options.isAutomaticReconnect()).isTrue();
        assertThat(options.isCleanSession()).isFalse();
        assertThat(options.getConnectionTimeout()).isEqualTo(10);
        assertThat(options.getUserName()).isEqualTo("backend");
        assertThat(options.getPassword()).containsExactly(
            's', 'e', 'c', 'r', 'e', 't'
        );
    }

    @Test
    void inboundAdapterUsesFourContractTopicsAtQosOne() {
        BomiMqttProperties properties = new BomiMqttProperties();
        MqttConnectOptions options = configuration.mqttConnectOptions(properties);
        MqttPahoClientFactory clientFactory = configuration.mqttClientFactory(options);

        MqttPahoMessageDrivenChannelAdapter adapter =
            configuration.mqttInboundAdapter(
                properties,
                clientFactory,
                new DirectChannel()
            );

        assertThat(adapter.getTopic()).containsExactly(MqttTopics.inboundSubscriptions());
        assertThat(adapter.getQos()).containsExactly(1, 1, 1, 1);
    }
}
