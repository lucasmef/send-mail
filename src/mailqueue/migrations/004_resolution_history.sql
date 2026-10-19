ALTER TABLE messages ADD COLUMN resolution_history_json TEXT NOT NULL DEFAULT '[]';
UPDATE messages SET resolution_history_json=json_array(json_object('action',resolution_action,'reason',resolution_reason,'at',resolved_at)) WHERE resolution_action IS NOT NULL;
