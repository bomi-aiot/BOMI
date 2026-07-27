package com.ssafy.bomi.mqtt.outbound;

public interface RobotCommandPublisher {

    void publish(RobotCommand command);
}
