"""Persistent Nexus domain model; PostgreSQL is the production database."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pgvector.sqlalchemy import Vector


def now():
    return datetime.now(timezone.utc)


def week_start(stamp=None):
    from datetime import timedelta
    local=(stamp or now()).astimezone(ZoneInfo('Asia/Shanghai'))
    return (local-timedelta(days=local.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Record, Base):
    __tablename__ = 'users'
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16))
    class_id: Mapped[str] = mapped_column(String(32), index=True)


class RevokedToken(Base):
    __tablename__ = 'revoked_tokens'
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PromptTemplate(Record, Base):
    __tablename__ = 'prompt_templates'
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Skill(Record, Base):
    __tablename__ = 'skills'
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    source_text: Mapped[str] = mapped_column(Text, default='')
    kind: Mapped[str] = mapped_column(String(32), default='custom')
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Agent(Record, Base):
    __tablename__ = 'agents'
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(Text, default='你是教学助手，回答简洁，依据材料并注明来源。')
    template_id: Mapped[int | None] = mapped_column(ForeignKey('prompt_templates.id'))
    material_ids: Mapped[list] = mapped_column(JSON, default=list)
    skill_ids: Mapped[list] = mapped_column(JSON, default=list)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Material(Record, Base):
    __tablename__ = 'materials'
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(200))
    active_version_id: Mapped[int | None] = mapped_column(Integer)


class MaterialVersion(Record, Base):
    __tablename__ = 'material_versions'
    __table_args__ = (UniqueConstraint('material_id', 'number'),)
    material_id: Mapped[int] = mapped_column(ForeignKey('materials.id'))
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    number: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(24), default='draft')
    content: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)


class Chunk(Record, Base):
    __tablename__ = 'chunks'
    __table_args__ = (UniqueConstraint('version_id', 'position'),)
    version_id: Mapped[int] = mapped_column(ForeignKey('material_versions.id'), index=True)
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    position: Mapped[int] = mapped_column(Integer)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text, default='')
    embedding: Mapped[list] = mapped_column(Vector(512))


class KnowledgeGap(Record, Base):
    __tablename__ = 'knowledge_gaps'
    __table_args__ = (UniqueConstraint('class_id', 'fingerprint'),)
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    heat: Mapped[int] = mapped_column(default=1)
    student_ids: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(24), default='pending')
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    version_id: Mapped[int | None] = mapped_column(ForeignKey('material_versions.id'))
    note: Mapped[str] = mapped_column(Text, default='')
    before_hits: Mapped[list] = mapped_column(JSON, default=list)
    after_hits: Mapped[list] = mapped_column(JSON, default=list)


class Conversation(Record, Base):
    __tablename__ = 'conversations'
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    agent_id: Mapped[int] = mapped_column(ForeignKey('agents.id'))
    title: Mapped[str] = mapped_column(String(100), default='新的会话')


class Message(Record, Base):
    __tablename__ = 'messages'
    conversation_id: Mapped[int] = mapped_column(ForeignKey('conversations.id'), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    trace_id: Mapped[str] = mapped_column(String(64))
    skill_id: Mapped[int | None] = mapped_column(ForeignKey('skills.id'))


class Assignment(Record, Base):
    __tablename__ = 'assignments'
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(200))
    question_template: Mapped[str] = mapped_column(Text)
    ranges: Mapped[dict] = mapped_column(JSON)
    answer_expression: Mapped[str] = mapped_column(String(200))
    rubric: Mapped[list] = mapped_column(JSON)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(24), default='draft')


class Paper(Record, Base):
    __tablename__ = 'papers'
    __table_args__ = (UniqueConstraint('assignment_id', 'user_id'),)
    assignment_id: Mapped[int] = mapped_column(ForeignKey('assignments.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    question: Mapped[str] = mapped_column(Text, default='')
    standard_answer: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(24), default='issuing')
    error: Mapped[str | None] = mapped_column(Text)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Submission(Record, Base):
    __tablename__ = 'submissions'
    paper_id: Mapped[int] = mapped_column(ForeignKey('papers.id'), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    answer: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(24), default='queued')
    ai_score: Mapped[float | None] = mapped_column(Float)
    final_score: Mapped[float | None] = mapped_column(Float)
    ai_raw: Mapped[dict] = mapped_column(JSON, default=dict)
    feedback: Mapped[str] = mapped_column(Text, default='')
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    review_note: Mapped[str] = mapped_column(Text, default='')


class WrongQuestion(Record, Base):
    __tablename__ = 'wrong_questions'
    submission_id: Mapped[int] = mapped_column(ForeignKey('submissions.id'), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    explanation: Mapped[str] = mapped_column(Text, default='')


class WeeklyReport(Record, Base):
    __tablename__ = 'weekly_reports'
    __table_args__ = (UniqueConstraint('class_id', 'period_start'),)
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(24), default='queued')
    facts: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_comment: Mapped[str] = mapped_column(Text, default='')
    teacher_comment: Mapped[str] = mapped_column(Text, default='')
    published_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))


class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int] = mapped_column(Integer)
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    state: Mapped[str] = mapped_column(String(24), default='pending')
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Audit(Record, Base):
    __tablename__ = 'audit'
    actor_id: Mapped[int | None] = mapped_column(Integer)
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(100), default='')
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class LearningEvent(Record, Base):
    __tablename__ = 'learning_events'
    class_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    kind: Mapped[str] = mapped_column(String(32))
    resource_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
