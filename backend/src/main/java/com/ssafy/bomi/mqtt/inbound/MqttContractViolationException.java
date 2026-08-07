package com.ssafy.bomi.mqtt.inbound;

public class MqttContractViolationException extends RuntimeException {

    public MqttContractViolationException(String message) {
        super(message);
    }

    public MqttContractViolationException(String message, Throwable cause) {
        super(message, cause);
    }
}
