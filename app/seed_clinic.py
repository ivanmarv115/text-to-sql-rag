"""Seed knowledge for the synthetic clinic database.

This is the RAG corpus: hand-annotated DDL, short business/documentation notes,
and example question->SQL pairs. It mirrors the tables created by
``flyway/clinic`` and exists so retrieval works out of the box on first run.

Everything here is entirely synthetic — there is no real schema, no real data
and no real organisation behind it.

DDL blocks are annotated with two conventions the engine understands:
* column comments (``-- ...``) for business context, and
* ``-- Joins: <tables>`` lines that declare foreign-key relationships so the
  retriever can pull in related tables (priority P3).
"""

from __future__ import annotations

# --- DDL --------------------------------------------------------------------

DDL: list[tuple[str, str]] = [
    (
        "departments",
        """\
CREATE TABLE departments (
    department_id SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,   -- clinical service, e.g. 'Cardiology', 'Pediatrics'
    building      TEXT             -- physical building/wing
);
-- A clinical service/unit. Doctors belong to a department; visits happen in one.
-- Joins: doctors, visits
""",
    ),
    (
        "doctors",
        """\
CREATE TABLE doctors (
    doctor_id     SERIAL PRIMARY KEY,
    full_name     TEXT NOT NULL,
    specialty     TEXT,                  -- free-text specialty
    department_id INTEGER REFERENCES departments(department_id)
);
-- Treating clinicians.
-- Joins: departments, visits
""",
    ),
    (
        "patients",
        """\
CREATE TABLE patients (
    patient_id    SERIAL PRIMARY KEY,
    full_name     TEXT NOT NULL,
    birth_date    DATE,
    sex           TEXT,                  -- 'F' | 'M' | 'X'
    city          TEXT,                  -- city of residence
    registered_at TIMESTAMP NOT NULL DEFAULT now()
);
-- People receiving care. One patient has many visits.
-- Joins: visits
""",
    ),
    (
        "visits",
        """\
CREATE TABLE visits (
    visit_id      SERIAL PRIMARY KEY,
    patient_id    INTEGER NOT NULL REFERENCES patients(patient_id),
    doctor_id     INTEGER REFERENCES doctors(doctor_id),
    department_id INTEGER REFERENCES departments(department_id),
    visit_date    DATE NOT NULL,         -- date of the encounter
    reason        TEXT,                  -- chief complaint / reason for visit
    status        TEXT                   -- 'completed' | 'cancelled' | 'no_show'
);
-- One encounter between a patient and a doctor. The central fact table.
-- Joins: patients, doctors, departments, diagnoses
""",
    ),
    (
        "diagnoses",
        """\
CREATE TABLE diagnoses (
    diagnosis_id  SERIAL PRIMARY KEY,
    visit_id      INTEGER NOT NULL REFERENCES visits(visit_id),
    code          TEXT,                  -- ICD-10-style code, e.g. 'J06.9'
    description   TEXT                   -- human-readable diagnosis
);
-- Diagnoses recorded during a visit. A visit may have several.
-- Joins: visits
""",
    ),
]


# --- documentation / business notes ----------------------------------------

DOCS: list[tuple[str, str]] = [
    ("visit-definition", "A 'visit' is a single encounter between a patient and a doctor on a given date. The visits table is the central fact table; counts of activity are usually counts of visits."),
    ("this-month", "Questions about 'this month' filter visits with date_trunc('month', visit_date) = date_trunc('month', CURRENT_DATE)."),
    ("diagnosis-codes", "Diagnoses use ICD-10-style codes in diagnoses.code with a human description in diagnoses.description. 'Most common diagnoses' means grouping by code/description and counting."),
    ("department-meaning", "A department is a clinical service such as Cardiology or Pediatrics. Activity 'per department' joins visits to departments on department_id."),
    ("patient-demographics", "Patient demographics live on the patients table: city, sex and birth_date. Patient age = age(birth_date)."),
    ("status-values", "visits.status is one of 'completed', 'cancelled' or 'no_show'. Unless asked otherwise, analyses usually consider completed visits."),
]


# --- example question -> SQL pairs (multilingual) --------------------------

EXAMPLES: list[tuple[str, str]] = [
    (
        "How many patients are there?",
        "SELECT COUNT(*) AS total_patients FROM patients",
    ),
    (
        "¿Cuántos pacientes hay?",
        "SELECT COUNT(*) AS total_patients FROM patients",
    ),
    (
        "How many visits happened this month?",
        "SELECT COUNT(*) AS visits_this_month FROM visits "
        "WHERE date_trunc('month', visit_date) = date_trunc('month', CURRENT_DATE)",
    ),
    (
        "What are the most common diagnoses?",
        "SELECT code, description, COUNT(*) AS occurrences FROM diagnoses "
        "GROUP BY code, description ORDER BY occurrences DESC LIMIT 5",
    ),
    (
        "How many visits per department?",
        "SELECT dep.name AS department, COUNT(*) AS visits FROM visits v "
        "JOIN departments dep ON dep.department_id = v.department_id "
        "GROUP BY dep.name ORDER BY visits DESC",
    ),
    (
        "How many patients per city?",
        "SELECT city, COUNT(*) AS patients FROM patients "
        "GROUP BY city ORDER BY patients DESC",
    ),
    (
        "List doctors and their department",
        "SELECT d.full_name, d.specialty, dep.name AS department FROM doctors d "
        "JOIN departments dep ON dep.department_id = d.department_id "
        "ORDER BY d.full_name",
    ),
]
