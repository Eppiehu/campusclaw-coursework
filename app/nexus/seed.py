import os
from sqlalchemy import select
from werkzeug.security import generate_password_hash
from .db import transaction
from .models import User, PromptTemplate, Skill, Agent

BUILTINS = [
    ('解题引导','guide','解题,引导,数学,计算,方程','先询问学生的思路，只给下一步提示，不直接给出最终答案。引用已有材料，无法确认时说明限制。'),
    ('Rubric批改','grading','批改,评分,作业','依据当前作业Rubric逐项检查，指出得分依据和遗漏。只使用工具返回的标准，不编造分数。'),
    ('错题讲解','explain','错题,错因,讲解','先检查学生自己的错题记录，指出错误步骤，给出一条练习建议；不得读取其他学生的记录。'),
]


def seed():
    with transaction() as db:
        for name, role, klass in [('teacher_a','teacher','A'),('teacher_b','teacher','B'),
                                  ('student_a1','student','A'),('student_a2','student','A'),('student_b1','student','B')]:
            if not db.scalar(select(User).where(User.username==name)):
                password = os.environ.get('NEXUS_TEACHER_PASSWORD' if role=='teacher' else 'NEXUS_STUDENT_PASSWORD')
                if not password or len(password)<10:
                    raise ValueError('Seed passwords must be configured with at least 10 characters')
                db.add(User(username=name,password_hash=generate_password_hash(password),role=role,class_id=klass))
        db.flush()
        for klass in ['A','B']:
            template = db.scalar(select(PromptTemplate).where(PromptTemplate.class_id==klass))
            if not template:
                template=PromptTemplate(class_id=klass,name='课堂学习模板',content='你是本班教学助手。先澄清问题，再根据已提供的证据引导学习。资料不足时明确说明，不编造出处。')
                db.add(template);db.flush()
            skills=[]
            for name,kind,description,body in BUILTINS:
                skill=db.scalar(select(Skill).where(Skill.class_id==klass,Skill.kind==kind))
                if not skill:
                    skill=Skill(class_id=klass,name=name,kind=kind,description=description,body=body)
                    db.add(skill);db.flush()
                skills.append(skill.id)
            for name,tools in [('数学学习助手',['lecture_search','my_wrong_questions','assignment_rubric']),
                                ('语文阅读助手',['lecture_search','current_assignments']),
                                ('学习分析助手',['lecture_search','class_statistics'])]:
                if not db.scalar(select(Agent).where(Agent.class_id==klass,Agent.name==name)):
                    db.add(Agent(class_id=klass,name=name,template_id=template.id,skill_ids=skills,tools=tools))
