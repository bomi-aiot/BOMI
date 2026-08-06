package com.ssafy.bomi.mqtt.topic;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class MqttTopics {

    public static final String IOT_EVENTS_SUBSCRIPTION = "bomi/v1/iot/+/events";
    public static final String ROBOT_EVENTS_SUBSCRIPTION = "bomi/v1/robot/+/events";
    public static final String ROBOT_STATUS_SUBSCRIPTION = "bomi/v1/robot/+/status";
    public static final String ROBOT_RESULTS_SUBSCRIPTION = "bomi/v1/robot/+/results";

    private static final Pattern SAFE_TOPIC_ID = Pattern.compile("[A-Za-z0-9._-]{1,64}");
    private static final Pattern IOT_EVENTS = Pattern.compile("bomi/v1/iot/([^/]+)/events");
    private static final Pattern ROBOT_EVENTS = Pattern.compile("bomi/v1/robot/([^/]+)/events");
    private static final Pattern ROBOT_STATUS = Pattern.compile("bomi/v1/robot/([^/]+)/status");
    private static final Pattern ROBOT_RESULTS = Pattern.compile("bomi/v1/robot/([^/]+)/results");

    private MqttTopics() {
    }

    public static String[] inboundSubscriptions() {
        return new String[] {
            IOT_EVENTS_SUBSCRIPTION,
            ROBOT_EVENTS_SUBSCRIPTION,
            ROBOT_STATUS_SUBSCRIPTION,
            ROBOT_RESULTS_SUBSCRIPTION
        };
    }

    public static String robotCommands(String robotId) {
        requireSafeTopicId(robotId, "robotId");
        return "bomi/v1/robot/" + robotId + "/commands";
    }

    public static String aiCommands(String robotId) {
        requireSafeTopicId(robotId, "robotId");
        return "bomi/v1/ai/" + robotId + "/commands";
    }

    public static MqttTopicMatch matchInbound(String topic) {
        if (topic == null || topic.isBlank()) {
            throw new IllegalArgumentException("MQTT received topic must not be blank");
        }

        MqttTopicMatch match = match(topic, IOT_EVENTS, MqttInboundCategory.IOT_EVENT);
        if (match != null) {
            return match;
        }
        match = match(topic, ROBOT_EVENTS, MqttInboundCategory.ROBOT_EVENT);
        if (match != null) {
            return match;
        }
        match = match(topic, ROBOT_STATUS, MqttInboundCategory.ROBOT_STATUS);
        if (match != null) {
            return match;
        }
        match = match(topic, ROBOT_RESULTS, MqttInboundCategory.ROBOT_RESULT);
        if (match != null) {
            return match;
        }

        throw new IllegalArgumentException("Unsupported BOMI MQTT inbound topic: " + topic);
    }

    private static MqttTopicMatch match(
        String topic,
        Pattern pattern,
        MqttInboundCategory category
    ) {
        Matcher matcher = pattern.matcher(topic);
        if (!matcher.matches()) {
            return null;
        }
        String sourceId = matcher.group(1);
        requireSafeTopicId(sourceId, "topic sourceId");
        return new MqttTopicMatch(category, sourceId);
    }

    private static void requireSafeTopicId(String value, String field) {
        if (value == null || !SAFE_TOPIC_ID.matcher(value).matches()) {
            throw new IllegalArgumentException(
                field + " must be 1-64 topic-safe characters: letters, digits, '.', '_' or '-'"
            );
        }
    }
}
