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
    /** SPEAK payload: utterance text key. */
    public static final String SPEAK_TEXT_KEY = "text";

    // --- Inbound result payload keys ---
    /** Envelope key holding the nested payload object. */
    public static final String PAYLOAD_KEY = "payload";
    /** Result payload key echoing the scenario id we sent on the command. */
    public static final String RESULT_SCENARIO_ID_KEY = "scenarioId";

    private HomecomingContract() {
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
