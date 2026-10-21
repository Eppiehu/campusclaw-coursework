import io
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.hybrid_search import cosine
from scripts import init_db


class MemoryVectors:
    """Test double, never selected by production configuration."""
    def __init__(self):
        self.points = {}
        self.created = False
        self.filters = []

    def ensure(self, dimensions):
        new = not self.created
        self.created = True
        return new

    def upsert(self, points):
        self.points.update({point["id"]: point for point in points})

    def query(self, vector, class_id, material_ids, limit):
        self.filters.append((class_id, material_ids, limit))
        hits = [{"id": point["id"], "score": cosine(vector, point["vector"]), "payload": point["payload"]}
                for point in self.points.values()
                if point["payload"]["class_id"] == class_id and point["payload"]["material_id"] in material_ids]
        return sorted([point for point in hits if point["score"] >= .35], key=lambda point: (-point["score"], point["id"]))[:limit]

    def delete_material(self, class_id, material_id):
        self.points = {key: point for key, point in self.points.items()
                       if not (point["payload"]["class_id"] == class_id and point["payload"]["material_id"] == material_id)}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        old_root, old_db = init_db.ROOT, init_db.DB_FILE
        try:
            init_db.ROOT, init_db.DB_FILE = self.root, self.root / "data/app.db"
            init_db.init_database()
        finally:
            init_db.ROOT, init_db.DB_FILE = old_root, old_db
        self.vectors = MemoryVectors()
        self.app = create_app({"TESTING": True, "SECRET_KEY": "lesson5-test-secret", "DATABASE_URL": None,
                               "DATABASE": str(self.root / "data/app.db"), "UPLOAD_FOLDER": str(self.root / "uploads"),
                               "VECTOR_STORE": self.vectors})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def login(self, user="teacher_a", client=None):
        client = client or self.client
        password = "Teacher123!" if user.startswith("teacher") else "Student123!"
        response = client.post("/login", json={"username": user, "password": password})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return {"Authorization": "Bearer " + response.json["token"]}

    def upload(self, title="数学方程", text="数学方程要先检查等式两边。", headers=None):
        response = self.client.post("/materials/upload", data={"title": title, "file": (io.BytesIO(text.encode()), title + ".md")}, headers=headers)
        self.assertEqual(response.status_code, 302)
        with self.db() as db:
            return db.execute("SELECT id FROM materials WHERE title=? ORDER BY id DESC", (title,)).fetchone()[0]
