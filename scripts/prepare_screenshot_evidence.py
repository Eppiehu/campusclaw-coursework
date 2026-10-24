"""Render actual backend observations into read-only pages for browser screenshots."""
import hashlib
import html
import inspect
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.skill_files import route_skill

raw = json.loads((ROOT / "apitest/report/platform-screenshots-live-evidence.json").read_text(encoding="utf-8"))
assert len(raw["checks"]) == 5 and all(item["status"] == "PASS" for item in raw["checks"])
dest = ROOT / "tmp/evidence-viewer"
dest.mkdir(parents=True, exist_ok=True)
public = {"verified_at": raw["started_at"], "checks": raw["checks"], "demo_records": raw["demo_records"], "turns": []}
for turn in raw["turns"]:
    record = {"question": turn["question"], "model_requests": [], "events": turn["events"], "mcp_messages": []}
    for event in turn["trace"]:
        if event["event"] == "llm.request":
            record["model_requests"].append({"url": event["data"]["url"], "body": event["data"]["body"],
                "raw_content": "", "raw_tool_call_deltas": [], "finish_reasons": []})
        elif event["event"] == "llm.response":
            current = record["model_requests"][-1]
            for choice in event["data"].get("choices", []):
                delta = choice.get("delta", {})
                current["raw_content"] += delta.get("content") or ""
                if delta.get("tool_calls"):
                    current["raw_tool_call_deltas"].append(delta["tool_calls"])
                if choice.get("finish_reason"):
                    current["finish_reasons"].append(choice["finish_reason"])
        elif event["event"].startswith("mcp."):
            record["mcp_messages"].append(event)
    public["turns"].append(record)
encoded = json.dumps(public, ensure_ascii=False, indent=2).encode()
for marker in (b'"Authorization"', b'"password"', b'"OPENAI_API_KEY"'):
    assert marker not in encoded
path = ROOT / "docs/evidence/20261024-llm-requests.json"
path.write_bytes(encoded)
digest = hashlib.sha256(encoded).hexdigest()
first, second, tool = public["turns"]
flow = next(item["data"] for item in raw["turns"][0]["trace"] if item["event"] == "flow.context")
body = first["model_requests"][0]["body"]
skill = flow["skill"]


def esc(value):
    return html.escape(str(value))


def pre(value, compact=False):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, indent=None if compact else 2)
    return '<pre>' + esc(value) + '</pre>'


def block(title, content):
    return '<section><h2>' + esc(title) + '</h2>' + content + '</section>'


def table(head, rows):
    return '<table><tr>' + ''.join('<th>'+esc(v)+'</th>' for v in head) + '</tr>' + ''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows) + '</table>'


def page(filename, title, body_html):
    source = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{esc(title)} | CampusClaw 实测记录</title>
    <style>*{{box-sizing:border-box}}body{{margin:0;background:#edf2f5;color:#213346;font:17px/1.5 "Microsoft YaHei",sans-serif}}.sheet{{width:1160px;margin:24px auto;padding:28px 34px;background:white;border-top:5px solid #107976}}h1{{font-size:28px;line-height:1.3;margin:12px 0 18px}}h2{{font-size:19px;color:#08716f;margin:12px 0 8px}}.meta{{font-size:13px;color:#596b7b}}.badge{{background:#e3f5ed;color:#116746;padding:4px 10px;border-radius:4px;font-weight:bold}}section{{margin:14px 0}}pre{{font:15.5px/1.42 Consolas,"Microsoft YaHei",monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f9;border:1px solid #dbe5ec;padding:13px;margin:7px 0}}table{{border-collapse:collapse;width:100%;font-size:16px}}th,td{{border:1px solid #dce4ea;text-align:left;padding:8px 10px;vertical-align:top}}th{{background:#e8f2f1}}.summary{{padding:12px 16px;background:#eaf5f2;border-left:4px solid #0a8278}}.small{{font-size:14px;color:#617282}}</style>
    <main class="sheet"><div class="meta">CampusClaw · 后台实际捕获记录 · 只读取证阅读器（非开发者工具）</div><h1>{esc(title)}</h1>
    <div class="meta">实测时间：{esc(raw['started_at'])}（本机北京时间） · 代码功能基线：ef72267<br>来源：docs/evidence/20261024-llm-requests.json · SHA-256：{digest[:24]}…</div>
    {body_html}<p class="small">以上数值和文本直接取自真实DeepSeek/MySQL/Qdrant/MCP记录；长消息的完整JSON随报告提供。此页面仅用于截图阅读，没有模拟平台操作或模型结果。</p></main></html>'''
    (dest / filename).write_text(source, encoding="utf-8")


page("01-request.html", "验证1：实际 LLM 请求参数与提示词", '<div class="summary">'+esc(first["model_requests"][0]["url"])+" · POST · JSON</div>" +
    block("实际参数", pre({key: value for key, value in body.items() if key != "messages"})) +
    table(["messages", "角色", "正文字符数"], [(i, m["role"], len(m["content"])) for i,m in enumerate(body["messages"])]) +
    block("system 原文（包含模板、Skill正文和约束）", pre(body["messages"][0]["content"])))

page("02-response.html", "验证1：真实返回正文与最终 SSE", '<div class="summary">请求问题：'+esc(first["question"])+"</div>" +
    block("DeepSeek 原始 delta.content 合并正文", pre(first["model_requests"][0]["raw_content"])) +
    table(["观察项", "实际记录"], [
        ("finish_reason", first["model_requests"][0]["finish_reasons"]),
        ("SSE事件顺序", " → ".join([first["events"][0][0], "delta × " + str(sum(n=="delta" for n,d in first["events"])), first["events"][-1][0]])),
        ("最终数据库 message_id", first["events"][-1][1]["message_id"]),
        ("模板是否进入system", "是，实际system原文包含“模板验证标记：先询问教学对象、主题和课时。”"),
    ]) + block("应用最终返回的正文", pre(''.join(data["text"] for name,data in first["events"] if name=="delta"))))

hits = flow["citations"]
page("03-knowledge.html", "验证2：绑定知识库后的实际发送范围", '<div class="summary">'+esc(raw["checks"][1]["detail"])+"</div>" +
    table(["引用", "材料ID / 切片", "start-end", "发送字符数"], [(f"[{h['id']}]", f"{h['material_id']} / {h['chunk_index']}", f"{h['start_offset']}-{h['end_offset']}", len(h["content"])) for h in hits]) +
    block("实际传入消息的材料标题", pre(hits[0]["title"])) +
    block("user消息开头（原文节选，完整消息见JSON）", pre(body["messages"][-1]["content"][:430])) +
    table(["判断", "核对结果"], [("发送全部知识库？", "否：只传本轮命中的4个片段，每片≤800字"), ("服务端范围", "用户班级 ∩ 应用绑定materials ∩ 可选Skill资料范围"), ("材料消息角色", "user；system中不放检索材料正文")]))

page("04-skill-content.html", "验证3：标准 SKILL.md 与实际注入内容", '<div class="summary">实际命中：'+esc(skill["name"])+" · Markdown正文逐字出现在system中</div>" +
    block("实际上传的完整技能文件", pre(skill["source_text"])) +
    table(["区域", "用途", "是否整体发送到system"], [("name", "标识与显示", "否"), ("YAML description", "适用场景 / 路由", "否"), ("Markdown 正文", "技能指令", "是，完整正文"), ("其他候选技能", "只参与路由", "否")]))

route_source = inspect.getsource(route_skill)
page("05-skill-execution.html", "验证4：Skill执行规则与真实启停对照", '<div class="summary">绑定/启用过滤 → 描述关键词路由 → 至多选1个 → 注入正文 → 检索 → 模型流式回答</div>' +
    table(["同会话请求", "meta.skill", "system含技能正文"], [("首轮：历史探究问题", skill["name"], str(skill["description"] in body["messages"][0]["content"])),
      ("停用后再次提问", next(d for n,d in second["events"] if n=="meta")["skill"], str(skill["description"] in second["model_requests"][0]["body"]["messages"][0]["content"]))]) +
    block("真实路由源码：app/skill_files.py", pre(route_source)) +
    '<p>Skill以文本说明影响模型；服务器不执行上传文件内的Python、Shell或其他代码。</p>')

tool_first, tool_second = tool["model_requests"]
page("06-mcp-request.html", "验证5：接入MCP后的第一轮模型请求", '<div class="summary">模型只能看到当前应用绑定的 calculator；未绑定的 current_time 未进入本轮 tools。</div>' +
    block("实际 tools / tool_choice", pre({"tools":tool_first["body"]["tools"], "tool_choice":tool_first["body"]["tool_choice"]}, compact=True)) +
    table(["参数", "实际值"], [(key, tool_first["body"][key]) for key in ("model","stream","temperature","max_tokens")]) +
    block("模型实际产生的 tool_calls", pre(next(m["tool_calls"] for m in tool_second["body"]["messages"] if m.get("tool_calls")), compact=True)))

rpc_call = next(m["data"] for m in tool["mcp_messages"] if m["event"]=="mcp.request" and m["data"].get("method")=="tools/call")
rpc_response = next(m["data"] for m in tool["mcp_messages"] if m["event"]=="mcp.response" and m["data"].get("id")==rpc_call["id"])
page("07-mcp-result.html", "验证5：MCP执行与第二轮模型请求", '<div class="summary">initialize → initialized → tools/list → tools/call → role=tool → DeepSeek最终回答</div>' +
    block("真实MCP JSON-RPC请求与响应", pre({"request":rpc_call,"response":rpc_response}, compact=True)) +
    block("第二轮模型请求中的实际 tool 消息", pre(next(m for m in tool_second["body"]["messages"] if m["role"]=="tool"), compact=True)) +
    table(["第二轮messages角色顺序", "关联依据"], [(" → ".join(m["role"] for m in tool_second["body"]["messages"]), "assistant.tool_calls.id = tool.tool_call_id")]) +
    block("第二轮模型真实返回正文", pre(tool_second["raw_content"])))

(dest / "evidence.json").write_bytes(encoded)
print("Readonly screenshot pages:",dest)
print("Evidence:",path)
print("SHA256:",digest)
