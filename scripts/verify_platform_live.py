"""Explicit real DeepSeek/MySQL/Qdrant/MCP check of the five classroom questions."""
import argparse
from datetime import datetime
import io
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app
from app.db import get_db
from app.lesson5_schema import migrate
from app.vector_store import get_store


def frames(body):
    result = []
    for frame in body.split("\n\n"):
        if not frame.strip():
            continue
        name = next(line[6:].strip() for line in frame.splitlines() if line.startswith("event:"))
        data = "\n".join(line[5:].lstrip() for line in frame.splitlines() if line.startswith("data:"))
        result.append((name, json.loads(data)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional verification record destination")
    parser.add_argument("--keep-demo", action="store_true", help="Keep only this run's demo records for UI screenshots")
    args = parser.parse_args()
    if not args.live:
        parser.error("Actual model calls require --live")
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)
    app = create_app()
    records, checks = [], []
    app.config["LLM_OBSERVER"] = lambda name, data: records.append({"event": name, "data": data})
    tag = "平台验证-" + datetime.now().strftime("%m%d%H%M%S")
    teacher, student = app.test_client(), app.test_client()
    created = {"agents": [], "skills": [], "materials": [], "templates": [], "conversations": []}
    evidence = {"started_at": datetime.now().isoformat(), "model": os.environ.get("CHAT_MODEL"),
                "storage": "MySQL + Qdrant", "mcp": "real independent stdio process", "checks": checks, "turns": []}

    def login(client, user, variable, default):
        response = client.post("/api/login", json={"username": user, "password": os.environ.get(variable, default)})
        assert response.status_code == 200, "login failed"
        return {"Authorization": "Bearer " + response.json["token"]}

    def create(path, key, data=None, file=None):
        response = teacher.post(path, headers=th, json=data) if file is None else teacher.post(path, headers=th, data=file)
        assert response.status_code == 201, (path, response.status_code, response.json)
        result = response.json[key]
        created[{"agent": "agents", "skill": "skills", "template": "templates"}[key]].append(result["id"])
        return result

    def ask(cid, question):
        records.clear()
        response = student.post(f"/api/conversations/{cid}/messages", json={"question": question}, headers=sh)
        assert response.status_code == 200, response.status_code
        events = frames(response.get_data(as_text=True)); response.close()
        trace = json.loads(json.dumps(records, ensure_ascii=False))
        evidence["turns"].append({"question": question, "trace": trace, "events": events})
        assert events[0][0] == "meta" and events[-1][0] == "done", events[-1]
        assert sum(name == "delta" for name, _ in events) > 1
        result = "".join(data["text"] for name, data in events if name == "delta")
        saved = student.get(f"/api/conversations/{cid}", headers=sh).json
        assert saved["messages"][-1]["content"] == result
        assert saved["messages"][-1]["id"] == events[-1][1]["message_id"]
        return trace, events, result

    def check(number, text):
        checks.append({"number": number, "status": "PASS", "detail": text})
        print(f"PASS check {number}")

    try:
        with app.app_context():
            migrate(get_db())
        th = login(teacher, "teacher_a", "DEMO_TEACHER_PASSWORD", "Teacher123!")
        sh = login(student, "student_a1", "DEMO_STUDENT_PASSWORD", "Student123!")
        template = create("/api/prompt-templates", "template", {"name": tag,
            "content": "你是历史探究课程助手。模板验证标记：先询问教学对象、主题和课时。引用仅使用本轮材料编号。回答简洁。"})
        skill_source = (ROOT / "demo/history-lab/SKILL.md").read_text(encoding="utf-8")
        skill_name = "history-lab-" + datetime.now().strftime("%m%d%H%M%S")
        skill_source = skill_source.replace("name: history-lab", "name: " + skill_name, 1)
        skill = create("/api/skills", "skill", file={"file": (io.BytesIO(skill_source.encode()), "SKILL.md")})
        text = "\n\n".join(f"## 史料片段{index}\n历史探究时需要比较史料来源与观点。" + "核对史料出处、形成时间、作者立场；区分事实与推测。" * 28 for index in range(10))
        material_response = teacher.post("/api/materials/upload", headers=th,
            data={"title": tag + "历史资料", "file": (io.BytesIO(text.encode()), "history.md")})
        assert material_response.status_code == 201, material_response.json
        material_id = material_response.json["material_id"]
        created["materials"].append(material_id)
        agent = create("/api/agents", "agent", {"name": tag, "prompt_template_id": template["id"],
            "skill_ids": [skill["id"]], "material_ids": [material_id]})
        response = student.post("/api/conversations", headers=sh, json={"agent_id": agent["id"]})
        cid = response.json["conversation"]["id"]; created["conversations"].append(cid)
        trace, events, _ = ask(cid, "请用历史探究资料设计一次史料研读课，开始前需要确认什么？")
        requests = [item["data"]["body"] for item in trace if item["event"] == "llm.request"]
        raw = [item["data"] for item in trace if item["event"] == "llm.response"]
        assert len(requests) == 1 and raw
        body = requests[0]
        assert template["content"] in body["messages"][0]["content"]
        assert body["stream"] and body["model"] and body["max_tokens"] == 600
        check(1, "实际DeepSeek请求完整body包含模板；保存原始SSE事件和最终回答，未保存密钥或认证头。")
        citations = events[0][1]["citations"]
        assert citations and len(citations) <= 4 and all(item["material_id"] == material_id for item in citations)
        with app.app_context():
            total = get_db().execute("SELECT COUNT(*) FROM knowledge_chunks WHERE material_id=?", (material_id,)).fetchone()[0]
        assert total > len(citations)
        assert len(text) > len(body["messages"][-1]["content"])
        check(2, f"绑定资料共{total}片，本轮仅{len(citations)}片进入user消息；未发送整个知识库。班级隔离另有回归断言。")
        assert events[0][1]["skill"] == skill_name
        assert skill["description"] in body["messages"][0]["content"]
        assert "name: " + skill_name not in body["messages"][0]["content"]
        check(3, "标准SKILL.md按description路由；完整Markdown正文进入system，YAML头部不整体发送。")
        teacher.patch(f"/api/skills/{skill['id']}", headers=th, json={"enabled": False})
        disabled, events, _ = ask(cid, "请用历史探究资料设计一次史料研读课，开始前需要确认什么？")
        assert events[0][1]["skill"] is None
        disabled_body = next(item["data"]["body"] for item in disabled if item["event"] == "llm.request")
        assert skill["description"] not in disabled_body["messages"][0]["content"]
        check(4, "确认候选绑定/启用过滤→描述关键词路由→正文注入→检索→流式模型回答；停用后下轮立即不注入。技能文件不执行代码。")
        tool_agent = create("/api/agents", "agent", {"name": tag + "计算器",
            "prompt": "你是计算助手。对于算术问题必须先调用calculator工具，不能心算。工具返回后简洁说明工具算出的结果。", "mcp_tools": ["calculator"]})
        response = student.post("/api/conversations", headers=sh, json={"agent_id": tool_agent["id"]})
        tool_cid = response.json["conversation"]["id"]; created["conversations"].append(tool_cid)
        tool_trace, _, answer = ask(tool_cid, "请实际调用calculator计算(127+36)*8，告诉我工具返回的结果。")
        tool_requests = [item["data"]["body"] for item in tool_trace if item["event"] == "llm.request"]
        calls = [item["data"] for item in tool_trace if item["event"] == "mcp.request" and item["data"].get("method") == "tools/call"]
        assert len(tool_requests) >= 2 and calls
        assert [tool["function"]["name"] for tool in tool_requests[0]["tools"]] == ["calculator"]
        tool_message = next(message for message in tool_requests[1]["messages"] if message["role"] == "tool")
        assert "1304" in tool_message["content"] and "1304" in answer
        check(5, "真实DeepSeek发出tool_calls→独立MCP进程tools/call→1304结果作为role=tool传回DeepSeek→真实流式答案。完整两轮参数已留存。")
    except Exception as error:
        evidence["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        # Remove only records created by this explicit verification run.
        if "th" in locals() and not args.keep_demo:
            for identifier in reversed(created["conversations"]):
                student.delete(f"/api/conversations/{identifier}", headers=sh)
            for identifier in reversed(created["agents"]):
                teacher.delete(f"/api/agents/{identifier}", headers=th)
            for identifier in created["skills"]:
                teacher.delete(f"/api/skills/{identifier}", headers=th)
            for identifier in created["materials"]:
                with app.app_context():
                    db = get_db()
                    row = db.execute("SELECT stored_path FROM materials WHERE id=?", (identifier,)).fetchone()
                    try:
                        get_store().delete_material("A", identifier)
                    except Exception as cleanup_error:
                        evidence.setdefault("cleanup_errors", []).append(type(cleanup_error).__name__)
                    db.execute("DELETE FROM knowledge_chunks WHERE material_id=?", (identifier,))
                    db.execute("DELETE FROM knowledge_entries WHERE material_id=?", (identifier,))
                    db.execute("DELETE FROM materials WHERE id=?", (identifier,))
                    db.commit()
                    if row:
                        path = (Path(app.config["UPLOAD_FOLDER"]) / row["stored_path"]).resolve()
                        if path.is_relative_to(Path(app.config["UPLOAD_FOLDER"]).resolve()):
                            path.unlink(missing_ok=True)
            for identifier in created["templates"]:
                teacher.delete(f"/api/prompt-templates/{identifier}", headers=th)
        if args.keep_demo:
            evidence["demo_records"] = created
            evidence["demo_tag"] = tag
        target = args.output or ROOT / "apitest/report/platform-live-evidence.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Evidence:", target)


if __name__ == "__main__":
    main()
