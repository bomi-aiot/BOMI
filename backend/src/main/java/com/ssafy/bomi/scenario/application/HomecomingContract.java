package com.ssafy.bomi.scenario.application;

/** Homecoming command constants from the finalized MQTT v1 contract. */
public final class HomecomingContract {

    /** NAVIGATE payload: destination key. */
    public static final String NAV_TARGET_KEY = "target";
    /** NAVIGATE target value: the entrance. */
    public static final String TARGET_ENTRANCE = "ENTRANCE";
    /** NAVIGATE target value: the robot's default/home position. */
    public static final String TARGET_DEFAULT = "DEFAULT";
    /** NAVIGATE target value: the senior's usual living-room position. */
    public static final String TARGET_LIVING_ROOM = "LIVING_ROOM";
    /** SPEAK payload: utterance text key. */
    public static final String SPEAK_TEXT_KEY = "text";

    private HomecomingContract() {
    }
}
