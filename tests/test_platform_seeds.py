from app.db import get_db
from app.platform_seeds import seed_platform_apps, DEFAULTS
from tests.support import Fixture


class BuiltinApplicationsTests(Fixture):
    def test_fresh_install_multiple_apps_templates_skills_and_class_isolation(self):
        with self.app.app_context():
            db = get_db()
            seed_platform_apps(db)
            seed_platform_apps(db)
            for class_id in ("A", "B"):
                rows = db.execute("SELECT * FROM tutor_agents WHERE class_id=? ORDER BY id", (class_id,)).fetchall()
                self.assertEqual([row["name"] for row in rows], [item[0] for item in DEFAULTS])
                for row in rows:
                    self.assertEqual(db.execute("SELECT class_id FROM prompt_templates WHERE id=?", (row["prompt_template_id"],)).fetchone()[0], class_id)
                    skill = db.execute("SELECT s.class_id FROM skills s JOIN tutor_agent_skills b ON s.id=b.skill_id WHERE b.agent_id=?", (row["id"],)).fetchone()
                    self.assertEqual(skill[0], class_id)
        headers = self.login("student_a1")
        apps = self.client.get("/api/agents", headers=headers).json["agents"]
        self.assertEqual(len(apps), 2)
        self.assertTrue(all(row["class_id"] == "A" for row in apps))

    def test_reinitialization_preserves_teacher_edits_and_deletion(self):
        with self.app.app_context():
            db = get_db()
            seed_platform_apps(db)
            first = db.execute("SELECT id FROM tutor_agents WHERE class_id='A' ORDER BY id").fetchone()[0]
            db.execute("UPDATE tutor_agents SET name='教师定制应用',enabled=0 WHERE id=?", (first,))
            db.execute("DELETE FROM tutor_agent_skills WHERE agent_id=?", (first,))
            seed_platform_apps(db)
            row = db.execute("SELECT name,enabled FROM tutor_agents WHERE id=?", (first,)).fetchone()
            self.assertEqual(tuple(row), ("教师定制应用", 0))
            self.assertIsNone(db.execute("SELECT skill_id FROM tutor_agent_skills WHERE agent_id=?", (first,)).fetchone())
