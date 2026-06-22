-- Obviously-fake demo data. Names, cities and codes are deliberately synthetic
-- ("Test Patient One", "Mockville", "Dr. Demo House"). Visit dates are computed
-- relative to CURRENT_DATE so "this month" style questions always return rows.

INSERT INTO departments (name, building) VALUES
    ('Cardiology',  'Main Building'),   -- 1
    ('Pediatrics',  'West Wing'),       -- 2
    ('Emergency',   'Main Building'),   -- 3
    ('Dermatology', 'Annex');           -- 4

INSERT INTO doctors (full_name, specialty, department_id) VALUES
    ('Dr. Demo House',     'Cardiology',        1),  -- 1
    ('Dr. Sample Grey',    'Pediatrics',        2),  -- 2
    ('Dr. Fake Strange',   'Emergency Medicine',3),  -- 3
    ('Dr. Test Wilson',    'Cardiology',        1),  -- 4
    ('Dr. Mock Bailey',    'Dermatology',       4),  -- 5
    ('Dr. Example Cuddy',  'Pediatrics',        2);  -- 6

INSERT INTO patients (full_name, birth_date, sex, city) VALUES
    ('Test Patient One',  '1980-01-15', 'F', 'Springfield'),   -- 1
    ('Demo Doe',          '1975-06-30', 'M', 'Faketown'),      -- 2
    ('Sample Smith',      '1990-11-02', 'F', 'Mockville'),     -- 3
    ('Mock Johnson',      '2010-03-21', 'M', 'Springfield'),   -- 4
    ('Example Brown',     '1965-09-09', 'F', 'Sample City'),   -- 5
    ('Faux Garcia',       '1988-12-12', 'M', 'Testburg'),      -- 6
    ('Placeholder Lee',   '2015-07-07', 'X', 'Faketown'),      -- 7
    ('Dummy Martinez',    '1952-02-28', 'F', 'Springfield'),   -- 8
    ('Synthetic Davis',   '1999-04-18', 'M', 'Mockville'),     -- 9
    ('Fictional Wong',    '1983-08-23', 'F', 'Sample City'),   -- 10
    ('Notreal Patel',     '1971-10-05', 'M', 'Testburg'),      -- 11
    ('Imaginary Rossi',   '2005-05-14', 'F', 'Springfield');   -- 12

-- Visits: ids 1..22. Roughly half land in the current month.
INSERT INTO visits (patient_id, doctor_id, department_id, visit_date, reason, status) VALUES
    -- current month
    ( 1, 1, 1, (date_trunc('month', CURRENT_DATE) + INTERVAL '1 day')::date,  'Chest pain',              'completed'),
    ( 2, 4, 1, (date_trunc('month', CURRENT_DATE) + INTERVAL '2 days')::date, 'Hypertension follow-up',  'completed'),
    ( 4, 2, 2, (date_trunc('month', CURRENT_DATE) + INTERVAL '3 days')::date, 'Fever',                   'completed'),
    ( 7, 6, 2, (date_trunc('month', CURRENT_DATE) + INTERVAL '3 days')::date, 'Routine checkup',         'completed'),
    ( 5, 3, 3, (date_trunc('month', CURRENT_DATE) + INTERVAL '4 days')::date, 'Abdominal pain',          'completed'),
    ( 9, 5, 4, (date_trunc('month', CURRENT_DATE) + INTERVAL '5 days')::date, 'Rash',                    'completed'),
    ( 3, 1, 1, (date_trunc('month', CURRENT_DATE) + INTERVAL '6 days')::date, 'Palpitations',            'completed'),
    (11, 3, 3, (date_trunc('month', CURRENT_DATE) + INTERVAL '6 days')::date, 'Headache',                'completed'),
    (12, 2, 2, (date_trunc('month', CURRENT_DATE) + INTERVAL '7 days')::date, 'Asthma review',           'completed'),
    ( 8, 4, 1, (date_trunc('month', CURRENT_DATE) + INTERVAL '8 days')::date, 'Hypertension follow-up',  'no_show'),
    -- previous months
    ( 1, 1, 1, (CURRENT_DATE - INTERVAL '40 days')::date,  'Chest pain',             'completed'),
    ( 2, 4, 1, (CURRENT_DATE - INTERVAL '52 days')::date,  'Hypertension follow-up', 'completed'),
    ( 3, 5, 4, (CURRENT_DATE - INTERVAL '60 days')::date,  'Eczema',                 'completed'),
    ( 6, 3, 3, (CURRENT_DATE - INTERVAL '63 days')::date,  'Back pain',              'completed'),
    ( 6, 1, 1, (CURRENT_DATE - INTERVAL '75 days')::date,  'Chest pain',             'cancelled'),
    ( 9, 2, 2, (CURRENT_DATE - INTERVAL '80 days')::date,  'Cough',                  'completed'),
    (10, 6, 2, (CURRENT_DATE - INTERVAL '88 days')::date,  'Routine checkup',        'completed'),
    ( 5, 4, 1, (CURRENT_DATE - INTERVAL '95 days')::date,  'Palpitations',           'completed'),
    ( 8, 3, 3, (CURRENT_DATE - INTERVAL '100 days')::date, 'Headache',               'completed'),
    (11, 5, 4, (CURRENT_DATE - INTERVAL '110 days')::date, 'Rash',                   'completed'),
    ( 4, 2, 2, (CURRENT_DATE - INTERVAL '120 days')::date, 'Fever',                  'completed'),
    (12, 1, 1, (CURRENT_DATE - INTERVAL '130 days')::date, 'Back pain',              'completed');

-- Diagnoses: ids reference visits 1..22; codes intentionally repeat so that
-- "most common diagnoses" is meaningful.
INSERT INTO diagnoses (visit_id, code, description) VALUES
    ( 1, 'I10',     'Essential hypertension'),
    ( 2, 'I10',     'Essential hypertension'),
    ( 3, 'J06.9',   'Acute upper respiratory infection'),
    ( 4, 'J06.9',   'Acute upper respiratory infection'),
    ( 5, 'K21.9',   'Gastro-esophageal reflux disease'),
    ( 6, 'L20.9',   'Atopic dermatitis'),
    ( 7, 'J06.9',   'Acute upper respiratory infection'),
    ( 8, 'R51',     'Headache'),
    ( 9, 'J45.909', 'Asthma, unspecified'),
    (10, 'I10',     'Essential hypertension'),
    (11, 'I10',     'Essential hypertension'),
    (12, 'E11.9',   'Type 2 diabetes mellitus'),
    (13, 'L20.9',   'Atopic dermatitis'),
    (14, 'M54.5',   'Low back pain'),
    (15, 'E11.9',   'Type 2 diabetes mellitus'),
    (16, 'J06.9',   'Acute upper respiratory infection'),
    (17, 'E11.9',   'Type 2 diabetes mellitus'),
    (18, 'R51',     'Headache'),
    (19, 'R51',     'Headache'),
    (20, 'M54.5',   'Low back pain'),
    (21, 'J45.909', 'Asthma, unspecified'),
    (22, 'M54.5',   'Low back pain');
