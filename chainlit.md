# Natural-language → SQL assistant 🏥

Ask questions in plain language about a **sample** hospital/clinic database and
get answers backed by real (read-only) SQL.

This is a portfolio demo running on **synthetic data**. By default it runs in
**mock mode** — no GPU and no model server required.

**Try:**
- *How many patients are there?*
- *¿Cuántos pacientes hay?*
- *What are the most common diagnoses?*
- *How many visits per department?*

Every answer is produced by retrieving the relevant schema (RAG), generating a
**read-only** `SELECT`, validating it, running it against the demo database, and
summarising the result.
