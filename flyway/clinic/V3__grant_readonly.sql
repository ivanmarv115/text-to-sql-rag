-- Database-level read-only safety net. The application connects to this
-- database as the `llm_readonly` role (created in db/init/00-init.sh). Even if
-- the SQL validator were bypassed, this role can only SELECT.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'llm_readonly') THEN
        EXECUTE 'GRANT USAGE ON SCHEMA public TO llm_readonly';
        EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA public TO llm_readonly';
        EXECUTE 'GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO llm_readonly';
        -- future tables created by the owner are SELECT-able too
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO llm_readonly';
    END IF;
END
$$;

-- No one but the owner may create objects in public.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
