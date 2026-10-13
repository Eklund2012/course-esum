"""
Migration script: adds student_quotes (JSON) and teacher_reflection (TEXT)
columns to evaluation_reports in the existing SQLite database.

Run once after deploying the student-quote extraction feature.
Safe to run multiple times — skips columns that already exist.
"""
import sys
import sqlite3
from pathlib import Path

DB_PATHS = [
    Path("course_esum.db"),
    Path("src/course_esum.db"),
]

MIGRATIONS = [
    ("student_quotes", "TEXT DEFAULT '[]' NOT NULL"),
    ("teacher_reflection", "TEXT"),
]


def migrate(db_path: Path) -> None:
    if not db_path.exists():
        print(f"  Skipping {db_path} (not found)")
        return

    print(f"Migrating {db_path} ...")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(evaluation_reports)")
        existing = {row[1] for row in cur.fetchall()}
        print(f"  Existing columns: {sorted(existing)}")

        for col_name, col_def in MIGRATIONS:
            if col_name in existing:
                print(f"  Column '{col_name}' already exists — skipping.")
            else:
                sql = f"ALTER TABLE evaluation_reports ADD COLUMN {col_name} {col_def}"
                print(f"  Executing: {sql}")
                cur.execute(sql)
                print(f"  Column '{col_name}' added.")

        conn.commit()
        print(f"  Migration complete for {db_path}.")
    finally:
        conn.close()


if __name__ == "__main__":
    for p in DB_PATHS:
        migrate(p)
    print("All done.")
