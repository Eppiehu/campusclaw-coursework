from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
import uuid
from flask import Blueprint, Response, abort, g, jsonify, request, session, stream_with_context, send_file
from sqlalchemy import select, func
from werkzeug.security import check_password_hash
from .db import transaction, audit
from .security import require, scoped, issue, authenticate
from .models import (User, RevokedToken, PromptTemplate, Skill, Agent, Material, MaterialVersion,
 KnowledgeGap, Conversation, Message, Assignment, Paper, Submission, WrongQuestion, WeeklyReport,
 Task, Audit, LearningEvent, now, week_start)
from .schemas import Login, AssignmentInput
from .jobs import schedule, dispatch, redis_connection, calculate

bp=Blueprint('nexus',__name__,url_prefix='/api/nexus')


def data():
    value=request.get_json(silent=True)
    if not isinstance(value,dict):raise ValueError('请提交JSON对象')
    return value


def output(row,exclude=()):
    return {c.name:(getattr(row,c.name).isoformat() if isinstance(getattr(row,c.name),datetime) else getattr(row,c.name))
            for c in row.__table__.columns if c.name not in exclude}


def text_field(values,name,maximum=4000):
    value=values.get(name)
    if not isinstance(value,str) or not value.strip() or len(value)>maximum:raise ValueError(name+'格式不正确')
    return value.strip()


@bp.post('/login')
def login():
    values=Login.model_validate(data())
    limiter=redis_connection();key='nexus:login:'+hashlib.sha256((request.remote_addr or '').encode()).hexdigest()
    count=limiter.incr(key)
    if count==1:limiter.expire(key,60)
    if count>25:abort(429)
    with transaction() as db:
        user=db.scalar(select(User).where(User.username==values.username))
        if not user or not check_password_hash(user.password_hash,values.password):
            audit(db,user,'login.failed',success=False,request_id=g.request_id)
            return jsonify(error='用户名或密码错误'),401
        # Re-authentication revokes an explicitly supplied previous token.
        previous=request.headers.get('Authorization','').removeprefix('Bearer ')
        if previous:
            try:
                old,claims=authenticate(db,previous)
                if old.id==user.id:db.merge(RevokedToken(jti=claims['jti'],expires_at=datetime.fromtimestamp(claims['exp'],timezone.utc)))
            except PermissionError:pass
        token=issue(user);session.clear();session.update(user_id=user.id,role=user.role,class_id=user.class_id)
        audit(db,user,'login',request_id=g.request_id)
        return jsonify(token=token,user=output(user,('password_hash',)))


@bp.post('/logout')
@require()
def logout():
    with transaction() as db:
        db.merge(RevokedToken(jti=g.claims['jti'],expires_at=datetime.fromtimestamp(g.claims['exp'],timezone.utc)))
        audit(db,g.user,'logout',request_id=g.request_id)
    session.clear();return jsonify(ok=True)


@bp.get('/me')
@require()
def me():return jsonify(output(g.user,('password_hash',)))


@bp.get('/students')
@require('teacher')
def students():
    with transaction() as db:return jsonify([output(u,('password_hash',)) for u in db.scalars(select(User).where(User.class_id==g.user.class_id,User.role=='student'))])


@bp.get('/templates')
@require()
def templates():
    with transaction() as db:return jsonify([output(r) for r in db.scalars(select(PromptTemplate).where(PromptTemplate.class_id==g.user.class_id))])


@bp.post('/templates')
@require('teacher')
def new_template():
    values=data()
    with transaction() as db:
        row=PromptTemplate(class_id=g.user.class_id,name=text_field(values,'name',100),content=text_field(values,'content'))
        db.add(row);db.flush();return jsonify(output(row)),201


@bp.patch('/templates/<int:identifier>')
@require('teacher')
def edit_template(identifier):
    values=data()
    with transaction() as db:
        row=scoped(db,PromptTemplate,identifier,g.user,lock=True)
        for name in ['name','content']:
            if name in values:setattr(row,name,text_field(values,name,100 if name=='name' else 4000))
        if 'enabled' in values:
            if type(values['enabled']) is not bool:raise ValueError('enabled须为布尔值')
            row.enabled=values['enabled']
        return jsonify(output(row))


@bp.get('/skills')
@require()
def skills():
    with transaction() as db:return jsonify([output(r) for r in db.scalars(select(Skill).where(Skill.class_id==g.user.class_id))])


@bp.post('/skills')
@require('teacher')
def upload_skill():
    from app.skill_files import parse_skill
    file=request.files.get('file')
    if not file or not file.filename.lower().endswith(('.md','.txt')):raise ValueError('仅支持TXT或Markdown技能')
    try:parsed=parse_skill(file.read(32001).decode('utf-8-sig'))
    except UnicodeError:raise ValueError('请使用UTF-8编码')
    with transaction() as db:
        row=Skill(class_id=g.user.class_id,name=parsed['name'],description=parsed['trigger_text'],body=parsed['description'],source_text=parsed['source_text'])
        db.add(row);db.flush();audit(db,g.user,'skill.uploaded',row.id,request_id=g.request_id)
        return jsonify(output(row)),201


@bp.patch('/skills/<int:identifier>')
@require('teacher')
def toggle_skill(identifier):
    values=data()
    if type(values.get('enabled')) is not bool:raise ValueError('enabled须为布尔值')
    with transaction() as db:
        row=scoped(db,Skill,identifier,g.user,lock=True);row.enabled=values['enabled']
        audit(db,g.user,'skill.toggled',row.id,{'enabled':row.enabled},request_id=g.request_id)
        return jsonify(output(row))


@bp.get('/agents')
@require()
def agents():
    with transaction() as db:
        query=select(Agent).where(Agent.class_id==g.user.class_id)
        if g.user.role=='student':query=query.where(Agent.enabled==True)
        return jsonify([output(r) for r in db.scalars(query)])


def agent_values(db,row,values):
    if 'name' in values:row.name=text_field(values,'name',100)
    if 'prompt' in values:row.prompt=text_field(values,'prompt')
    if 'enabled' in values:
        if type(values['enabled']) is not bool:raise ValueError('enabled须为布尔值')
        row.enabled=values['enabled']
    if 'template_id' in values:
        if values['template_id'] is not None:scoped(db,PromptTemplate,values['template_id'],g.user)
        row.template_id=values['template_id']
    for key,model in [('material_ids',Material),('skill_ids',Skill)]:
        if key in values:
            if not isinstance(values[key],list) or len(values[key])>50:raise ValueError('绑定数量无效')
            for value in values[key]:scoped(db,model,value,g.user)
            setattr(row,key,list(dict.fromkeys(values[key])))
    if 'tools' in values:
        from .mcp_client import TOOL_NAMES
        if not isinstance(values['tools'],list) or set(values['tools'])-TOOL_NAMES:raise ValueError('工具名称无效')
        row.tools=list(dict.fromkeys(values['tools']))


@bp.post('/agents')
@require('teacher')
def new_agent():
    values=data()
    with transaction() as db:
        row=Agent(class_id=g.user.class_id,name=text_field(values,'name',100));agent_values(db,row,values)
        db.add(row);db.flush();return jsonify(output(row)),201


@bp.patch('/agents/<int:identifier>')
@require('teacher')
def edit_agent(identifier):
    with transaction() as db:
        row=scoped(db,Agent,identifier,g.user,lock=True);agent_values(db,row,data())
        audit(db,g.user,'agent.updated',row.id,request_id=g.request_id);return jsonify(output(row))


@bp.get('/materials')
@require()
def materials():
    with transaction() as db:
        rows=db.scalars(select(Material).where(Material.class_id==g.user.class_id).order_by(Material.id.desc()))
        result=[]
        for row in rows:
            versions=db.scalars(select(MaterialVersion).where(MaterialVersion.material_id==row.id).order_by(MaterialVersion.number.desc())).all()
            if g.user.role=='student' and not row.active_version_id:continue
            value=output(row)
            value['versions']=[output(v,('content',)) for v in versions if g.user.role=='teacher' or v.id==row.active_version_id]
            result.append(value)
        return jsonify(result)


def parse_material():
    file=request.files.get('file')
    if not file:raise ValueError('请选择材料文件')
    value=file.read();name=file.filename.lower()
    if name.endswith('.pdf'):
        from pypdf import PdfReader
        try:
            reader=PdfReader(io.BytesIO(value));content='\n'.join(page.extract_text() or '' for page in reader.pages[:200])
        except Exception:raise ValueError('PDF解析失败')
    elif name.endswith(('.txt','.md')):
        try:content=value.decode('utf-8-sig')
        except UnicodeError:raise ValueError('请上传UTF-8文本')
    else:raise ValueError('仅支持TXT、Markdown和可提取文字的PDF')
    if not content.strip() or len(content)>500000:raise ValueError('材料为空或正文超过50万字')
    return content


def add_version(db,material,content):
    number=(db.scalar(select(func.max(MaterialVersion.number)).where(MaterialVersion.material_id==material.id)) or 0)+1
    row=MaterialVersion(material_id=material.id,class_id=material.class_id,number=number,content=content,
                         sha256=hashlib.sha256(content.encode()).hexdigest(),state='indexing')
    db.add(row);db.flush();return row


@bp.post('/materials')
@require('teacher')
def upload_material():
    content=parse_material();title=request.form.get('title','').strip()
    if not title or len(title)>200:raise ValueError('请填写材料标题')
    with transaction() as db:
        row=Material(class_id=g.user.class_id,owner_id=g.user.id,title=title);db.add(row);db.flush()
        version=add_version(db,row,content);identifier=row.id;version_id=version.id
        audit(db,g.user,'material.uploaded',identifier,request_id=g.request_id)
    task=schedule('index',version_id,g.user.class_id)
    return jsonify(id=identifier,version_id=version_id,task_id=task),202


@bp.post('/materials/<int:identifier>/versions')
@require('teacher')
def replace_material(identifier):
    content=parse_material()
    with transaction() as db:
        row=scoped(db,Material,identifier,g.user,lock=True);version=add_version(db,row,content);version_id=version.id
    return jsonify(version_id=version_id,task_id=schedule('index',version_id,g.user.class_id)),202


@bp.get('/materials/<int:identifier>/download')
@require()
def download(identifier):
    with transaction() as db:
        row=scoped(db,Material,identifier,g.user)
        version=db.get(MaterialVersion,row.active_version_id) if row.active_version_id else None
        if not version or version.state!='active':abort(404)
        db.add(LearningEvent(user_id=g.user.id,class_id=g.user.class_id,kind='material_view',resource_id=identifier))
        return send_file(io.BytesIO(version.content.encode()),mimetype='text/plain; charset=utf-8',as_attachment=True,download_name=f'material-{identifier}.txt')


@bp.post('/materials/<int:identifier>/withdraw')
@require('teacher')
def withdraw(identifier):
    with transaction() as db:
        row=scoped(db,Material,identifier,g.user,lock=True)
        for version in db.scalars(select(MaterialVersion).where(MaterialVersion.material_id==identifier)):
            version.state='withdrawn'
        row.active_version_id=None;audit(db,g.user,'material.withdrawn',row.id,request_id=g.request_id)
    return jsonify(ok=True)


@bp.post('/search')
@require()
def search():
    from .retrieval import search as retrieve
    values=data();question=text_field(values,'query',1000)
    with transaction() as db:
        agent=scoped(db,Agent,values.get('agent_id'),g.user)
        return jsonify(hits=retrieve(db,g.user,question,agent.material_ids))


@bp.get('/gaps')
@require('teacher')
def gaps():
    with transaction() as db:return jsonify([output(r) for r in db.scalars(select(KnowledgeGap).where(KnowledgeGap.class_id==g.user.class_id).order_by(KnowledgeGap.heat.desc()))])


@bp.post('/gaps/<int:identifier>/review')
@require('teacher')
def review_gap(identifier):
    values=data();decision=values.get('decision')
    if decision not in ('approve','reject'):raise ValueError('请选择通过或驳回')
    with transaction() as db:
        gap=scoped(db,KnowledgeGap,identifier,g.user,lock=True)
        if gap.state not in ('pending','approved','index_failed'):abort(409)
        gap.teacher_id=g.user.id;gap.note=str(values.get('note',''))[:2000]
        if decision=='reject':gap.state='rejected';return jsonify(output(gap))
        gap.state='approved'
        audit(db,g.user,'gap.approved',gap.id,request_id=g.request_id)
        return jsonify(output(gap))


@bp.post('/gaps/<int:identifier>/supplement')
@require('teacher')
def supplement(identifier):
    values=data();content=text_field(values,'content',50000)
    with transaction() as db:
        gap=scoped(db,KnowledgeGap,identifier,g.user,lock=True)
        if gap.state not in ('approved','index_failed'):abort(409)
        row=Material(class_id=g.user.class_id,owner_id=g.user.id,title=text_field(values,'title',200));db.add(row);db.flush()
        version=add_version(db,row,content);gap.version_id=version.id;gap.teacher_id=g.user.id;gap.state='indexing'
        # The teacher explicitly adds the supplemental lecture to this class's assistants.
        for agent in db.scalars(select(Agent).where(Agent.class_id==g.user.class_id)):
            agent.material_ids=list(dict.fromkeys(agent.material_ids+[row.id]))
        version_id=version.id
        audit(db,g.user,'gap.supplemented',gap.id,{'material_id':row.id},request_id=g.request_id)
    return jsonify(task_id=schedule('index',version_id,g.user.class_id)),202


@bp.get('/conversations')
@require()
def conversations():
    with transaction() as db:return jsonify([output(r) for r in db.scalars(select(Conversation).where(Conversation.class_id==g.user.class_id,Conversation.user_id==g.user.id).order_by(Conversation.id.desc()))])


@bp.post('/conversations')
@require()
def new_conversation():
    values=data()
    with transaction() as db:
        agent=scoped(db,Agent,values.get('agent_id'),g.user)
        if not agent.enabled:abort(409)
        row=Conversation(user_id=g.user.id,class_id=g.user.class_id,agent_id=agent.id);db.add(row);db.flush()
        return jsonify(output(row)),201


@bp.get('/conversations/<int:identifier>/messages')
@require()
def messages(identifier):
    with transaction() as db:
        scoped(db,Conversation,identifier,g.user,owner=True)
        return jsonify([output(r) for r in db.scalars(select(Message).where(Message.conversation_id==identifier).order_by(Message.id))])


@bp.post('/conversations/<int:identifier>/messages')
@require()
def send(identifier):
    from .agent import stream
    question=text_field(data(),'question',4000)
    with transaction() as db:
        conversation=scoped(db,Conversation,identifier,g.user,owner=True);agent_id=conversation.agent_id
    # One active generation per conversation; expiry protects against killed HTTP workers.
    lock=redis_connection().lock(f'nexus:conversation:{identifier}',timeout=360,blocking_timeout=0)
    if not lock.acquire(blocking=False):abort(409)
    capacity=redis_connection().lock('nexus:agent-capacity',timeout=360,blocking_timeout=0)
    if not capacity.acquire(blocking=False):
        lock.release();abort(429)
    user_id,token,trace_id=g.user.id,g.token,g.request_id
    def generate():
        try:yield from stream(question,user_id,agent_id,identifier,token,trace_id)
        finally:
            try:lock.release()
            except Exception:pass
            try:capacity.release()
            except Exception:pass
    return Response(stream_with_context(generate()),mimetype='text/event-stream',headers={'X-Accel-Buffering':'no','Cache-Control':'no-cache'})


@bp.get('/assignments')
@require()
def assignments():
    with transaction() as db:
        query=select(Assignment).where(Assignment.class_id==g.user.class_id)
        if g.user.role=='student':query=query.where(Assignment.state!='draft')
        return jsonify([output(r,('answer_expression',)) for r in db.scalars(query.order_by(Assignment.id.desc()))])


@bp.post('/assignments')
@require('teacher')
def create_assignment():
    values=AssignmentInput.model_validate(data());payload=values.model_dump();deadline=datetime.fromisoformat(payload.pop('deadline').replace('Z','+00:00'))
    if deadline.tzinfo is None or deadline<=now():raise ValueError('截止时间须为带时区的未来时间')
    calculate(values.answer_expression,{k:v[0] for k,v in values.ranges.items()})
    try:values.question_template.format(**{k:v[0] for k,v in values.ranges.items()})
    except (KeyError,ValueError):raise ValueError('题干参数与范围不匹配')
    with transaction() as db:
        row=Assignment(class_id=g.user.class_id,teacher_id=g.user.id,deadline=deadline,**payload)
        db.add(row);db.flush();return jsonify(output(row,('answer_expression',))),201


@bp.post('/assignments/<int:identifier>/publish')
@require('teacher')
def publish_assignment(identifier):
    pending=[]
    with transaction() as db:
        assignment=scoped(db,Assignment,identifier,g.user,lock=True)
        if assignment.deadline<=now():abort(409)
        for user in db.scalars(select(User).where(User.class_id==g.user.class_id,User.role=='student')):
            paper=db.scalar(select(Paper).where(Paper.assignment_id==identifier,Paper.user_id==user.id))
            if not paper:
                paper=Paper(assignment_id=identifier,user_id=user.id,class_id=user.class_id);db.add(paper);db.flush();pending.append(paper.id)
        assignment.state='published';audit(db,g.user,'assignment.published',identifier,request_id=g.request_id)
    return jsonify(task_ids=[schedule('issue',pid,g.user.class_id) for pid in pending]),202


@bp.get('/papers')
@require()
def papers():
    with transaction() as db:
        query=select(Paper).where(Paper.class_id==g.user.class_id)
        if g.user.role=='student':query=query.where(Paper.user_id==g.user.id)
        return jsonify([output(r,('standard_answer',)) for r in db.scalars(query.order_by(Paper.id.desc()))])


@bp.post('/papers/<int:identifier>/start')
@require('student')
def start_paper(identifier):
    with transaction() as db:
        row=scoped(db,Paper,identifier,g.user,owner=True,lock=True)
        if row.state not in ('ready','frozen'):abort(409)
        if db.get(Assignment,row.assignment_id).deadline<=now():abort(409)
        row.state='frozen';row.frozen_at=row.frozen_at or now()
        return jsonify(output(row,('standard_answer',)))


@bp.post('/papers/<int:identifier>/submit')
@require('student')
def submit(identifier):
    answer=text_field(data(),'answer',12000)
    with transaction() as db:
        row=scoped(db,Paper,identifier,g.user,owner=True,lock=True)
        if row.state not in ('ready','frozen'):abort(409)
        if db.get(Assignment,row.assignment_id).deadline<=now():abort(409)
        row.state='submitted';row.frozen_at=row.frozen_at or now()
        sub=Submission(paper_id=row.id,user_id=g.user.id,class_id=g.user.class_id,answer=answer)
        db.add(sub);db.flush();sid=sub.id
        audit(db,g.user,'submission.created',sid,request_id=g.request_id)
    return jsonify(id=sid,task_id=schedule('grade',sid,g.user.class_id)),202


@bp.get('/submissions')
@require()
def submissions():
    with transaction() as db:
        query=select(Submission).where(Submission.class_id==g.user.class_id)
        if g.user.role=='student':query=query.where(Submission.user_id==g.user.id)
        return jsonify([output(r) for r in db.scalars(query.order_by(Submission.id.desc()))])


@bp.post('/submissions/<int:identifier>/review')
@require('teacher')
def review_grade(identifier):
    values=data();score=values.get('score')
    if type(score) not in (int,float) or not 0<=score<=100:raise ValueError('分数须为0至100')
    note=text_field(values,'note',2000)
    with transaction() as db:
        row=scoped(db,Submission,identifier,g.user,lock=True)
        if row.state not in ('graded','reviewed'):abort(409)
        row.final_score=score;row.reviewed_by=g.user.id;row.review_note=note;row.state='reviewed'
        wrong=db.scalar(select(WrongQuestion).where(WrongQuestion.submission_id==row.id))
        if score<100 and not wrong:db.add(WrongQuestion(submission_id=row.id,user_id=row.user_id,class_id=row.class_id,explanation=row.feedback))
        if score==100 and wrong:db.delete(wrong)
        audit(db,g.user,'submission.reviewed',row.id,{'ai_score':row.ai_score,'final_score':score,'note':note},request_id=g.request_id)
        return jsonify(output(row))


@bp.get('/wrong-questions')
@require()
def wrong_questions():
    with transaction() as db:
        query=select(WrongQuestion).where(WrongQuestion.class_id==g.user.class_id)
        if g.user.role=='student':query=query.where(WrongQuestion.user_id==g.user.id)
        return jsonify([output(r) for r in db.scalars(query)])


@bp.get('/weekly')
@require()
def weeklies():
    with transaction() as db:
        query=select(WeeklyReport).where(WeeklyReport.class_id==g.user.class_id)
        if g.user.role=='student':query=query.where(WeeklyReport.state=='published')
        return jsonify([output(r) for r in db.scalars(query.order_by(WeeklyReport.id.desc()))])


@bp.post('/weekly')
@require('teacher')
def new_weekly():
    start=week_start()
    with transaction() as db:
        if db.scalar(select(WeeklyReport).where(WeeklyReport.class_id==g.user.class_id,WeeklyReport.period_start==start)):abort(409)
        row=WeeklyReport(class_id=g.user.class_id,period_start=start);db.add(row);db.flush();identifier=row.id
    return jsonify(id=identifier,task_id=schedule('weekly',identifier,g.user.class_id)),202


@bp.post('/weekly/<int:identifier>/publish')
@require('teacher')
def publish_weekly(identifier):
    values=data()
    with transaction() as db:
        row=scoped(db,WeeklyReport,identifier,g.user,lock=True)
        if row.state!='draft':abort(409)
        row.teacher_comment=text_field(values,'comment',5000);row.state='published';row.published_by=g.user.id
        audit(db,g.user,'weekly.published',row.id,request_id=g.request_id);return jsonify(output(row))


@bp.get('/tasks')
@require('teacher')
def tasks():
    with transaction() as db:return jsonify([output(r) for r in db.scalars(select(Task).where(Task.class_id==g.user.class_id).order_by(Task.created_at.desc()).limit(100))])


@bp.post('/tasks/<identifier>/retry')
@require('teacher')
def retry(identifier):
    with transaction() as db:
        row=db.get(Task,identifier)
        if not row or row.class_id!=g.user.class_id:abort(404)
        if row.state not in ('failed','dispatch_failed'):abort(409)
        if row.kind=='index':
            for gap in db.scalars(select(KnowledgeGap).where(KnowledgeGap.version_id==row.target_id,KnowledgeGap.state=='index_failed')):gap.state='indexing'
        audit(db,g.user,'task.retried',identifier,request_id=g.request_id)
    dispatch(identifier);return jsonify(ok=True),202


@bp.get('/audit')
@require('teacher')
def audits():
    with transaction() as db:
        query=select(Audit).where(Audit.class_id==g.user.class_id).order_by(Audit.id.desc()).limit(100)
        return jsonify([output(r) for r in db.scalars(query)])
