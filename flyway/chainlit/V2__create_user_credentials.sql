-- Password-auth credentials. Passwords are bcrypt-hashed by the application
-- (see app/chainlit_db.py and scripts/create_user.py); only the hash is stored.

CREATE TABLE IF NOT EXISTS user_credentials (
    identifier      TEXT PRIMARY KEY,
    hashed_password TEXT NOT NULL,
    display_name    TEXT,
    role            TEXT NOT NULL DEFAULT 'user',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
