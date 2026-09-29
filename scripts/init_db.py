"""Create the course database and demo rows. Safe to run more than once."""
import os
import sqlite3
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent.parent
DB_FILE = Path(os.environ.get("DATABASE", ROOT / "data" / "app.db"))

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS classes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('teacher', 'student')),
    class_id TEXT NOT NULL REFERENCES classes(id)
);
CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    class_id TEXT NOT NULL REFERENCES classes(id),
    uploaded_by INTEGER REFERENCES users(id),
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS knowledge_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL UNIQUE REFERENCES materials(id) ON DELETE CASCADE,
    class_id TEXT NOT NULL REFERENCES classes(id),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS lectures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id TEXT REFERENCES classes(id),
    title TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id TEXT REFERENCES classes(id),
    title TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assistants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id TEXT REFERENCES classes(id),
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
"""


def init_database():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.executescript(SCHEMA)
        with connection:
            connection.executemany(
                "INSERT OR IGNORE INTO classes (id, name) VALUES (?, ?)",
                [("A", "A班"), ("B", "B班")],
            )
            users = [
                ("teacher_a", "teacher", "A", os.environ.get("DEMO_TEACHER_PASSWORD", "Teacher123!")),
                ("student_a1", "student", "A", os.environ.get("DEMO_STUDENT_PASSWORD", "Student123!")),
                ("student_b1", "student", "B", os.environ.get("DEMO_STUDENT_PASSWORD", "Student123!")),
            ]
            for username, role, class_id, password in users:
                if not connection.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                    connection.execute(
                        "INSERT INTO users (username, password_hash, role, class_id) VALUES (?, ?, ?, ?)",
                        (username, generate_password_hash(password), role, class_id),
                    )
            teacher_id = connection.execute("SELECT id FROM users WHERE username='teacher_a'").fetchone()[0]
            for class_id, title in [("A", "A班演示材料"), ("B", "B班演示材料")]:
                if connection.execute("SELECT 1 FROM materials WHERE class_id=? AND title=?", (class_id, title)).fetchone():
                    continue
                text = f"# {title}\n\n这是 {class_id} 班预置的演示材料。"
                relative = Path(class_id) / f"seed_{class_id}.md"
                destination = ROOT / "uploads" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(text, encoding="utf-8")
                cursor = connection.execute(
                    "INSERT INTO materials (title, class_id, uploaded_by, original_filename, stored_path) VALUES (?, ?, ?, ?, ?)",
                    (title, class_id, teacher_id if class_id == "A" else None, f"{title}.md", relative.as_posix()),
                )
                connection.execute(
                    "INSERT INTO knowledge_entries (material_id, class_id, content) VALUES (?, ?, ?)",
                    (cursor.lastrowid, class_id, text),
                )
    finally:
        connection.close()


if __name__ == "__main__":
    init_database()
    print(f"Database initialized: {DB_FILE}")
