from unittest.mock import patch
from flask import g
from app.conversation_flow import build_messages, prepare_turn, history_messages
from app.db import get_db
from tests.support import Fixture


class FlowFixture(Fixture):
    def setUp(self):
        super().setUp()
        self.teacher = self.login()
        self.math = self.upload("数学方程资料", "数学方程需要检查变形的依据。", self.teacher)
        self.language = self.upload("语文阅读资料", "阅读需要先找到上下文。", self.teacher)
        skills = self.client.get("/api/skills", headers=self.teacher).json["skills"]
        self.math_skill = next(item["id"] for item in skills if item["name"] == "数学解题引导")
        self.language_skill = next(item["id"] for item in skills if item["name"] == "语文解题引导")
        self.agent_a = self.client.post("/api/agents", json={"name": "数学助手", "skill_ids": [self.math_skill], "material_ids": [self.math]}, headers=self.teacher).json["agent"]["id"]
        self.agent_b = self.client.post("/api/agents", json={"name": "语文助手", "skill_ids": [self.language_skill], "material_ids": [self.language]}, headers=self.teacher).json["agent"]["id"]
        self.student_client = self.app.test_client()
        self.student = self.login("student_a1", self.student_client)
        self.cid = self.student_client.post("/api/conversations", json={"agent_id": self.agent_a}, headers=self.student).json["conversation"]["id"]

    def prepare(self, question):
        with self.app.test_request_context(), patch("app.hybrid_search.embed_text", return_value=[1.0, 0.0]):
            g.user = get_db().execute("SELECT id,username,role,class_id FROM users WHERE username='student_a1'").fetchone()
            turn = prepare_turn(self.cid, question)
            return turn, build_messages(turn)


class FlowTests(FlowFixture):
    def test_bindings_routing_subject_and_prompt_boundary(self):
        turn, messages = self.prepare("我这道语文阅读题错在哪里？")
        self.assertIsNone(turn["skill"])
        self.assertTrue(all(item["material_id"] == self.math for item in turn["citations"]))
        self.assertNotIn("语文阅读资料", messages[-1]["content"])
        self.client.patch(f"/api/agents/{self.agent_a}", json={"skill_ids": [self.language_skill]}, headers=self.teacher)
        mismatched, _ = self.prepare("语文阅读题")
        self.assertEqual(mismatched["skill"]["id"], self.language_skill)
        self.assertEqual(mismatched["citations"], [])
        self.client.patch(f"/api/agents/{self.agent_a}", json={"skill_ids": [self.math_skill]}, headers=self.teacher)
        turn, messages = self.prepare("方程这一步怎么检查？")
        self.assertEqual(turn["skill"]["id"], self.math_skill)
        self.assertIn("dataBoundary", messages[0]["content"])
        self.assertIn("耐心", messages[0]["content"])
        self.assertNotIn("数学方程资料", messages[0]["content"])
        self.assertIn("数学方程资料", messages[-1]["content"])
        self.assertTrue(all(len(item["content"]) <= 800 for item in turn["citations"]))
        self.client.patch(f"/api/skills/{self.math_skill}", json={"enabled": False}, headers=self.teacher)
        self.assertIsNone(self.prepare("方程这一步怎么检查？")[0]["skill"])
        self.client.patch(f"/api/skills/{self.math_skill}", json={"enabled": True}, headers=self.teacher)
        self.client.patch(f"/api/agents/{self.agent_a}", json={"skill_ids": []}, headers=self.teacher)
        self.assertIsNone(self.prepare("方程这一步怎么检查？")[0]["skill"])
        self.client.patch(f"/api/agents/{self.agent_a}", json={"material_ids": []}, headers=self.teacher)
        self.assertEqual(self.prepare("方程")[0]["citations"], [])

    def test_history_last_six_role_and_500_characters(self):
        with self.db() as connection:
            records = [(self.cid, "user" if index % 2 == 0 else "assistant", str(index) + "字" * 600, "[]") for index in range(10)]
            connection.executemany("INSERT INTO messages (conversation_id,role,content,citations_json) VALUES (?,?,?,?)", records)
            connection.execute("INSERT INTO messages (conversation_id,role,content,citations_json) VALUES (?,'system','秘密','[]')", (self.cid,))
            connection.execute("INSERT INTO messages (conversation_id,role,content,citations_json) VALUES (?,'assistant',' ','[]')", (self.cid,))
        with self.app.app_context():
            history = history_messages(self.cid, 99999)
            self.assertEqual(len(history), 4)
            self.assertEqual([item["content"][0] for item in history], ["6", "7", "8", "9"])
            self.assertTrue(all(len(item["content"]) == 500 for item in history))

    def test_title_first24_and_disabled_locked_agent(self):
        question = "方程" * 30
        first, _ = self.prepare(question)
        self.client.patch(f"/api/agents/{self.agent_a}", json={"enabled": False}, headers=self.teacher)
        second, _ = self.prepare("后续问题")
        self.assertEqual(second["agent"]["id"], self.agent_a)
        with self.db() as connection:
            row = connection.execute("SELECT title,agent_id FROM conversations WHERE id=?", (self.cid,)).fetchone()
            self.assertEqual(row["title"], question[:24])
            self.assertEqual(row["agent_id"], self.agent_a)
        self.assertEqual(self.student_client.post("/api/conversations", json={"agent_id": self.agent_a}, headers=self.student).status_code, 404)
