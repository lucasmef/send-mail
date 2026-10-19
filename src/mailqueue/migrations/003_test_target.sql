ALTER TABLE runs ADD COLUMN test_message_id TEXT REFERENCES messages(id);
