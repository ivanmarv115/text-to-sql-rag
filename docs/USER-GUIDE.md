# User guide

A short guide to using the chat assistant. (For setup and architecture, see the
[top-level README](../README.md).)

## Logging in

Open the app (http://localhost:8000 by default) and sign in. The demo creates a
login automatically: **`demo` / `demo`**.

## Asking questions

Type a question in plain language — English or Spanish. The assistant figures
out whether you're asking about the data or just chatting, and for data
questions it retrieves the relevant schema, writes a **read-only** SQL query,
runs it, and summarises the answer.

Good starting points:

- *How many patients are there?*
- *¿Cuántos pacientes hay?*
- *What are the most common diagnoses?*
- *How many visits per department?*

In **mock mode** (the default) the assistant answers a fixed set of sample
questions. In **vLLM mode** it can handle open-ended questions about the schema.

## Feedback

After a data answer you'll be asked *"Was this answer correct?"*. Reply **yes**
or **no**. Your feedback is stored so good question→SQL pairs can be reviewed
and added to the curated examples over time.

## Seeing the SQL

By default the SQL is hidden. Set `DEBUG_CHAT=true` to expose a trace showing the
retrieved tables and the exact query that ran.
