package com.ssafy.bomi.mqtt.topic;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class MqttTopicsTest {

    @Test
    void exposesFourContractSubscriptions() {
        assertThat(MqttTopics.inboundSubscriptions()).containsExactly(
            "bomi/v1/iot/+/events",
            "bomi/v1/robot/+/events",
            "bomi/v1/robot/+/status",
            "bomi/v1/robot/+/results"
        );
    }

    @Test
    void createsRobotCommandTopicFromSafeId() {
        assertThat(MqttTopics.robotCommands("robot-01"))
            .isEqualTo("bomi/v1/robot/robot-01/commands");
    }

    @Test
    void rejectsTopicInjectionInRobotId() {
        assertThatThrownBy(() -> MqttTopics.robotCommands("robot-01/#"))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("topic-safe");
    }

    @Test
    void classifiesInboundTopicsAndExtractsSourceId() {
        assertThat(MqttTopics.matchInbound("bomi/v1/iot/entrance-hub/events"))
            .isEqualTo(new MqttTopicMatch(MqttInboundCategory.IOT_EVENT, "entrance-hub"));
        assertThat(MqttTopics.matchInbound("bomi/v1/robot/robot-01/events"))
            .isEqualTo(new MqttTopicMatch(MqttInboundCategory.ROBOT_EVENT, "robot-01"));
        assertThat(MqttTopics.matchInbound("bomi/v1/robot/robot-01/status"))
            .isEqualTo(new MqttTopicMatch(MqttInboundCategory.ROBOT_STATUS, "robot-01"));
        assertThat(MqttTopics.matchInbound("bomi/v1/robot/robot-01/results"))
            .isEqualTo(new MqttTopicMatch(MqttInboundCategory.ROBOT_RESULT, "robot-01"));
    }
}
