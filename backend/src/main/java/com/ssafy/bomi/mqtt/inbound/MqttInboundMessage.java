package com.ssafy.bomi.mqtt.inbound;

import com.fasterxml.jackson.databind.JsonNode;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import java.time.OffsetDateTime;

public record MqttInboundMessage(
    MqttInboundCategory category,
    String topic,
    String sourceId,
    String eventId,
    String type,
    OffsetDateTime occurredAt,
    int qos,
    boolean retained,
    JsonNode body
) {
}
