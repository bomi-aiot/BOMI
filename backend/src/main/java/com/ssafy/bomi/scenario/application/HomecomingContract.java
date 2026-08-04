package com.ssafy.bomi.scenario.application;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.UUID;

/**
 * Single source of truth for the homecoming MQTT <b>payload</b> field names and
 * enumerated values.
 *
 * <p>The envelope (eventId/type/occurredAt/sourceId/payload) is fixed by the team
 * topic convention. Only the field names <i>inside</i> {@code payload} are our
 * assumption until the robot team finalizes the contract — change them here (one
 * place) and the whole flow follows.</p>
 */
public final class HomecomingContract {

    // --- Outbound command payload keys/values ---
    /** NAVIGATE payload: destination key. */
    public static final String NAV_TARGET_KEY = "target";
    /** NAVIGATE target value: the entrance. */
    public static final String TARGET_ENTRANCE = "ENTRANCE";
    /** NAVIGATE target value: the robot's default/home position. */
    public static final String TARGET_DEFAULT = "DEFAULT";
    /** NAVIGATE target value: 어르신 평소 위치(거실). WELLNESS_CHECK 등에서 사용. */
    public static final String TARGET_LIVING_ROOM = "LIVING_ROOM";
    /** SPEAK payload: utterance text key. */
    public static final String SPEAK_TEXT_KEY = "text";

    // --- Inbound result payload keys ---
    /** Envelope key holding the nested payload object. */
    public static final String PAYLOAD_KEY = "payload";
    /** Result payload key echoing the scenario id we sent on the command. */
    public static final String RESULT_SCENARIO_ID_KEY = "scenarioId";
    /** Result payload key holding the robot's outcome for the command. */
    public static final String RESULT_STATUS_KEY = "status";
    /** Result status value: the robot reached its target. */
    public static final String RESULT_STATUS_ARRIVED = "ARRIVED";
    /** Result status value: the robot failed to reach its target. */
    public static final String RESULT_STATUS_FAILED = "FAILED";

    private HomecomingContract() {
    }

    /**
     * Extracts the result status from an inbound result body
     * ({@code body.payload.status}), or {@code null} when it is absent or blank.
     *
     * <p>Unlike {@link #readScenarioId}, a missing status is not an error: the
     * caller decides how to treat an unknown status (the navigation handler
     * neither advances nor fails the scenario on it).</p>
     */
    public static String readResultStatus(JsonNode body) {
        JsonNode payload = body == null ? null : body.get(PAYLOAD_KEY);
        JsonNode statusNode = payload == null ? null : payload.get(RESULT_STATUS_KEY);
        if (statusNode == null || !statusNode.isTextual() || statusNode.textValue().isBlank()) {
            return null;
        }
        return statusNode.textValue();
    }

    /**
     * Extracts the echoed scenario id from an inbound result body
     * ({@code body.payload.scenarioId}).
     *
     * @throws IllegalArgumentException if the id is missing or not a UUID
     */
    public static UUID readScenarioId(JsonNode body) {
        JsonNode payload = body == null ? null : body.get(PAYLOAD_KEY);
        JsonNode idNode = payload == null ? null : payload.get(RESULT_SCENARIO_ID_KEY);
        if (idNode == null || !idNode.isTextual() || idNode.textValue().isBlank()) {
            throw new IllegalArgumentException(
                "Result payload is missing a textual '" + RESULT_SCENARIO_ID_KEY + "'");
        }
        try {
            return UUID.fromString(idNode.textValue());
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                "Result payload '" + RESULT_SCENARIO_ID_KEY + "' is not a valid UUID", ex);
        }
    }
}
