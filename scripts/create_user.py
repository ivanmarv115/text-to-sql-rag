#!/usr/bin/env python3
"""Create (or update) a login user in the ``user_credentials`` table.

Standalone helper — not shipped inside the Docker image. Connects to the
Chainlit/audit database using the same ``CHAINLIT_DB_*`` environment variables
as the app and stores a bcrypt-hashed password.

    python scripts/create_user.py <username> <password> "Display Name" [role]

Example:

    python scripts/create_user.py admin s3cret "Administrator" admin
"""

from __future__ import annotations

import argparse
import os
import sys


def dsn() -> str:
    return (
        "host={host} port={port} dbname={db} user={user} password={pw}".format(
            host=os.environ.get("CHAINLIT_DB_HOST", "localhost"),
            port=os.environ.get("CHAINLIT_DB_PORT", "5432"),
            db=os.environ.get("CHAINLIT_DB_NAME", "chainlit"),
            user=os.environ.get("CHAINLIT_DB_USER", "app"),
            pw=os.environ.get("CHAINLIT_DB_PASSWORD", ""),
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update a login user.")
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument("display_name", nargs="?", default="")
    parser.add_argument("role", nargs="?", default="user")
    args = parser.parse_args()

    try:
        import bcrypt
        import psycopg2
    except ImportError as exc:
        print(f"Missing dependency: {exc}. Run `pip install -r requirements.txt`.", file=sys.stderr)
        return 2

    hashed = bcrypt.hashpw(args.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = psycopg2.connect(dsn())
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_credentials (identifier, hashed_password, display_name, role)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (identifier) DO UPDATE
                    SET hashed_password = EXCLUDED.hashed_password,
                        display_name   = EXCLUDED.display_name,
                        role           = EXCLUDED.role
                """,
                (args.username, hashed, args.display_name, args.role),
            )
        conn.commit()
    finally:
        conn.close()

    print(f"User '{args.username}' (role={args.role}) created/updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
