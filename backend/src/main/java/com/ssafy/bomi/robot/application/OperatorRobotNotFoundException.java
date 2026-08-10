package com.ssafy.bomi.robot.application;

public class OperatorRobotNotFoundException extends RuntimeException {

    public OperatorRobotNotFoundException(String deviceId) {
        super("Robot is not registered: " + deviceId);
    }
}
