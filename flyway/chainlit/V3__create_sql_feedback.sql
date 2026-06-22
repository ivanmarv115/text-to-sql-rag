-- Feedback on generated answers. Confirmed-good pairs can later be curated into
-- the seed data (app/seed_clinic.py) to improve retrieval over time.

CREATE TABLE IF NOT EXISTS sql_feedback (
    id         SERIAL PRIMARY KEY,
    username   TEXT,
    question   TEXT NOT NULL,
    sql        TEXT NOT NULL,
    feedback   TEXT NOT NULL,            -- 'positive' | 'negative'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_sql_feedback_created ON sql_feedback (created_at DESC);
