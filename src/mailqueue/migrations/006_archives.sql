CREATE TABLE archives(
 message_id TEXT PRIMARY KEY REFERENCES messages(id),
 state TEXT NOT NULL CHECK(state IN('pending','appending','archived','failed','uncertain')),
 folder TEXT NOT NULL, wire_bytes BLOB NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0, last_error_code TEXT,
 created_at REAL NOT NULL, updated_at REAL NOT NULL, archived_at REAL,
 uid TEXT, uidvalidity TEXT);
CREATE INDEX archives_state ON archives(state);
