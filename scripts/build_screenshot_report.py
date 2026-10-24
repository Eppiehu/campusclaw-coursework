"""Submission report with genuine browser captures and embedded full JSON evidence."""
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile
from PIL import Image as PILImage
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak, Flowable

ROOT = Path(__file__).resolve().parents[1]
SHOTDIR = ROOT / "output/screenshots/20261024"
OUTPUT = ROOT / "output/pdf/CampusClaw_阶段性验收报告_截图版.pdf"
BUNDLE = ROOT / "output/CampusClaw_截图版报告与验证证据.zip"
SOURCE = ROOT / "docs/evidence/20261024-llm-requests.json"
source_bytes = SOURCE.read_bytes()
source = json.loads(source_bytes)
assert all(row["status"] == "PASS" for row in source["checks"]) and len(source["checks"]) == 5
first, second, tools = source["turns"]
request = first["model_requests"][0]
meta = next(data for name,data in first["events"] if name == "meta")
raw = json.loads((ROOT / "apitest/report/platform-screenshots-live-evidence.json").read_text(encoding="utf-8"))
flow = next(item["data"] for item in raw["turns"][0]["trace"] if item["event"] == "flow.context")
pdfmetrics.registerFont(TTFont("ReportCN", "C:/Windows/Fonts/simhei.ttf"))
STYLES = {
    "body": ParagraphStyle("body",fontName="ReportCN",fontSize=10.3,leading=16,spaceAfter=7,wordWrap="CJK",textColor=colors.HexColor("#27394C")),
    "small": ParagraphStyle("small",fontName="ReportCN",fontSize=8.8,leading=13,spaceAfter=5,wordWrap="CJK",textColor=colors.HexColor("#52687B")),
    "title": ParagraphStyle("title",fontName="ReportCN",fontSize=25,leading=34,spaceAfter=14,textColor=colors.HexColor("#183F58")),
    "h1": ParagraphStyle("h1",fontName="ReportCN",fontSize=18,leading=25,spaceAfter=13,textColor=colors.HexColor("#183F58")),
    "h2": ParagraphStyle("h2",fontName="ReportCN",fontSize=12,leading=18,spaceBefore=6,spaceAfter=6,textColor=colors.HexColor("#0C7B77")),
}
PW, PH = A4
WIDTH = PW - 88
story = []
manifest = {"capture_date":"2026-10-24", "verification_time":source["verified_at"],
            "evidence_file":SOURCE.relative_to(ROOT).as_posix(), "evidence_sha256":hashlib.sha256(source_bytes).hexdigest(),
            "description":"Actual browser screenshots. Some figures are clipped in the PDF for readability; the original JPEG bytes remain unchanged.", "images":[]}


def p(text, style="body"):
    story.append(Paragraph(escape(str(text)).replace("\n","<br/>"), STYLES[style]))


def h(text):
    p(text,"h2")


def page(title):
    if story:
        story.append(PageBreak())
    p(title,"h1")


def table(headers, rows, widths):
    cells = [[Paragraph(escape(str(value)),STYLES["small"]) for value in row] for row in [headers,*rows]]
    t=Table(cells,colWidths=widths,repeatRows=1,hAlign="LEFT")
    t.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E0EFEC")),
                          ("GRID",(0,0),(-1,-1),.4,colors.HexColor("#D2DEE7")),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
    story.append(t);story.append(Spacer(1,8))


class Screenshot(Flowable):
    def __init__(self, path, crop, max_height):
        super().__init__()
        self.path, self.crop = path, crop
        with PILImage.open(path) as img:
            self.iw,self.ih=img.size
        left,top,right,bottom=crop
        assert 0<=left<right<=self.iw and 0<=top<bottom<=self.ih,(path,crop,self.iw,self.ih)
        self.scale=min(WIDTH/(right-left), max_height/(bottom-top))
        self.width=(right-left)*self.scale;self.height=(bottom-top)*self.scale
        self.hAlign="CENTER"

    def draw(self):
        c=self.canv;c.saveState()
        region=c.beginPath();region.rect(0,0,self.width,self.height);c.clipPath(region,stroke=0,fill=0)
        left,top,right,bottom=self.crop
        c.drawImage(str(self.path),-left*self.scale,self.height-(self.ih-top)*self.scale,
                    width=self.iw*self.scale,height=self.ih*self.scale)
        c.restoreState()


def viewer_crop(path):
    # Read pixels only to locate the page's teal rule. Never modify screenshot files.
    with PILImage.open(path).convert("RGB") as image:
        w,h=image.size
        for y in range(min(70,h)):
            xs=[x for x in range(w) if (lambda rgb: rgb[0]<100 and 65<rgb[1]<160 and 60<rgb[2]<160)(image.getpixel((x,y)))]
            if len(xs)>w*.45:
                return (max(0,min(xs)-5),max(0,y-5),min(w,max(xs)+6),h)
        return (0,0,w,h)


def fig(number, filename, caption, crop=None, max_height=460, url=None):
    path=SHOTDIR/filename
    assert path.is_file(),path
    with PILImage.open(path) as image:
        size=image.size
    if crop is None:
        crop=viewer_crop(path) if int(filename[:2])>=5 and int(filename[:2])<=11 else (0,0,*size)
    story.append(Screenshot(path,crop,max_height));story.append(Spacer(1,6))
    p(f"图{number}  {caption}","small")
    manifest["images"].append({"figure":number,"file":filename,"caption":caption,"source_url":url,
        "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"size":size,"pdf_crop":crop})


p("个人项目阶段性验收 · 截图证据版","small")
p("CampusClaw\n班级 AI 应用平台","title")
p("提交者：王闯\n验证与截图日期：2026年10月24日（北京时间）")
story.append(Paragraph('<link href="https://github.com/Eppiehu/campusclaw-coursework" color="#0C7B77">Git仓库：https://github.com/Eppiehu/campusclaw-coursework</link>',STYLES["body"]))
p("项目面向班级教学：教师管理多个AI应用、提示词模板、知识材料与技能；学生通过本班应用进行带来源的流式问答，并由模型按需调用MCP外部工具。")
table(["功能要求","实际实现与证据"],[
    ("内置多个AI应用","每班默认数学学习助手、语文阅读助手；初始化幂等。见图1。"),
    ("提示词模板","独立管理并绑定应用，每轮完整传入system。见图3、5。"),
    ("知识库检索","MySQL正文、Qdrant向量，关键词/向量/RRF混合检索与来源offset。见图7。"),
    ("内置及上传Skill","内置解题引导，支持UTF-8 .txt/.md及标准SKILL.md上传。见图4、8、9。"),
    ("外部工具与MCP","独立stdio MCP进程、工具发现、模型调用、Schema校验与结果回传。见图2、10-12。"),
], [126,WIDTH-126])
h("验收结论")
p("本次五项验证全部PASS：3轮对话实际产生4次DeepSeek请求，包含1次MCP调用及结果回传；本次模型正文均以stop正常结束。报告逐项给出截图、解释和原始JSON证据。")
h("证据口径")
p("平台截图来自真实本机应用；后台LLM/MCP截图来自实际记录的只读取证阅读器，图上明确标注。浏览器Network中的前端会话请求与后台发往DeepSeek的请求不同，本报告核对的是后者。只读阅读器为临时报告工具，没有加入产品功能。","small")
p("功能代码基线：ef72267。正式运行使用Flask/MySQL/Qdrant；本报告不将LangGraph、pgvector或RQ等后续规划写为已实现。完整请求与返回JSON已嵌入PDF附件。","small")

page("01  平台功能：多个应用与工具绑定")
p("教师配置页实际列出数学、语文等多个启用应用。验证用计算器应用绑定calculator，工具选择与后续模型请求中的tools一致。")
fig(1,"03-built-in-ai-apps.jpg","真实应用列表区域：包含内置数学学习助手、语文阅读助手。",crop=(193,235,840,660),max_height=340,url="http://127.0.0.1:8080/manage")
fig(2,"04-mcp-binding.jpg","真实配置中的MCP选择区，calculator处于选中状态。",crop=(190,18,820,215),max_height=160,url="http://127.0.0.1:8080/manage")
p("当前默认MCP工具为计算器和北京时间，应用只向模型开放已绑定工具；未绑定调用会被拒绝。工具进程不继承模型密钥、数据库凭据或用户Token。","small")

page("02  平台功能：提示词模板与技能上传")
fig(3,"02-prompt-template.jpg","教师点击编辑后，页面显示本次应用使用的真实模板原文。",crop=(375,220,995,655),max_height=505,url="http://127.0.0.1:8080/manage")
p("模板内容：你是历史探究课程助手。模板验证标记：先询问教学对象、主题和课时。引用仅使用本轮材料编号。回答简洁。")
p("模板单独保存、按班级管理，并通过prompt_template_id绑定应用。每轮读取当前启用模板；停用后回退到应用角色设定。")

page("03  平台功能：内置技能与文件上传")
fig(4,"01-platform-templates-skills.jpg","真实技能管理区域：上传入口、标准文件格式和数学/语文内置技能。",crop=(590,190,1150,925),max_height=480,url="http://127.0.0.1:8080/manage")
p("本次通过教师上传接口提交标准SKILL.md，生成技能“"+flow["skill"]["name"]+"”。文件头为name和description，后接Markdown正文；界面支持替换文件、启用与停用。")
p("数学/语文解题引导为内置技能。标准文件与原中文字段格式并存，文件由服务器解析和校验，上传文本不作为程序执行。")

page("04  验证一：具体请求参数与模板传递")
p("结论：PASS。实际后台请求为POST "+request["url"]+"，请求体包含model、messages、stream、temperature和max_tokens。")
fig(5,"05-validation1-request.jpg","实际请求参数和system原文；模板验证标记可逐字核对。",max_height=490,url="http://127.0.0.1:8765/01-request.html")
p("本次参数：model=deepseek-flash，stream=true，temperature=0.1，max_tokens=600。首轮messages为system + user，正文字符数分别为445和3312。模板全文与本轮命中技能正文均进入system。","small")
p("3轮对话的4次完整模型请求及返回正文见PDF附件20261024-llm-requests.json；本页图片没有截取Authorization或密钥。","small")

page("05  验证一：返回正文与SSE结果")
fig(6,"06-validation1-response.jpg","DeepSeek原始正文与应用最终正文，以及SSE和数据库message_id。",max_height=480,url="http://127.0.0.1:8765/02-response.html")
p("首轮实际SSE顺序为meta → "+str(sum(n=="delta" for n,d in first["events"]))+"个delta → done，最终message_id="+str(first["events"][-1][1]["message_id"])+"。验证脚本读取会话数据库返回，断言入库正文等于全部delta顺序拼接。")
p("原始上游正文与最终正文分别留存。当前样例二者相同；内置解题引导等场景可能经过输出边界处理，不能以最终正文代替原始上游响应。")

page("06  验证二：是否发送全部知识库")
fig(7,"07-validation2-rag.jpg","实际只发送11个片段中的4个，展示引用编号、材料ID、offset与字数。",max_height=470,url="http://127.0.0.1:8765/03-knowledge.html")
p("结论：PASS，未全量发送。检索限定为用户数据库班级 ∩ 当前应用绑定材料 ∩ 可选Skill资料范围；关键词和向量结果以RRF融合，最终仅取Top4非空片段，每片最多800字。")
p("本轮材料ID="+str(meta["citations"][0]["material_id"])+"，发送片段的字符数为"+"、".join(str(len(hit["content"])) for hit in meta["citations"])+"。标题与片段正文位于user材料数据区，不放在system。")

page("07  验证三：Skill是否完整传入")
fig(8,"08-validation3-skill.jpg","实际上传文件及区域映射：YAML用于元数据和路由，Markdown正文完整注入。",max_height=470,url="http://127.0.0.1:8765/04-skill-content.html")
p("结论：PASS。本轮命中技能的Markdown正文完整进入system；YAML的name/description没有作为整块文件头一并注入。绑定多个技能时也不会全部发送，每轮最多选择一个命中技能。")
p("本次已断言skill.description逐字出现在system，同时断言“name: "+flow["skill"]["name"]+"”未出现在system。课堂照片未展示的正文由本项目编写，示例文件已明确注明。","small")

page("08  验证四：Skill执行逻辑")
fig(9,"09-validation4-execution.jpg","真实启停对照及当前route_skill源码。",max_height=470,url="http://127.0.0.1:8765/05-skill-execution.html")
p("结论：PASS。流程：会话和班级校验 → 取应用绑定且启用的技能 → 关键词评分路由 → 至多选一个 → 注入技能正文 → 限定范围检索 → 模型流式回答 → 保存正文与来源。")
p("最高分为0不选择技能，同分取id较小者。标准description按中文二字词与英文词匹配；原中文格式按适用条件分词匹配。停用后再次问同一句，meta.skill为null，system中不再包含该技能正文。")

page("09  验证五：MCP后的模型请求参数")
fig(10,"10-validation5-tools.jpg","第一轮实际tools、tool_choice和模型产生的tool_calls。",max_height=455,url="http://127.0.0.1:8765/06-mcp-request.html")
p("结论：PASS。基础参数仍为model/messages/stream/temperature/max_tokens；绑定MCP后增加tools与tool_choice=auto。tools包含工具名称、说明和JSON Schema，本轮只出现calculator，没有未绑定的current_time。")
p("模型实际请求expression=(127+36)*8。后端对绑定范围、调用轮数和JSON Schema校验后才执行MCP工具，不接受模型请求未绑定工具。")

page("10  验证五：工具执行与第二轮回传")
fig(11,"11-validation5-roundtrip.jpg","真实tools/call请求与1304响应、第二轮role=tool以及最终模型正文。",max_height=450,url="http://127.0.0.1:8765/07-mcp-result.html")
p("MCP使用独立stdio进程，依次initialize、initialized、tools/list及tools/call。工具结果通过role=tool放入第二轮DeepSeek请求，tool_call_id与assistant.tool_calls.id一致。")
p("第二轮messages角色顺序为system → user → assistant → tool，模型最终回答明确引用工具结果1304；这两次模型调用的finish_reason分别为tool_calls和stop。")

page("11  平台实际问答结果")
fig(12,"12-live-chat-result.jpg","真实学生端会话正文区域，显示本次问题与工具计算结果1304。",crop=(470,210,1490,675),max_height=410,url="http://127.0.0.1:8080/tutor")
p("本次计算会话ID="+str(source["demo_records"]["conversations"][1])+"，锁定计算器应用ID="+str(source["demo_records"]["agents"][1])+"。浏览器截图与前述后台记录中的问题、表达式和答案相互对应。")
p("此图为已保存会话的真实浏览器回放。后台SSE新增delta与数据库一致性由本次验证断言；本次未把会话回放截图等同于浏览器实时流式动画验收。","small")

page("12  结论、复现与完整证据")
table(["验证项","结果","本报告证据"],[
    ("1. 请求、返回与模板","PASS","图3、5、6；完整4次请求与返回JSON"),
    ("2. 知识库发送范围","PASS","图7；11片中仅发送4片"),
    ("3. Skill发送内容","PASS","图8与图5；完整正文注入，头部不整体注入"),
    ("4. Skill执行逻辑","PASS","图9；源码与启停前后实际请求对照"),
    ("5. MCP参数与闭环","PASS","图2、10-12；真实计算与role=tool回传"),
], [170,62,WIDTH-232])
h("测试记录与限制")
p("2026-10-24重新执行上述五项真实验证，均通过；浏览器实际登录、模板读取、工具选择查看与会话回放已截图。2026-10-21完整回归记录为48项单元、31项API通过，本次不将历史回归计为当天重跑。")
p("NOT RUN：Docker Compose构建启动、Nginx部署、浏览器实时逐段动画验收。本次未更换课程实现技术栈，也未将简历中的终版规划混入报告。")
h("证据文件")
p("完整请求、响应正文、MCP JSON-RPC与SSE事件：20261024-llm-requests.json（已嵌入PDF附件）；截图清单与SHA-256：screenshots-manifest.json（同样嵌入）。截图包保留原始JPEG，PDF只在排版时取局部区域，未改写图片内容。","small")
p("JSON SHA-256："+manifest["evidence_sha256"],"small")
h("复现命令")
p("1. 按README启动MySQL、Qdrant及Flask，配置本地.env。\n2. python scripts/verify_platform_live.py --live --keep-demo --output apitest/report/platform-screenshots-live-evidence.json\n3. python scripts/prepare_screenshot_evidence.py\n4. 使用浏览器截图保存到output/screenshots/20261024，再运行python scripts/build_screenshot_report.py。","small")
story.append(Paragraph('<link href="https://github.com/Eppiehu/campusclaw-coursework" color="#0C7B77">打开个人项目Git仓库</link>',STYLES["body"]))


def decorate(canvas,doc):
    canvas.setLineWidth(1.5);canvas.setStrokeColor(colors.HexColor("#0C7B77"));canvas.line(44,PH-32,PW-44,PH-32)
    canvas.setFont("ReportCN",8);canvas.setFillColor(colors.HexColor("#6F8290"))
    canvas.drawString(44,24,"CampusClaw | 个人项目阶段性验收 · 截图证据版 | 2026-10-24")
    canvas.drawRightString(PW-44,24,str(doc.page))


temp=ROOT/"tmp/pdfs/screenshot-report-base.pdf";temp.parent.mkdir(parents=True,exist_ok=True)
SimpleDocTemplate(str(temp),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=52,bottomMargin=42,
    title="王闯 - CampusClaw个人项目阶段性验收报告（截图版）",author="王闯").build(story,onFirstPage=decorate,onLaterPages=decorate)
manifest_bytes=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
(SHOTDIR/"screenshots-manifest.json").write_bytes(manifest_bytes)
writer=PdfWriter();writer.clone_document_from_reader(PdfReader(temp))
writer.add_attachment("20261024-llm-requests.json",source_bytes);writer.add_attachment("screenshots-manifest.json",manifest_bytes)
OUTPUT.parent.mkdir(parents=True,exist_ok=True)
with OUTPUT.open("wb") as file:writer.write(file)
reader=PdfReader(OUTPUT)
assert len(manifest["images"])==12
assert len(reader.pages)==13,len(reader.pages)
assert len(reader.attachments)==2
texts="\n".join(page.extract_text() or "" for page in reader.pages)
assert all(word in texts for word in ("验证一","验证二","验证三","验证四","验证五","1304","github.com/Eppiehu"))
with zipfile.ZipFile(BUNDLE,"w",zipfile.ZIP_DEFLATED) as archive:
    archive.write(OUTPUT,OUTPUT.name)
    archive.write(SOURCE,SOURCE.name)
    archive.writestr("screenshots-manifest.json",manifest_bytes)
    for item in manifest["images"]:archive.write(SHOTDIR/item["file"],"screenshots/"+item["file"])
    archive.writestr("说明.txt","直接提交PDF即可。截图与完整JSON另行提供，便于核对。截图均为2026-10-24实际浏览器捕获，后端参数图来自实际记录只读阅读器；未包含密钥、登录令牌和已有私人材料。")
print("PDF:",OUTPUT,"Pages:",len(reader.pages))
print("Screenshots:",len(manifest["images"]))
print("Bundle:",BUNDLE)
