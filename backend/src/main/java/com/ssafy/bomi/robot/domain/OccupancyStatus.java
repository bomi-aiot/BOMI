package com.ssafy.bomi.robot.domain;

/**
 * Whether the senior is currently at home, derived from the entrance sensor.
 *
 * <p>The single most valuable safety input: it decides what a silence
 * <em>means</em>. {@code HOME} plus no response is suspicious; {@code AWAY} plus
 * no response is normal.</p>
 *
 * <p>{@code UNKNOWN} is not a placeholder — it is a real state that must be
 * acted on conservatively. It occurs on boot, on sensor contradiction, and when
 * the entrance node's heartbeat stops. Treating it as "probably fine" would let
 * a dead sensor silently switch off safety monitoring.</p>
 *
 * <p>Speech beats the sensor: any detected utterance promotes
 * {@code UNKNOWN}/{@code AWAY} to {@code HOME} (CLAUDE.md §11).</p>
 */
public enum OccupancyStatus {
    HOME,
    AWAY,
    UNKNOWN
}
