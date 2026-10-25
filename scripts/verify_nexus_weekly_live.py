"""Exercise the sufficient-sample LLM summary using new, labeled synthetic grades."""
from datetime import timedelta
import json
import os
from pathlib import Path
import time
import uuid
from dotenv import load_dotenv
from sqlalchemy import select
from werkzeug.security import generate_password_hash

ROOT=Path(__file__).resolve().parents[1]


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
    if not args.live:parser.error('--live required')
    load_dotenv(ROOT/'.env.nexus-live2.local',override=True)
    if os.environ.get('NEXUS_LIVE_ISOLATED')!='1' or not os.environ['NEXUS_DATABASE_URL'].endswith('/campusclaw_nexus_live2'):
        parser.error('Use the isolated synthetic-only database')
    from app.nexus.db import transaction
    from app.nexus.models import User,Assignment,Paper,Submission,WeeklyReport,Task,Audit,now
    from app.nexus.jobs import schedule
    tag='weekly-fixture-'+uuid.uuid4().hex[:10]
    scores=[75,90,40,80,66,100]
    stamp=now();start=(stamp-timedelta(days=stamp.weekday())).replace(hour=0,minute=0,second=0,microsecond=0)
    with transaction() as db:
        teacher=User(username=tag,role='teacher',class_id=tag,password_hash=generate_password_hash(uuid.uuid4().hex));db.add(teacher);db.flush()
        students=[]
        for i in range(3):
            user=User(username=tag+'-'+str(i),role='student',class_id=tag,password_hash=generate_password_hash(uuid.uuid4().hex));db.add(user);db.flush();students.append(user)
        for i,score in enumerate(scores):
            assignment=Assignment(class_id=tag,teacher_id=teacher.id,title='虚构人工评分样本',question_template='演示题',ranges={'a':[1,2]},answer_expression='a',rubric=[{'name':'演示','points':100}],deadline=now()+timedelta(days=1),state='published');db.add(assignment);db.flush()
            student=students[i%3]
            paper=Paper(assignment_id=assignment.id,class_id=tag,user_id=student.id,state='submitted',question='周报分支演示题',standard_answer={'value':1});db.add(paper);db.flush()
            # These are explicitly synthetic teacher-reviewed fixtures, not AI grades.
            db.add(Submission(paper_id=paper.id,user_id=student.id,class_id=tag,answer='虚构答案',state='reviewed',final_score=score,
                              reviewed_by=teacher.id,review_note='周报分支测试的虚构人工评分，非AI批改结果'))
        report=WeeklyReport(class_id=tag,period_start=start);db.add(report);db.flush();identifier=report.id
    task_id=schedule('weekly',identifier,tag)
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        with transaction() as db:task=db.get(Task,task_id)
        if task.state=='failed':raise AssertionError(task.error)
        if task.state=='succeeded':break
        time.sleep(1)
    else:raise TimeoutError('Weekly worker timed out')
    with transaction() as db:
        report=db.get(WeeklyReport,identifier)
        assert report.state=='draft' and report.facts['sample_sufficient']
        assert report.facts['student_count']==3 and report.facts['submission_count']==6
        assert report.facts['average_score']==round(sum(scores)/6,2)
        requests=list(db.scalars(select(Audit).where(Audit.request_id==task_id,Audit.action=='llm.request')))
        assert len(requests)==1
        result={'status':'PASS','fixture':'new isolated class with synthetic manually reviewed grades; not claimed as AI grades',
                'facts':report.facts,'ai_comment':report.ai_comment,'model_request':requests[0].details['body']}
    (ROOT/'apitest/report/nexus-weekly-live.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS sufficient-sample weekly LLM summary; program facts verified')


if __name__=='__main__':main()
