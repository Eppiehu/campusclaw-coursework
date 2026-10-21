import io
import json
import jwt
from app.skill_files import parse_skill, route_skill
from tests.support import Fixture

VALID = "名称：实验技能\n适用条件：方程,Equation\n资料：数学\n工具：knowledge_search\n启用：是\n\n只指出下一步检查什么。"


class InterfaceTests(Fixture):
    def test_jwt_core_claims_relogin_and_logout_revocation(self):
        first = self.login("student_a1")
        token = first["Authorization"].split()[1]
        claims = jwt.decode(token, options={"verify_signature": False})
        self.assertEqual(set(claims), {"sub", "jti", "iat", "exp"})
        response = self.client.post("/login", json={"username": "student_a1", "password": "Student123!"}, headers=first)
        self.assertEqual(response.status_code, 200)
        second = {"Authorization": "Bearer " + response.json["token"]}
        self.assertEqual(self.client.get("/api/me", headers=first).status_code, 401)
        self.assertEqual(self.client.post("/api/logout", json={}, headers=second).status_code, 200)
        self.assertEqual(self.client.get("/api/materials", headers=second).status_code, 401)
        with self.db() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM token_revocations").fetchone()[0], 2)

    def test_skill_parser_rejects_bad_files(self):
        self.assertEqual(parse_skill(VALID)["subject_text"], "数学")
        malformed = [VALID.replace("名称：实验技能", "名称：一\n名称：二"), VALID.replace("资料：数学", "未知：数学"),
                     VALID.split("\n\n")[0], VALID.replace("knowledge_search", "shell"),
                     VALID.replace("实验技能", "技" * 33), "文" * 8001]
        for source in malformed:
            with self.assertRaises(ValueError):
                parse_skill(source)
        candidates = [dict(parse_skill(VALID), id=9), dict(parse_skill(VALID), id=3)]
        self.assertEqual(route_skill("EQUATION 方程", candidates)["id"], 3)
        self.assertIsNone(route_skill("作文", candidates))

    def test_agent_skill_crud_scopes_and_student_writes(self):
        teacher = self.login()
        material = self.upload(headers=teacher)
        skill_response = self.client.post("/api/skills", data={"file": (io.BytesIO(VALID.encode()), "skill.txt")}, headers=teacher)
        self.assertEqual(skill_response.status_code, 201)
        skill = skill_response.json["skill"]["id"]
        agent_response = self.client.post("/api/agents", json={"name": "数学助手", "prompt": "", "skill_ids": [skill], "material_ids": [material]}, headers=teacher)
        self.assertEqual(agent_response.status_code, 201)
        agent = agent_response.json["agent"]["id"]
        self.assertEqual(agent_response.json["agent"]["prompt"], "")
        self.assertEqual(self.client.post("/api/agents", json={"name": "数学助手"}, headers=teacher).status_code, 409)
        self.assertEqual(self.client.post("/api/agents", json={"name": "a" * 65}, headers=teacher).status_code, 400)
        self.assertEqual(self.client.patch(f"/api/agents/{agent}", json={"enabled": False}, headers=teacher).status_code, 200)
        student_client = self.app.test_client()
        student = self.login("student_a1", student_client)
        self.assertEqual(student_client.get("/api/agents", headers=student).json["agents"], [])
        disabled = student_client.get(f"/api/agents/{agent}", headers=student)
        absent = student_client.get("/api/agents/9999", headers=student)
        self.assertEqual((disabled.status_code, disabled.json), (absent.status_code, absent.json))
        self.assertEqual(student_client.post("/api/agents", json={"name": "x"}, headers=student).status_code, 403)
        self.assertEqual(student_client.delete(f"/api/skills/{skill}", headers=student).status_code, 403)
        self.assertEqual(self.client.patch(f"/api/skills/{skill}", json={"enabled": False}, headers=teacher).status_code, 200)
        updated = VALID.replace("实验技能", "替换技能")
        self.assertEqual(self.client.put(f"/api/skills/{skill}", data={"file": (io.BytesIO(updated.encode()), "skill.md")}, headers=teacher).json["skill"]["name"], "替换技能")
        self.assertEqual(self.client.delete(f"/api/skills/{skill}", headers=teacher).status_code, 200)
        self.assertEqual(self.client.get(f"/api/agents/{agent}", headers=teacher).json["agent"]["skill_ids"], [])

    def test_conversation_creation_private_and_hidden_agents(self):
        teacher = self.login()
        first = self.client.post("/api/agents", json={"name": "Agent A"}, headers=teacher).json["agent"]["id"]
        disabled = self.client.post("/api/agents", json={"name": "Agent B", "enabled": False}, headers=teacher).json["agent"]["id"]
        student_client = self.app.test_client()
        student = self.login("student_a1", student_client)
        self.assertEqual(student_client.post("/api/conversations", json={"agent_id": disabled}, headers=student).status_code, 404)
        created = student_client.post("/api/conversations", json={"agent_id": first}, headers=student)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json["conversation"]["title"], "新的提问")
        cid = created.json["conversation"]["id"]
        owner_view = student_client.get(f"/api/conversations/{cid}", headers=student)
        self.assertEqual(owner_view.json["conversation"]["agent_id"], first)
        others = [self.client.get(f"/api/conversations/{cid}", headers=teacher), self.client.get("/api/conversations/9999", headers=teacher)]
        bclient = self.app.test_client()
        btoken = self.login("student_b1", bclient)
        others += [bclient.get(f"/api/conversations/{cid}", headers=btoken), bclient.get(f"/api/agents/{first}", headers=btoken)]
        with self.db() as connection:
            skill_id = connection.execute("SELECT id FROM skills WHERE class_id='A' LIMIT 1").fetchone()[0]
        others += [bclient.get(f"/api/skills/{skill_id}", headers=btoken), bclient.get("/api/skills/99999", headers=btoken)]
        for response in others:
            self.assertEqual((response.status_code, response.json), (404, {"error": "不存在"}))
        response = bclient.post("/api/search", json={"query": "数学", "class_id": "A"}, headers=btoken)
        self.assertEqual((response.status_code, response.json["hits"]), (200, []))
