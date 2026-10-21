import json
import os
import re
from unittest.mock import patch
from tests.test_lesson5_flow import FlowFixture


def decode_events(body):
    result = []
    for frame in body.replace("\r\n", "\n").split("\n\n"):
        if not frame.strip():
            continue
        name = next(line[6:].strip() for line in frame.splitlines() if line.startswith("event:"))
        data = "\n".join(line[5:].lstrip() for line in frame.splitlines() if line.startswith("data:"))
        result.append((name, json.loads(data)))
    return result


class StreamingTests(FlowFixture):
    def test_guidance_ref_duplicate_across_chunks(self):
        from app.chat_stream import OutputBoundary
        boundary = OutputBoundary({"skill": {"name": "数学解题引导"}, "citations": [{"id": 1}]})
        parts = boundary.feed("最终答案是2。")
        parts += boundary.feed("[1]\n", final=True)
        text = "".join(parts)
        self.assertIn("下一步", text)
        self.assertEqual(text.count("[1]"), 1)

    def send(self, question="方程该检查哪一步？", **body):
        with patch("app.hybrid_search.embed_text", return_value=[1.0, 0.0]):
            response = self.student_client.post(f"/api/conversations/{self.cid}/messages", json={"question": question, **body}, headers=self.student, buffered=False)
        return response

    def test_true_incremental_meta_first_done_after_commit(self):
        state = {"finished": False, "called": False}
        def provider(messages):
            state["called"] = True
            self.assertIn("本轮是解题引导", messages[0]["content"])
            yield "先检查你进行等式变形时，是否对两边做了相同的操作。[1]"
            yield "下一步核对该步骤所用的依据。[1]"
            state["finished"] = True
        self.app.config["CHAT_STREAM_FACTORY"] = provider
        response = self.send(agent_id=self.agent_b)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content_type.startswith("text/event-stream"))
        self.assertEqual(response.headers["X-Accel-Buffering"], "no")
        iterator = iter(response.response)
        first = next(iterator).decode()
        self.assertEqual(decode_events(first)[0][0], "meta")
        self.assertFalse(state["called"])
        second = next(iterator).decode()
        self.assertEqual(decode_events(second)[0][0], "delta")
        self.assertFalse(state["finished"])
        events = decode_events(first + second + b"".join(iterator).decode())
        response.close()
        self.assertGreater(sum(name == "delta" for name, _ in events), 1)
        self.assertEqual(events[-1][0], "done")
        text = "".join(data["text"] for name, data in events if name == "delta")
        self.assertIn("[1]", text)
        with self.db() as connection:
            row = connection.execute("SELECT * FROM messages WHERE id=?", (events[-1][1]["message_id"],)).fetchone()
            self.assertEqual(row["content"], text)
            self.assertEqual(row["skill_name"], "数学解题引导")
            self.assertEqual(connection.execute("SELECT agent_id FROM conversations WHERE id=?", (self.cid,)).fetchone()[0], self.agent_a)
            citations = json.loads(row["citations_json"])
            self.assertEqual(citations, events[0][1]["citations"])
            self.assertTrue(all(int(ref) in {item["id"] for item in citations} for ref in re.findall(r"\[(\d+)\]", text)))

    def test_no_evidence_still_calls_model_and_no_citations(self):
        self.client.patch(f"/api/agents/{self.agent_a}", json={"material_ids": [], "skill_ids": []}, headers=self.teacher)
        called = []
        def provider(messages):
            called.append(messages)
            yield "可以先拆分你想解决的问题。["
            yield "1]再逐一说明已知条件。"
        self.app.config["CHAT_STREAM_FACTORY"] = provider
        response = self.send("如何安排学习计划？")
        events = decode_events(response.get_data(as_text=True))
        response.close()
        self.assertEqual(len(called), 1)
        self.assertEqual(events[0][1]["citations"], [])
        text = "".join(item["text"] for name, item in events if name == "delta")
        self.assertNotRegex(text, r"\[\d+\]")
        self.assertNotIn("未找到相关内容", text)

    def test_guidance_changes_after_skill_disabled(self):
        self.app.config["CHAT_STREAM_FACTORY"] = lambda messages: iter(["最终答案是 x = 2。"])
        enabled = self.send()
        first = decode_events(enabled.get_data(as_text=True)); enabled.close()
        text = "".join(data["text"] for name, data in first if name == "delta")
        self.assertNotIn("最终答案", text)
        self.assertNotIn("x = 2", text)
        self.assertIn("下一步", text)
        self.client.patch(f"/api/skills/{self.math_skill}", json={"enabled": False}, headers=self.teacher)
        disabled = self.send()
        second = decode_events(disabled.get_data(as_text=True)); disabled.close()
        self.assertIsNone(second[0][1]["skill"])
        self.assertIn("x = 2", "".join(data["text"] for name, data in second if name == "delta"))

    def test_partial_failure_persisted_error_and_empty_failure(self):
        def partial(messages):
            yield "先检查当前步骤的依据"
            raise RuntimeError("mock upstream failure")
        self.app.config["CHAT_STREAM_FACTORY"] = partial
        response = self.send()
        events = decode_events(response.get_data(as_text=True)); response.close()
        self.assertEqual(events[-1][0], "error")
        self.assertIsNotNone(events[-1][1]["message_id"])
        text = "".join(data["text"] for name, data in events if name == "delta")
        with self.db() as connection:
            self.assertEqual(connection.execute("SELECT content FROM messages WHERE id=?", (events[-1][1]["message_id"],)).fetchone()[0], text)
        def empty(messages):
            raise RuntimeError("mock empty failure")
            yield ""
        self.app.config["CHAT_STREAM_FACTORY"] = empty
        response = self.send(); events = decode_events(response.get_data(as_text=True)); response.close()
        self.assertEqual([name for name, _ in events], ["meta", "error"])
        self.assertIsNone(events[-1][1]["message_id"])

    def test_pre_stream_statuses(self):
        path = f"/api/conversations/{self.cid}/messages"
        self.assertEqual(self.student_client.post(path, json={"question": "x"}).status_code, 401)
        self.assertEqual(self.student_client.post(path, json={"question": ""}, headers=self.student).status_code, 400)
        self.assertEqual(self.student_client.post("/api/conversations/99999/messages", json={"question": "x"}, headers=self.student).status_code, 404)
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), patch("app.hybrid_search.embed_text", return_value=[1.0, 0.0]):
            self.assertEqual(self.student_client.post(path, json={"question": "x"}, headers=self.student).status_code, 503)
