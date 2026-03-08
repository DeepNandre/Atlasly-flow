BEGIN;

DROP TRIGGER IF EXISTS audit_events_no_delete_trg ON audit_events;
DROP TRIGGER IF EXISTS audit_events_no_update_trg ON audit_events;
DROP FUNCTION IF EXISTS prevent_audit_event_mutation();

DROP TABLE IF EXISTS event_consumer_dedup;
DROP TABLE IF EXISTS domain_events;
DROP TABLE IF EXISTS audit_events;

COMMIT;

