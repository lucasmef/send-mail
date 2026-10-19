ALTER TABLE attempts ADD COLUMN delay_seconds REAL NOT NULL DEFAULT 15 CHECK(delay_seconds >= 0);
UPDATE runs SET resume_after=NULL WHERE blocked_reason='ACCOUNT_COOLDOWN'
AND NOT EXISTS (SELECT 1 FROM runs source WHERE source.blocked_reason='SMTP_THROTTLED' AND source.resume_after=runs.resume_after);
UPDATE runs SET resume_after=NULL WHERE blocked_reason='DAILY_BUDGET';
