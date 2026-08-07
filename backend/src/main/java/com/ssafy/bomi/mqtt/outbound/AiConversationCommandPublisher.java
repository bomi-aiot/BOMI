package com.ssafy.bomi.mqtt.outbound;

public interface AiConversationCommandPublisher {

    void publish(AiConversationCommand command);
}
