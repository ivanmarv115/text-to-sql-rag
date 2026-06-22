-- Synthetic clinic schema. Entirely fictional — no real schema, organisation or
-- data. This is the read-only database the assistant queries.

CREATE TABLE IF NOT EXISTS departments (
    department_id SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    building      TEXT
);

CREATE TABLE IF NOT EXISTS doctors (
    doctor_id     SERIAL PRIMARY KEY,
    full_name     TEXT NOT NULL,
    specialty     TEXT,
    department_id INTEGER REFERENCES departments(department_id)
);

CREATE TABLE IF NOT EXISTS patients (
    patient_id    SERIAL PRIMARY KEY,
    full_name     TEXT NOT NULL,
    birth_date    DATE,
    sex           TEXT,
    city          TEXT,
    registered_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS visits (
    visit_id      SERIAL PRIMARY KEY,
    patient_id    INTEGER NOT NULL REFERENCES patients(patient_id),
    doctor_id     INTEGER REFERENCES doctors(doctor_id),
    department_id INTEGER REFERENCES departments(department_id),
    visit_date    DATE NOT NULL,
    reason        TEXT,
    status        TEXT DEFAULT 'completed'
);

CREATE TABLE IF NOT EXISTS diagnoses (
    diagnosis_id SERIAL PRIMARY KEY,
    visit_id     INTEGER NOT NULL REFERENCES visits(visit_id),
    code         TEXT,
    description  TEXT
);

CREATE INDEX IF NOT EXISTS ix_visits_date ON visits (visit_date);
CREATE INDEX IF NOT EXISTS ix_visits_patient ON visits (patient_id);
CREATE INDEX IF NOT EXISTS ix_diagnoses_visit ON diagnoses (visit_id);
