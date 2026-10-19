CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at REAL NOT NULL, sending_blocked INTEGER NOT NULL DEFAULT 0 CHECK(sending_blocked IN (0,1)));
CREATE TABLE runs(
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE, params_hash TEXT NOT NULL, batch_id TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('running','paused','interrupted','blocked','completed','limit_reached')),
 pause_requested INTEGER NOT NULL DEFAULT 0 CHECK(pause_requested IN(0,1)),
 max_messages INTEGER NOT NULL CHECK(max_messages>0), max_attempts INTEGER NOT NULL CHECK(max_attempts>0), max_active_seconds REAL NOT NULL CHECK(max_active_seconds>0),
 messages_started INTEGER NOT NULL DEFAULT 0, attempts_started INTEGER NOT NULL DEFAULT 0, active_seconds REAL NOT NULL DEFAULT 0,
 heartbeat_at REAL, created_at REAL NOT NULL, updated_at REAL NOT NULL, finished_at REAL, blocked_reason TEXT);
CREATE TABLE messages(
 id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, external_id TEXT NOT NULL, account_id TEXT NOT NULL,
 input_hash TEXT NOT NULL, content_hash TEXT NOT NULL,
 sender TEXT NOT NULL, recipient TEXT NOT NULL, subject TEXT NOT NULL, html TEXT NOT NULL, text TEXT NOT NULL,
 mime_bytes BLOB NOT NULL, message_id TEXT NOT NULL UNIQUE,
 kind TEXT NOT NULL DEFAULT 'normal' CHECK(kind IN('normal','test')), source_message_id TEXT REFERENCES messages(id),
 request_id TEXT UNIQUE, params_hash TEXT,
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN('pending','sending','retry_wait','sent','failed','uncertain','cancelled')),
 run_id TEXT REFERENCES runs(id), attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count BETWEEN 0 AND 5),
 next_attempt_at REAL, last_error_code TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL, sent_at REAL,
 confirmation_source TEXT CHECK(confirmation_source IN('smtp','manual')), resolution_action TEXT, resolution_reason TEXT, resolved_at REAL,
 UNIQUE(batch_id,external_id,account_id));
CREATE TABLE attempts(
 id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages(id), run_id TEXT NOT NULL REFERENCES runs(id), started_at REAL NOT NULL, finished_at REAL,
 phase TEXT NOT NULL CHECK(phase IN('reserved','connected','authenticated','envelope_ready','submission_started','accepted')),
 outcome TEXT CHECK(outcome IN('success','transient','permanent','uncertain')), smtp_code INTEGER, response TEXT, error_code TEXT, submission_reserved_at REAL);
CREATE INDEX messages_eligible ON messages(state,next_attempt_at);
CREATE INDEX messages_batch ON messages(batch_id,id);
CREATE INDEX attempts_submission ON attempts(submission_reserved_at);
CREATE INDEX attempts_run ON attempts(run_id,message_id);
