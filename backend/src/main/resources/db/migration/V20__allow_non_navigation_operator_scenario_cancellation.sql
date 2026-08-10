ALTER TABLE operator_scenario_cancellation_audit
    ALTER COLUMN target_navigation_command_id DROP NOT NULL,
    ALTER COLUMN cancel_command_id DROP NOT NULL;

COMMENT ON TABLE operator_scenario_cancellation_audit IS
    'Authenticated operator force-cancellation of an active scenario.';
