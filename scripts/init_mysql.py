"""Initialize MySQL and optionally import the existing SQLite coursework data."""
import os
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db import MySQLConnection
from app.lesson5_schema import migrate
from app.platform_seeds import seed_platform_apps
from scripts.init_db import SCHEMA


def initialize():
    url = os.environ["DATABASE_URL"]
    connection = MySQLConnection(url)
    try:
        schema = re.sub(r"PRAGMA[^;]+;", "", SCHEMA)
        schema = re.sub(r"CREATE INDEX IF NOT EXISTS[^;]+;", "", schema)
        schema = schema.replace("AUTOINCREMENT", "AUTO_INCREMENT")
        schema = schema.replace("id TEXT PRIMARY KEY", "id VARCHAR(32) PRIMARY KEY")
        schema = schema.replace("class_id TEXT", "class_id VARCHAR(32)")
        schema = schema.replace("name TEXT", "name VARCHAR(128)")
        schema = schema.replace("role TEXT", "role VARCHAR(16)")
        schema = schema.replace("TEXT NOT NULL DEFAULT (datetime('now'))", "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP")
        for statement in schema.split(";"):
            if statement.strip():
                connection.execute(statement)
        old_path = Path(os.environ.get("SQLITE_MIGRATE_FROM", "data/app.db"))
        empty = not connection.execute("SELECT id FROM users LIMIT 1").fetchone()
        if empty and old_path.is_file():
            source = sqlite3.connect(old_path)
            source.row_factory = sqlite3.Row
            try:
                for table in ("classes", "users", "materials", "knowledge_entries", "knowledge_chunks"):
                    records = source.execute(f"SELECT * FROM {table}").fetchall()
                    target_columns = {row["Field"] for row in connection.execute(f"SHOW COLUMNS FROM {table}").fetchall()}
                    for record in records:
                        fields = [field for field in record.keys() if field in target_columns]
                        connection.execute(f"INSERT IGNORE INTO {table} ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", [record[field] for field in fields])
                connection.commit()
            finally:
                source.close()
        if not connection.execute("SELECT id FROM users LIMIT 1").fetchone():
            from werkzeug.security import generate_password_hash
            connection.executemany("INSERT IGNORE INTO classes (id,name) VALUES (?,?)", [("A", "A班"), ("B", "B班")])
            for username, role, class_id, variable, default in [
                ("teacher_a", "teacher", "A", "DEMO_TEACHER_PASSWORD", "Teacher123!"),
                ("student_a1", "student", "A", "DEMO_STUDENT_PASSWORD", "Student123!"),
                ("student_b1", "student", "B", "DEMO_STUDENT_PASSWORD", "Student123!"),
            ]:
                connection.execute("INSERT INTO users (username,password_hash,role,class_id) VALUES (?,?,?,?)", (username, generate_password_hash(os.environ.get(variable, default)), role, class_id))
            connection.commit()
        migrate(connection)
        seed_platform_apps(connection)
        print("MySQL schema and lesson-5 migrations ready (credentials redacted).")
    finally:
        connection.close()


if __name__ == "__main__":
    initialize()
