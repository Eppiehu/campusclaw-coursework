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


p("个人项目阶段性验收报告","small")
p("CampusClaw 班级 AI 应用平台","title")
p("姓名：王闯")
story.append(Paragraph('<link href="https://github.com/Eppiehu/campusclaw-coursework" color="#0C7B77">Git仓库：https://github.com/Eppiehu/campusclaw-coursework</link>',STYLES["body"]))
h("一、项目简介")
p("CampusClaw是一个面向班级教学的AI应用平台。教师可以配置学习助手，管理提示词模板、知识材料和技能；学生使用本班应用进行问答，查看回答引用的材料。应用还可以绑定MCP工具，由模型根据问题决定是否调用。后端使用Flask，材料和会话保存在MySQL中，向量检索使用Qdrant，回答由DeepSeek生成。")
table(["课程要求","项目实现"],[
    ("内置多个AI应用","每班默认数学学习助手、语文阅读助手；初始化幂等。见图1。"),
    ("提示词模板","独立管理并绑定应用，每轮完整传入system。见图3、5。"),
    ("知识库检索","MySQL正文、Qdrant向量，关键词/向量/RRF混合检索与来源offset。见图7。"),
    ("内置及上传Skill","内置解题引导，支持UTF-8 .txt/.md及标准SKILL.md上传。见图4、8、9。"),
    ("外部工具与MCP","独立stdio MCP进程、工具发现、模型调用、Schema校验与结果回传。见图2、10-12。"),
], [126,WIDTH-126])
h("二、验证方法")
p("围绕提示词、知识库、Skill和MCP完成3轮对话，共产生4次DeepSeek请求。其中计算器问题包含工具调用和结果回传两次模型请求。后文结合页面截图、请求记录和代码说明五项验证结果。")
p("平台配置和问答截图取自浏览器。后台请求截图通过本地只读页面展示捕获的LLM/MCP记录，完整JSON随报告附上。浏览器Network只能直接看到前端发给Flask的请求，因此需要在后端记录发往DeepSeek的参数。","small")

page("01  平台功能：多个应用与工具绑定")
p("教师配置页中有数学、语文等多个应用。计算器验证所用的应用绑定了calculator，后续请求中的tools与这里的选择一致。")
fig(1,"03-built-in-ai-apps.jpg","应用列表，包括数学学习助手和语文阅读助手。",crop=(193,235,840,660),max_height=340,url="http://127.0.0.1:8080/manage")
fig(2,"04-mcp-binding.jpg","MCP工具绑定，已选择calculator。",crop=(190,18,820,215),max_height=160,url="http://127.0.0.1:8080/manage")
p("当前默认MCP工具为计算器和北京时间，应用只向模型开放已绑定工具；未绑定调用会被拒绝。工具进程不继承模型密钥、数据库凭据或用户Token。","small")

page("02  平台功能：提示词模板与技能上传")
fig(3,"02-prompt-template.jpg","本次历史探究应用使用的提示词模板。",crop=(375,220,995,655),max_height=505,url="http://127.0.0.1:8080/manage")
p("模板内容：你是历史探究课程助手。模板验证标记：先询问教学对象、主题和课时。引用仅使用本轮材料编号。回答简洁。")
p("模板单独保存、按班级管理，并通过prompt_template_id绑定应用。每轮读取当前启用模板；停用后回退到应用角色设定。")

page("03  平台功能：内置技能与文件上传")
fig(4,"01-platform-templates-skills.jpg","技能上传入口、文件格式示例和内置技能。",crop=(590,190,1150,925),max_height=480,url="http://127.0.0.1:8080/manage")
p("本次通过教师上传接口提交标准SKILL.md，生成技能“"+flow["skill"]["name"]+"”。文件头为name和description，后接Markdown正文；界面支持替换文件、启用与停用。")
p("数学/语文解题引导为内置技能。标准文件与原中文字段格式并存，文件由服务器解析和校验，上传文本不作为程序执行。")

page("04  验证一：具体请求参数与模板传递")
p("先给历史探究应用发送问题，再查看后端记录。请求地址为POST "+request["url"]+"，请求体包含model、messages、stream、temperature和max_tokens。")
fig(5,"05-validation1-request.jpg","请求参数及system消息中的模板正文。",max_height=490,url="http://127.0.0.1:8765/01-request.html")
p("本次参数：model=deepseek-flash，stream=true，temperature=0.1，max_tokens=600。首轮messages为system + user，正文字符数分别为445和3312。模板全文与本轮命中技能正文均进入system。","small")
p("对照图3和图5，可以确认模板全文被放入system消息。4次模型请求及返回正文保存在附件20261024-llm-requests.json中。","small")

page("05  验证一：返回正文与SSE结果")
fig(6,"06-validation1-response.jpg","DeepSeek原始正文与应用最终正文，以及SSE和数据库message_id。",max_height=480,url="http://127.0.0.1:8765/02-response.html")
p("首轮实际SSE顺序为meta → "+str(sum(n=="delta" for n,d in first["events"]))+"个delta → done，最终message_id="+str(first["events"][-1][1]["message_id"])+"。验证脚本读取会话数据库返回，断言入库正文等于全部delta顺序拼接。")
p("本例中，DeepSeek返回的正文与页面保存的正文相同。系统另外保留了原始响应，便于检查解题引导等场景中后端是否对回答作了处理。")

page("06  验证二：是否发送全部知识库")
fig(7,"07-validation2-rag.jpg","知识库切片总数与本轮发送的4个片段。",max_height=470,url="http://127.0.0.1:8765/03-knowledge.html")
p("没有发送全部知识库。本次绑定材料共有11个片段，只有检索命中的4个进入请求。检索范围由用户班级、应用绑定材料及Skill资料范围共同限定；关键词和向量结果用RRF融合后取Top4，每片最多800字。")
p("本轮材料ID="+str(meta["citations"][0]["material_id"])+"，发送片段的字符数为"+"、".join(str(len(hit["content"])) for hit in meta["citations"])+"。标题与片段正文位于user材料数据区，不放在system。")

page("07  验证三：Skill是否完整传入")
fig(8,"08-validation3-skill.jpg","上传的SKILL.md与各部分在请求中的用途。",max_height=470,url="http://127.0.0.1:8765/04-skill-content.html")
p("传入的是本轮命中技能的完整Markdown正文，不是整个SKILL.md文件。YAML中的name和description用于标识及路由，不作为文件头整体传入。即使应用绑定多个技能，每轮也最多选择一个。")
p("检查请求可见，解析后保存在skill.description字段的正文逐字出现在system中，而“name: "+flow["skill"]["name"]+"”没有出现。历史探究技能沿用课堂示例的格式，照片中未展示的正文在项目中补充。","small")

page("08  验证四：Skill执行逻辑")
fig(9,"09-validation4-execution.jpg","技能停用前后的请求对照与route_skill源码。",max_height=470,url="http://127.0.0.1:8765/05-skill-execution.html")
p("Skill在这里是一组交给模型的指令，上传文件中的代码不会被执行。服务端先校验会话和班级，读取当前应用绑定且启用的技能，再按关键词评分选出至多一个技能，将正文加入system，随后检索资料、调用模型并保存回答及来源。")
p("最高分为0不选择技能，同分取id较小者。标准description按中文二字词与英文词匹配；原中文格式按适用条件分词匹配。停用后再次问同一句，meta.skill为null，system中不再包含该技能正文。")

page("09  验证五：MCP后的模型请求参数")
fig(10,"10-validation5-tools.jpg","第一轮的tools、tool_choice和模型返回的tool_calls。",max_height=455,url="http://127.0.0.1:8765/06-mcp-request.html")
p("绑定MCP后，请求保留原有model、messages等参数，并增加tools与tool_choice=auto。tools中包含工具名称、说明和参数的JSON Schema。本轮只有calculator，未绑定的current_time没有传给模型。")
p("模型实际请求expression=(127+36)*8。后端对绑定范围、调用轮数和JSON Schema校验后才执行MCP工具，不接受模型请求未绑定工具。")

page("10  验证五：工具执行与第二轮回传")
fig(11,"11-validation5-roundtrip.jpg","MCP返回1304，后端通过role=tool传给模型。",max_height=450,url="http://127.0.0.1:8765/07-mcp-result.html")
p("MCP使用独立stdio进程，依次initialize、initialized、tools/list及tools/call。工具结果通过role=tool放入第二轮DeepSeek请求，tool_call_id与assistant.tool_calls.id一致。")
p("第二轮messages角色顺序为system → user → assistant → tool，模型最终回答明确引用工具结果1304；这两次模型调用的finish_reason分别为tool_calls和stop。")

page("11  学生端问答结果")
fig(12,"12-live-chat-result.jpg","学生端保存的提问和回答，工具计算结果为1304。",crop=(470,210,1490,675),max_height=410,url="http://127.0.0.1:8080/tutor")
p("本次计算会话ID="+str(source["demo_records"]["conversations"][1])+"，锁定计算器应用ID="+str(source["demo_records"]["agents"][1])+"。浏览器截图与前述后台记录中的问题、表达式和答案相互对应。")
p("页面重新打开后仍能查看这条问答。SSE事件和入库正文的一致性另由验证脚本检查；这张静态截图用于展示保存结果。","small")

page("12  验证结果与说明")
table(["验证项","结果","本报告证据"],[
    ("1. 请求、返回与模板","PASS","图3、5、6；完整4次请求与返回JSON"),
    ("2. 知识库发送范围","PASS","图7；11片中仅发送4片"),
    ("3. Skill发送内容","PASS","图8与图5；完整正文注入，头部不整体注入"),
    ("4. Skill执行逻辑","PASS","图9；源码与启停前后实际请求对照"),
    ("5. MCP参数与闭环","PASS","图2、10-12；真实计算与role=tool回传"),
], [170,62,WIDTH-232])
h("结果分析")
p("提示词模板随system传入；知识库只提供检索命中的片段；Skill只注入本轮选中技能的正文；MCP先向模型描述可用工具，工具执行后再把结果作为tool消息回传。五项验证中的请求记录与页面结果一致。")
h("验证范围")
p("本报告重新执行了上述五项模型调用验证。项目此前的回归记录为48项单元测试和31项API测试通过，本次没有重跑完整回归。Docker Compose构建启动、Nginx部署和浏览器实时逐段显示未在本次验证中执行。","small")
h("附件与复现")
p("附件20261024-llm-requests.json包含4次模型请求、返回正文、MCP消息和SSE事件；screenshots-manifest.json记录截图文件及校验值。两份文件均嵌入PDF，也可以从仓库下载。","small")
p("复现时，按README启动MySQL、Qdrant和Flask，在本地配置模型密钥，再执行scripts/verify_platform_live.py（参数--live --keep-demo）。该脚本创建测试材料、模板和技能，完成三轮提问并保存请求记录。","small")
story.append(Paragraph('<link href="https://github.com/Eppiehu/campusclaw-coursework" color="#0C7B77">打开个人项目Git仓库</link>',STYLES["body"]))


def decorate(canvas,doc):
    canvas.setLineWidth(1.5);canvas.setStrokeColor(colors.HexColor("#0C7B77"));canvas.line(44,PH-32,PW-44,PH-32)
    canvas.setFont("ReportCN",8);canvas.setFillColor(colors.HexColor("#6F8290"))
    canvas.drawString(44,24,"CampusClaw | 个人项目阶段性验收报告")
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
