"""Five classroom checks against real assembly, SSE transport adapter and MCP process."""
import io
import json
import os
import unittest
from unittest.mock import patch
from jsonschema import ValidationError
from app.skill_files import parse_skill, route_skill
from app.mcp_client import MCPSession
from tests.test_lesson5_flow import FlowFixture
from tests.test_lesson5_sse import decode_events

TEACHER_DESCRIPTION = "打造历史探究学习资源包，包含史料卡片库、多维探究教案、批判性练习及博物馆风格交互网页，支持随机点名抽题；当用户需要制作探究式历史课件、设计史料研读课程或开展历史批判思维教学时使用"
# The photo ends at the heading. The instruction below is our own test fixture.
STANDARD = f"---\nname: history-lab\ndescription: {TEACHER_DESCRIPTION}\n---\n\n# 历史探究实验室\n\n## 重要提示\n先询问教学对象和历史主题，再设计史料研读活动。"


def sse(*deltas):
    return io.BytesIO(("".join("data: " + json.dumps({"choices": [{"delta": delta}]}, ensure_ascii=False) + "\n\n" for delta in deltas)
                       + "data: [DONE]\n\n").encode())


class StandardSkillTests(unittest.TestCase):
    def test_teacher_yaml_template_and_routing(self):
        parsed = parse_skill(STANDARD)
        self.assertEqual(parsed["name"], "history-lab")
        self.assertEqual(parsed["trigger_text"], TEACHER_DESCRIPTION)
        self.assertTrue(parsed["description"].startswith("# 历史探究实验室"))
        self.assertEqual(parsed["source_text"], STANDARD)
        self.assertEqual(parsed["enabled"], 1)
        candidate = {**parsed, "id": 5}
        self.assertEqual(route_skill("请设计历史探究课件", [candidate])["id"], 5)
        self.assertIsNone(route_skill("今天午饭吃什么", [candidate]))
        self.assertIsNone(route_skill("我需要学习帮助", [candidate]))

    def test_yaml_strict_validation(self):
        for bad in (STANDARD.replace("name: history-lab", "name: a\nname: b"),
                    STANDARD.replace("name: history-lab", "name: [a]"),
                    STANDARD.replace("name: history-lab", "name: history-lab\nshell: echo bad"),
                    STANDARD.replace("name: history-lab", "name: !!python/object:builtins.object {}"),
                    "---\nname: a\ndescription: b", "---\nname: a\ndescription: b\n---"):
            with self.subTest(sample=bad[:50]), self.assertRaises(ValueError):
                parse_skill(bad)
        folded = parse_skill("---\nname: test\ndescription: >\n  历史探究\n  史料研读\n---\n正文")
        self.assertIn("史料研读", folded["trigger_text"])


class PlatformTests(FlowFixture):
    def template(self):
        response = self.client.post("/api/prompt-templates", headers=self.teacher,
            json={"name": "苏格拉底式提问", "content": "模板验证标记：先询问学生的推理依据，再给建议。"})
        self.assertEqual(response.status_code, 201, response.json)
        return response.json["template"]

    def ask_wire(self, question, responses):
        captured = []
        traces = []
        self.app.config["LLM_OBSERVER"] = lambda name, data: traces.append((name, data))
        def upstream(request, **_kwargs):
            captured.append(json.loads(request.data))
            self.assertEqual(request.get_header("Content-type"), "application/json")
            return responses[len(captured)-1]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-not-a-secret"}), \
             patch("app.chat_stream.urlopen", side_effect=upstream), \
             patch("app.hybrid_search.embed_text", return_value=[1.0, 0.0]):
            response = self.student_client.post(f"/api/conversations/{self.cid}/messages",
                json={"question": question}, headers=self.student)
            events = decode_events(response.get_data(as_text=True))
            response.close()
        self.assertEqual(events[0][0], "meta")
        self.assertEqual(events[-1][0], "done", events[-1])
        return captured, traces, events

    def test_template_crud_binding_scope_and_effective_prompt(self):
        template = self.template()
        tid = template["id"]
        self.assertEqual(self.client.post("/api/prompt-templates", headers=self.student,
                                        json={"name": "x", "content": "y"}).status_code, 403)
        b = self.login("student_b1")
        self.assertEqual(self.client.get(f"/api/prompt-templates/{tid}", headers=b).status_code, 404)
        self.assertEqual(self.client.get("/api/prompt-templates", headers=b).json["templates"], [])
        self.assertEqual(self.client.patch(f"/api/agents/{self.agent_a}", headers=self.teacher,
            json={"prompt_template_id": tid}).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/prompt-templates/{tid}", headers=self.teacher).status_code, 409)
        _, messages = self.prepare("方程")
        self.assertIn(template["content"], messages[0]["content"])
        self.client.patch(f"/api/prompt-templates/{tid}", headers=self.teacher, json={"content": "更新后的模板标记"})
        self.assertIn("更新后的模板标记", self.prepare("方程")[1][0]["content"])
        self.client.patch(f"/api/prompt-templates/{tid}", headers=self.teacher, json={"enabled": False})
        self.assertNotIn("更新后的模板标记", self.prepare("方程")[1][0]["content"])
        self.assertEqual(self.client.patch(f"/api/agents/{self.agent_a}", headers=self.teacher,
            json={"prompt_template_id": tid, "name": "数学助手"}).status_code, 200)
        self.assertEqual(self.client.get(f"/api/prompt-templates/{tid}", headers=self.student).status_code, 404)
        self.client.patch(f"/api/agents/{self.agent_a}", headers=self.teacher, json={"prompt_template_id": None})
        self.assertEqual(self.client.delete(f"/api/prompt-templates/{tid}", headers=self.teacher).status_code, 200)

    def test_cross_class_template_binding_and_tool_write_denied(self):
        with self.db() as db:
            tid = db.execute("INSERT INTO prompt_templates (class_id,name,content) VALUES ('B','他班','不允许')").lastrowid
        self.assertEqual(self.client.patch(f"/api/agents/{self.agent_a}", headers=self.teacher,
            json={"prompt_template_id": tid}).status_code, 404)
        self.assertEqual(self.client.patch(f"/api/agents/{self.agent_a}", headers=self.student,
            json={"mcp_tools": ["calculator"]}).status_code, 403)
        self.assertEqual(self.client.patch(f"/api/agents/{self.agent_a}", headers=self.teacher,
            json={"mcp_tools": ["shell"]}).status_code, 400)
        self.assertEqual(self.client.get("/api/mcp/tools").status_code, 401)

    def test_check1_exact_request_template_and_raw_response(self):
        template = self.template()
        self.client.patch(f"/api/agents/{self.agent_a}", headers=self.teacher, json={"prompt_template_id": template["id"]})
        for index in range(2):
            captured, traces, events = self.ask_wire(f"方程如何检查，第{index}轮", [sse({"content": "最终答案是2。"})])
            request = captured[0]
            self.assertEqual(set(request), {"model", "messages", "stream", "temperature", "max_tokens"})
            self.assertTrue(request["stream"])
            self.assertIn(template["content"], request["messages"][0]["content"])
            self.assertEqual(next(data["body"] for name, data in traces if name == "llm.request"), request)
            raw = "".join(data["choices"][0]["delta"].get("content", "") for name, data in traces if name == "llm.response")
            final = "".join(data["text"] for name, data in events if name == "delta")
            self.assertEqual(raw, "最终答案是2。")
            self.assertNotEqual(raw, final)
            self.assertNotIn("最终答案", final)
            self.assertNotIn("test-key-not-a-secret", json.dumps(traces))
            if index:
                self.assertGreater(len(request["messages"]), 2)
            with self.db() as db:
                self.assertEqual(db.execute("SELECT content FROM messages WHERE id=?", (events[-1][1]["message_id"],)).fetchone()[0], final)

    def test_check2_only_retrieved_bound_class_chunks(self):
        unbound = self.upload("未绑定的数学资料", "禁止传递的未绑定标记", self.teacher)
        with self.db() as db:
            b_text = db.execute("SELECT content FROM knowledge_entries WHERE class_id='B'").fetchone()[0]
        captured, _, events = self.ask_wire("数学方程", [sse({"content": "先检查等式两边。[1]"})])
        citations = events[0][1]["citations"]
        self.assertTrue(citations)
        self.assertLessEqual(len(citations), 4)
        self.assertTrue(all(item["material_id"] == self.math and len(item["content"]) <= 800 for item in citations))
        payload = json.dumps(captured, ensure_ascii=False)
        self.assertNotIn("禁止传递的未绑定标记", payload)
        self.assertNotIn(b_text, payload)
        self.assertNotIn(str(unbound) + "未绑定", payload)
        for item in citations:
            self.assertIn(item["content"], captured[0]["messages"][-1]["content"])
            self.assertNotIn(item["content"], captured[0]["messages"][0]["content"])

    def test_check3_and4_skill_body_injection_routing_and_disable(self):
        response = self.client.post("/api/skills", headers=self.teacher, data={"file": (io.BytesIO(STANDARD.encode()), "SKILL.md")})
        self.assertEqual(response.status_code, 201, response.json)
        skill = response.json["skill"]
        self.client.patch(f"/api/agents/{self.agent_a}", headers=self.teacher,
                          json={"skill_ids": [skill["id"]], "material_ids": []})
        captured, _, events = self.ask_wire("请设计历史探究课程", [sse({"content": "请先说明学生年级和历史主题。"})])
        self.assertEqual(events[0][1]["skill"], "history-lab")
        system = captured[0]["messages"][0]["content"]
        self.assertIn(skill["description"], system)
        self.assertNotIn("name: history-lab", system)
        self.assertNotIn(TEACHER_DESCRIPTION, system)
        self.assertNotIn("只指出学生错在哪一步", system)
        self.assertIsNone(self.prepare("今天午饭吃什么")[0]["skill"])
        self.client.patch(f"/api/skills/{skill['id']}", headers=self.teacher, json={"enabled": False})
        disabled, _, events = self.ask_wire("请设计历史探究课程", [sse({"content": "可以先确定课程目标。"})])
        self.assertIsNone(events[0][1]["skill"])
        self.assertNotIn(skill["description"], disabled[0]["messages"][0]["content"])

    def test_real_mcp_initialize_discover_call_and_schema(self):
        response = self.client.get("/api/mcp/tools", headers=self.teacher)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual({tool["name"] for tool in response.json["tools"]}, {"calculator", "current_time"})
        with self.app.app_context(), MCPSession() as client:
            self.assertEqual(client.call("calculator", {"expression": "(12+3)*4"})["content"][0]["text"], "60")
            self.assertRegex(client.call("current_time", {})["content"][0]["text"], r"\+08:00$")
            with self.assertRaises(ValidationError):
                client.call("calculator", {"expression": "2+2", "class_id": "B"})
            with self.assertRaises(ValueError):
                client.call("shell", {})
            self.assertTrue(client.call("calculator", {"expression": "__import__('os')"})["isError"])

    def test_check5_model_tool_call_mcp_result_and_second_request(self):
        self.client.patch(f"/api/agents/{self.agent_a}", headers=self.teacher,
            json={"mcp_tools": ["calculator"], "material_ids": [], "skill_ids": []})
        captured, traces, _ = self.ask_wire("请调用计算器计算(12+3)*4", [
            sse({"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "calcu", "arguments": ""}}]},
                {"tool_calls": [{"index": 0, "function": {"name": "lator", "arguments": '{"expression":"(12+'}}]},
                {"tool_calls": [{"index": 0, "function": {"arguments": '3)*4"}'}}]}),
            sse({"content": "计算结果为60。"})])
        self.assertEqual(len(captured), 2)
        self.assertEqual([item["function"]["name"] for item in captured[0]["tools"]], ["calculator"])
        self.assertEqual(captured[0]["tool_choice"], "auto")
        returned = captured[1]["messages"][-1]
        self.assertEqual(returned["role"], "tool")
        self.assertEqual(returned["tool_call_id"], "call_1")
        self.assertEqual(json.loads(returned["content"])["content"][0]["text"], "60")
        rpc = [data for name, data in traces if name == "mcp.request"]
        self.assertEqual([message["method"] for message in rpc], ["initialize", "notifications/initialized", "tools/list", "tools/call"])
        self.assertEqual(rpc[-1]["params"], {"name": "calculator", "arguments": {"expression": "(12+3)*4"}})
        self.assertNotIn("OPENAI_API_KEY", json.dumps(traces))

    def test_unbound_model_tool_rejected_and_stream_closed(self):
        self.client.patch(f"/api/agents/{self.agent_a}", headers=self.teacher,
            json={"mcp_tools": ["calculator"], "material_ids": [], "skill_ids": []})
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("app.chat_stream.urlopen", return_value=sse(
            {"tool_calls": [{"index": 0, "id": "bad", "function": {"name": "current_time", "arguments": "{}"}}]})):
            response = self.student_client.post(f"/api/conversations/{self.cid}/messages", headers=self.student,
                json={"question": "test"})
            events = decode_events(response.get_data(as_text=True)); response.close()
        self.assertEqual([name for name, _ in events], ["meta", "error"])
