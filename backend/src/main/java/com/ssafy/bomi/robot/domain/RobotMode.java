package com.ssafy.bomi.robot.domain;

/**
 * Operating mode of a {@link Robot}.
 *
 * <p>Only {@code IDLE} is confirmed by the SQL default; additional values are
 * provisional and must be reconciled with the finalized ERD.</p>
 */
public enum RobotMode {
    IDLE,
    ACTIVE
}
