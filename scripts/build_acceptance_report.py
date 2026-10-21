"""Build the submission PDF from the actual, synthetic-data live verification record."""
import hashlib
import json
from pathlib import Path
import subprocess
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Preformatted

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/pdf/1021_CampusClaw_个人项目阶段性验收报告.pdf"
TEMP = ROOT / "tmp/pdfs"
TEMP.mkdir(parents=True, exist_ok=True)
OUT.parent.mkdir(parents=True, exist_ok=True)
SOURCE = ROOT / "apitest/report/platform-live-evidence.json"
original = json.loads(SOURCE.read_text(encoding="utf-8"))
api_summary = json.loads((ROOT / "apitest/report/summary.json").read_text(encoding="utf-8"))
unit_log = (ROOT / "tmp/final-acceptance-unit-tests.log").read_text(encoding="utf-8", errors="replace")
assert "Ran 48 tests" in unit_log and unit_log.rstrip().endswith("OK")
assert api_summary == {"tests": 31, "failures": 0, "skipped": 0}
regression = {"date": "2026-10-21", "unit_tests": {"tests": 48, "failures": 0}, "api_tests": api_summary,
              "models": "mock for regression; real DeepSeek in separate live evidence",
              "not_run": ["browser click and visual acceptance", "Docker Compose build/start", "Nginx deployment"]}
assert len(original["checks"]) == 5 and all(item["status"] == "PASS" for item in original["checks"])
REPO = "https://github.com/Eppiehu/campusclaw-coursework"
evidence = {"verified_at": original["started_at"], "source": "Real DeepSeek / MySQL / Qdrant / stdio MCP",
            "data_scope": "New synthetic demonstration data only; no existing private materials or credentials",
            "checks": original["checks"], "turns": []}
for turn in original["turns"]:
    item = {"question": turn["question"], "model_requests": [], "final_events": turn["events"]}
    for record in turn["trace"]:
        if record["event"] == "llm.request":
            item["model_requests"].append({"url": record["data"]["url"], "body": record["data"]["body"],
                                           "raw_content": "", "raw_tool_call_deltas": [], "finish_reasons": []})
        elif record["event"] == "llm.response":
            current = item["model_requests"][-1]
            for choice in record["data"].get("choices", []):
                current["raw_content"] += choice.get("delta", {}).get("content") or ""
                if choice.get("delta", {}).get("tool_calls"):
                    current["raw_tool_call_deltas"].append(choice["delta"]["tool_calls"])
                if choice.get("finish_reason"):
                    current["finish_reasons"].append(choice["finish_reason"])
    evidence["turns"].append(item)
encoded = json.dumps(evidence, ensure_ascii=False, indent=2).encode("utf-8")
# Public evidence is restricted to known synthetic data; omit auth and raw reasoning.
for secret_marker in (b'"Authorization"', b'"OPENAI_API_KEY"', b'"password"'):
    assert secret_marker not in encoded
evidence_path = ROOT / "docs/evidence/20261021-llm-requests.json"
evidence_path.parent.mkdir(parents=True, exist_ok=True)
evidence_path.write_bytes(encoded)
(evidence_path.parent / "20261021-regression-summary.json").write_text(json.dumps(regression, ensure_ascii=False, indent=2), encoding="utf-8")
digest = hashlib.sha256(encoded).hexdigest()

pdfmetrics.registerFont(TTFont("CN", "C:/Windows/Fonts/simhei.ttf"))
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BodyCN", fontName="CN", fontSize=10.2, leading=16, spaceAfter=7, wordWrap="CJK", textColor=colors.HexColor("#263548")))
styles.add(ParagraphStyle(name="SmallCN", parent=styles["BodyCN"], fontSize=8.8, leading=13, spaceAfter=4))
styles.add(ParagraphStyle(name="TitleCN", parent=styles["BodyCN"], fontSize=26, leading=36, spaceAfter=14, textColor=colors.HexColor("#123B52")))
styles.add(ParagraphStyle(name="H1CN", parent=styles["BodyCN"], fontSize=19, leading=26, spaceAfter=12, textColor=colors.HexColor("#123B52")))
styles.add(ParagraphStyle(name="H2CN", parent=styles["BodyCN"], fontSize=12.4, leading=18, spaceBefore=8, spaceAfter=7, textColor=colors.HexColor("#0D807D")))
styles.add(ParagraphStyle(name="CodeCN", fontName="CN", fontSize=8.1, leading=10.6, spaceAfter=7,
                          backColor=colors.HexColor("#F1F5F8"), borderPadding=8, wordWrap="CJK"))
W, H = A4
WIDTH = W - 92
story = []


def p(text, style="BodyCN"):
    story.append(Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[style]))


def h(text):
    p(text, "H2CN")


def code(text):
    # Wrap by rendered width, so Chinese JSON and long URLs stay inside the page.
    lines = []
    for line in str(text).splitlines():
        part = ""
        for char in line:
            if pdfmetrics.stringWidth(part + char, "CN", 8.1) > WIDTH - 22:
                lines.append(part)
                part = "  " + char
            else:
                part += char
        lines.append(part)
    story.append(Preformatted("\n".join(lines), styles["CodeCN"]))


def table(headers, rows, widths):
    data = [[Paragraph(escape(str(cell)), styles["SmallCN"]) for cell in row] for row in [headers, *rows]]
    item = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    item.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDEDEC")),
                             ("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#D5DFE7")),
                             ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(item)
    story.append(Spacer(1, 8))


def page(number, title):
    if story:
        story.append(PageBreak())
    p(f"{number:02d}  {title}", "H1CN")


first, disabled, mcp = evidence["turns"]
first_request = first["model_requests"][0]
first_body = first_request["body"]
first_meta = next(data for name, data in first["final_events"] if name == "meta")
flow = next(item["data"] for item in original["turns"][0]["trace"] if item["event"] == "flow.context")
skill = flow["skill"]

p("个人项目 · 阶段性验收", "SmallCN")
p("CampusClaw\n班级 AI 应用平台", "TitleCN")
p("项目介绍与五项实现验证报告", "H2CN")
p("验收日期：2026年10月21日（北京时间）\n项目仓库账号：Eppiehu")
story.append(Paragraph(f'<link href="{REPO}" color="#0D807D">Git仓库：{REPO}</link>', styles["BodyCN"]))
p("项目面向班级教学场景：教师配置 AI 应用、提示词模板、技能及知识材料；学生选择本班应用提问，获得带来源的流式回答。外部 MCP 工具支持由模型发起的计算与时间查询。")
table(["正式验收要求", "项目实现"], [
    ("内置多个 AI 应用", "首次初始化为每班内置数学学习助手、语文阅读助手，分别绑定提示词模板与内置技能。教师可继续新建和调整应用。"),
    ("提示词模板", "班级内独立管理、复用、启停；应用每轮读取有效模板并传入模型system消息。"),
    ("知识库检索", "支持keyword/vector/hybrid；服务端按用户班级、应用绑定材料限定范围，保留标题、切片和原文offset。"),
    ("内置及上传 Skill", "内置数学/语文解题引导；支持上传UTF-8文本与SKILL.md，兼容课堂YAML模板和原中文格式。"),
    ("外部工具及 MCP", "独立stdio MCP进程提供calculator/current_time；支持工具发现、模型tool_calls、执行与结果回传。"),
], [130, WIDTH-130])
h("技术组成")
p("Python / Flask 3.x / Jinja；MySQL保存业务正文与会话，Qdrant保存向量，BGE中文嵌入本地运行；DeepSeek负责回答。API使用Bearer Token，页面保留Flask签名Cookie会话。")
p("调用链：浏览器 → Flask权限与编排 → 检索/技能/模板 → DeepSeek；模型需要工具时，由Flask连接独立MCP进程，回传结果后继续生成。", "SmallCN")

page(1, "验证一：每轮参数、模板与返回")
p("结论：PASS。实际捕获了3轮对话共4次模型HTTP请求。第3轮因调用MCP产生两次模型请求。下列值来自真实记录，未以模拟输出替代。")
table(["参数", "实际值"], [("接口", first_request["url"]), ("model", first_body["model"]),
    ("stream / temperature / max_tokens", f"{first_body['stream']} / {first_body['temperature']} / {first_body['max_tokens']}"),
    ("首轮messages", "system + user；停用Skill后的下一轮包含system + user + assistant + user"),
    ("模板传递", "模板原文完整进入system；每轮从当前应用的有效模板读取。")], [143, WIDTH-143])
h("首轮实际 system 原文")
code(first_body["messages"][0]["content"])
h("实际问题与模型返回正文")
p(first["question"])
p(first_request["raw_content"], "SmallCN")
finishes = first_request["finish_reasons"]
p(f"上游finish_reason：{', '.join(finishes)}。该样例达到600 token上限，原始正文在句中结束；这里忠实保留截断内容。此项PASS表示参数、模板传递和原始返回已核对，不表示该样例回答完整。", "SmallCN")
p("完整4次请求body及逐次原始返回正文，已作为JSON附件嵌入本PDF，同时保存于仓库docs/evidence/20261021-llm-requests.json。未包含密钥、Authorization或已有私人材料。", "SmallCN")

page(2, "验证二：知识库是否全量发送")
p("结论：PASS。演示材料实际分为11片，本轮仅4片进入模型请求。已绑定知识库并不会将全部正文发送给模型。")
h("实际发送的来源")
table(["引用", "材料与切片", "原文offset", "发送字数"], [
    (f"[{item['id']}]", f"{item['title']} / {item['chunk_index']}", f"{item['start_offset']}-{item['end_offset']}", len(item["content"]))
    for item in first_meta["citations"]], [43, 241, 113, WIDTH-397])
h("服务端范围与检索顺序")
p("当前用户数据库班级 ∩ 当前应用绑定materials ∩ 命中技能的可选subject标题过滤；候选材料不取自客户端传入的班级。")
p("关键词检索与向量检索各最多20条；向量端同时过滤class_id/material_id并使用Cosine阈值0.35；混合结果使用RRF（K=60）融合，最终取Top4非空片段。")
h("消息放置")
p("标题、切片编号与每片最多800字的正文，放在user消息的材料数据区。system只保存角色/技能/约束，知识材料不作为system指令执行。")
code(first_body["messages"][-1]["content"][:300] + "\n[本页仅节选；完整user消息见PDF JSON附件]")
h("权限与溯源断言")
p("自动测试额外放入未绑定的A班材料与B班材料，确认它们的正文未进入请求。最终引用保留title、chunk_index、start_offset与end_offset，输出编号与meta/数据库来源一致。")

page(3, "验证三：Skill传递范围与模板")
p("结论：PASS。绑定后先路由选择技能；只有本轮命中技能的完整Markdown正文进入system。文件的YAML头部用于名称和适用描述，未将整个文件或所有候选技能一起发送。")
h("课堂 SKILL.md 格式")
code("---\nname: " + skill["name"] + "\ndescription: " + skill["trigger_text"] + "\n---")
h("本次命中技能的完整正文")
code(skill["description"])
p("说明：照片只展示到“重要提示”标题。本项目示例正文由项目编写，已在文件内注明；没有冒充老师照片未展示的原文。", "SmallCN")
table(["文件区域", "项目用途", "是否整体进入system"], [
    ("name", "技能名称与界面标记", "否"),
    ("YAML description", "适用场景与确定性路由依据", "否"),
    ("Markdown正文", "本轮命中技能的指令说明", "是，完整正文"),
    ("其他候选技能", "只参与路由，最多选1个", "否"),
], [114, 237, WIDTH-351])
p("原中文“名称/适用条件/资料/工具/启用”格式仍兼容；标准文件仅支持name与description头部，重复字段、非法类型与危险YAML标签会被拒绝。", "SmallCN")

page(4, "验证四：技能的实际执行逻辑")
p("结论：PASS。当前技能以声明式文本影响模型，不在服务器执行上传文件中的代码。执行流程与选择条件均有代码和测试对应。")
for index, text in enumerate([
    "校验会话归属、用户和班级，读取会话已锁定的AI应用。",
    "仅加载本班、已绑定该应用且enabled的技能候选。",
    "中文旧格式按适用条件分词做小写substring计分；标准description以去重中文二字词及英文词匹配，排除部分通用词。",
    "得分最高者命中；同分取id较小者；最高分为0则不选，一轮最多1个技能。",
    "保存用户问题；在应用绑定材料中检索，并应用命中技能的可选subject范围。",
    "将模板/角色、命中技能正文及安全约束放入system；历史和当前材料分别进入适当消息。",
    "DeepSeek实际生成新增delta，必要时经过输出边界处理；助手正文、技能名与引用落库后发送done。",
], 1):
    p(f"{index}. {text}")
h("真实启停对照")
table(["请求", "meta.skill", "system是否含技能正文"], [
    ("首轮历史探究问题", "history-lab", "包含，已逐字核对"),
    ("同会话停用技能后再问", "null", "不包含；应用模板仍在"),
], [188, 110, WIDTH-298])
h("停用后真实返回正文")
p(disabled["model_requests"][0]["raw_content"], "SmallCN")
p("内置数学/语文解题引导还带输出限制：只给检查方向，避免最终得数和完整过程。原始上游文本与最终入库文本可能不同，报告证据分别保存两者。", "SmallCN")

page(5, "验证五：MCP参数与调用闭环")
p("结论：PASS。模型实际请求calculator，独立MCP进程返回1304；该结果进入第二次DeepSeek请求，随后生成最终回答。")
mcp_first, mcp_second = mcp["model_requests"]
h("第一轮实际 tools 与 tool_choice")
code(json.dumps({"tools": mcp_first["body"]["tools"], "tool_choice": mcp_first["body"]["tool_choice"]}, ensure_ascii=False, indent=2))
h("模型工具请求与后端执行")
assistant_tool = next(message for message in mcp_second["body"]["messages"] if message.get("tool_calls"))
code(json.dumps(assistant_tool["tool_calls"], ensure_ascii=False, indent=2))
p("MCP顺序：initialize → notifications/initialized → tools/list → tools/call。后端只执行当前应用绑定且服务器允许的工具，并校验JSON Schema；本例参数为expression=(127+36)*8。", "SmallCN")
h("第二轮新增的实际 tool 消息")
tool_message = next(message for message in mcp_second["body"]["messages"] if message["role"] == "tool")
code(json.dumps(tool_message, ensure_ascii=False, indent=2))
p(mcp_second["raw_content"], "SmallCN")
p("第二轮保留原system/user，并附加assistant.tool_calls和上述role=tool结果；tool_call_id与调用编号一致。完整model/messages/tools/stream等参数见附件。", "SmallCN")

page(6, "回归、复现与证据索引")
table(["验证范围", "结果与实际口径"], [
    ("五项课堂验证", "PASS：真实DeepSeek + MySQL + Qdrant + 独立MCP；仅新建虚构演示数据外发。"),
    ("新增平台测试", "PASS：标准技能、模板、MCP等10项；内置应用、班级隔离、幂等初始化另有2项。"),
    ("原有及新增单元测试", "PASS：完整48/48通过；原有认证、班级隔离、上传下载、SSE及新增平台功能均纳入回归。"),
    ("按URL组织的API回归", "PASS：31/31通过，含内置多应用初始化、模板与MCP用例；失败0、跳过0。"),
    ("HTTP与前端解析", "PASS：首个delta早于上游完成；UTF-8/CRLF分包解析、模块语法检查通过。"),
    ("未执行范围", "NOT RUN：浏览器人工按钮点击、Docker Compose构建/启动、Nginx部署。"),
], [143, WIDTH-143])
h("复现方式")
code("# 参照README配置.env，启动MySQL和Qdrant\npython scripts/init_mysql.py\npython -m unittest discover -s tests -v\npython apitest/run_all.py\npython scripts/verify_platform_live.py --live\npython -m flask --app 'app:create_app()' run --port 8080")
p("普通测试使用隔离SQLite与模拟模型；live脚本使用真实服务。--live会发送新建演示内容并产生API用量。真实测试完成后会清理当次演示业务数据。", "SmallCN")
h("代码与证据位置")
for label, path in [
    ("默认应用", "app/platform_seeds.py"), ("提示词模板", "app/prompt_api.py"),
    ("技能解析/路由", "app/skill_files.py"), ("会话与Prompt", "app/conversation_flow.py"),
    ("模型SSE与工具循环", "app/chat_stream.py"), ("MCP连接/服务", "app/mcp_client.py / app/mcp_demo_server.py"),
    ("五项真实验证脚本", "scripts/verify_platform_live.py"), ("完整请求/返回证据", "docs/evidence/20261021-llm-requests.json"),
]:
    p(label + "：" + path, "SmallCN")
p("JSON证据SHA-256：" + digest, "SmallCN")
story.append(Paragraph(f'<link href="{REPO}/blob/main/docs/evidence/20261021-llm-requests.json" color="#0D807D">打开仓库中的完整请求与返回证据</link>', styles["SmallCN"]))
p("边界说明：当前MCP支持stdio与两个只读示例工具；技能为文本路由和提示注入，不提供任意程序执行。模型输出受token上限约束。知识库索引本机已迁移至WSL Linux文件系统，正文保留在MySQL。", "SmallCN")


def decorate(canvas, document):
    canvas.setStrokeColor(colors.HexColor("#0D807D"))
    canvas.setLineWidth(2)
    canvas.line(46, H-34, W-46, H-34)
    canvas.setFont("CN", 8)
    canvas.setFillColor(colors.HexColor("#6F8290"))
    canvas.drawString(46, 25, "CampusClaw | 个人项目阶段性验收 | 2026-10-21")
    canvas.drawRightString(W-46, 25, str(document.page))


base = TEMP / "acceptance-report-base.pdf"
SimpleDocTemplate(str(base), pagesize=A4, leftMargin=46, rightMargin=46, topMargin=52, bottomMargin=44,
                  title="CampusClaw 个人项目阶段性验收报告", author="Eppiehu", pageCompression=1).build(story, onFirstPage=decorate, onLaterPages=decorate)
writer = PdfWriter()
writer.clone_document_from_reader(PdfReader(base))
writer.add_attachment("20261021-llm-requests.json", encoded)
with OUT.open("wb") as stream:
    writer.write(stream)
reader = PdfReader(OUT)
all_text = "\n".join(page.extract_text() or "" for page in reader.pages)
assert all(term in all_text for term in ["验证一", "验证二", "验证三", "验证四", "验证五", "1304", REPO])
assert "20261021-llm-requests.json" in reader.attachments
print("PDF:", OUT)
print("Pages:", len(reader.pages))
print("Evidence SHA256:", digest)
