package com.ssafy.bomi.robot.domain;

/**
 * Operating mode of a {@link Robot}.
 *
 * <p>Values follow the {@code ROBOT_ENUM} code dictionary of the MVP ERD
 * ({@code current_mode}); {@code IDLE} is the SQL default.</p>
 */
public enum RobotMode {
    IDLE,
    SCENARIO_ACTIVE,
    REST_GUARD,
    SAFE_STOP
}
