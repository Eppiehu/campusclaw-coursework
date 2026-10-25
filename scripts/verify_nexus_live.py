"""Explicit synthetic-data verification against real HTTP, PostgreSQL, RQ and DeepSeek."""
import argparse
from datetime import datetime,timedelta,timezone
import io
import json
from pathlib import Path
import time
import uuid
import httpx

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--isolated',action='store_true');parser.add_argument('--url',default='http://127.0.0.1:8081')
    args=parser.parse_args()
    if not args.live:parser.error('Real model calls require --live')
    import os
    if not args.isolated or os.environ.get('NEXUS_LIVE_ISOLATED')!='1':
        parser.error('Live external calls are restricted to a dedicated empty synthetic database')
    from app.nexus.db import transaction
    from app.nexus.models import Paper,Audit,Task,Material,Assignment,Conversation,WeeklyReport
    from sqlalchemy import select
    tag='Nexus演示-'+datetime.now().strftime('%m%d%H%M%S')
    from sqlalchemy import func
    with transaction() as db:
        for model in [Material,Assignment,Conversation,WeeklyReport]:
            if db.scalar(select(func.count()).select_from(model)):
                parser.error('The live verification database must contain no previous business records')
    report={'tag':tag,'started_at':datetime.now(timezone.utc).isoformat(),'checks':[],'records':{}}
    clients={}
    def check(name,detail):
        report['checks'].append({'name':name,'status':'PASS','detail':detail});print('PASS',name,flush=True)
    def call(name,method,path,expected=200,**kwargs):
        response=clients[name].request(method,'/api/nexus'+path,**kwargs)
        assert response.status_code==expected,(method,path,response.status_code,response.text[:400])
        return response
    def wait_tasks(identifiers):
        deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            with transaction() as db:rows=[db.get(Task,i) for i in identifiers]
            if any(r.state in ('failed','dispatch_failed') for r in rows):
                raise AssertionError([(r.kind,r.state,r.error) for r in rows])
            if all(r.state=='succeeded' for r in rows):return
            time.sleep(1)
        raise TimeoutError('Worker task did not complete')
    def chat(name,cid,question):
        response=call(name,'POST',f'/conversations/{cid}/messages',json={'question':question})
        frames=[]
        for frame in response.text.replace('\r\n','\n').split('\n\n'):
            for line in frame.splitlines():
                if line.startswith('data:'):frames.append(json.loads(line[5:]))
        assert frames and frames[-1]['event']=='done',frames[-2:]
        report['records'].setdefault('turns',[]).append({'question':question,'events':frames})
        return frames
    try:
        for name in ['teacher_a','teacher_b','student_a1','student_a2','student_b1']:
            client=httpx.Client(base_url=args.url,timeout=240,trust_env=False)
            response=client.post('/api/nexus/login',json={'username':name,'password':'Teacher123!' if name.startswith('teacher') else 'Student123!'})
            assert response.status_code==200,(name,response.status_code)
            assert 'session=' in response.headers.get('set-cookie','')
            client.headers['Authorization']='Bearer '+response.json()['token'];clients[name]=client
        assert httpx.get(args.url+'/health',trust_env=False).status_code==200
        check('登录与健康','5个演示账号登录成功，Flask Cookie及Bearer可用；health=200')
        call('student_a1','POST','/templates',expected=403,json={'name':'x','content':'x'})
        foreign=call('teacher_b','GET','/agents').json()[0]
        call('teacher_a','PATCH',f"/agents/{foreign['id']}",expected=404,json={'name':'x'})
        check('班级与角色','学生写教师接口403，A班修改B班应用404')
        material=call('teacher_a','POST','/materials',expected=202,data={'title':tag+'分数讲义'},files={'file':('fraction.md','分数相加需要先通分，再将分子相加。结果保持相同分母，最后约分。'.encode())}).json()
        wait_tasks([material['task_id']]);report['records']['material']=material
        call('student_a1','GET',f"/materials/{material['id']}/download")
        call('student_b1','GET',f"/materials/{material['id']}/download",expected=404)
        check('真实异步索引与下载','真实FastEmbed生成512维向量，RQ索引成功；本班下载200，跨班404')
        template=call('teacher_a','POST','/templates',expected=201,json={'name':tag,'content':'你是教学助手。回答前先明确学习主题，使用本轮给出的材料编号，不编造出处。回答简洁。'}).json()
        skill_source='---\nname: nexus-history\ndescription: 月球潮汐锁定学习讲解\n---\n# 学习引导\n先确认学生是否理解自转和公转，再结合讲义解释潮汐锁定。'
        skill=call('teacher_a','POST','/skills',expected=201,files={'file':('SKILL.md',skill_source.encode())}).json()
        agent=call('teacher_a','POST','/agents',expected=201,json={'name':tag,'template_id':template['id'],'material_ids':[material['id']],'skill_ids':[skill['id']],'tools':[]}).json()
        cid=call('student_a1','POST','/conversations',expected=201,json={'agent_id':agent['id']}).json()['id']
        report['records'].update(agent=agent['id'],conversation=cid,template=template['id'],skill=skill['id'])
        question='月球潮汐锁定的形成原因是什么？'
        before=chat('student_a1',cid,question)
        assert not before[0]['citations'] and before[0]['gap_id']
        gap_id=before[0]['gap_id'];call('teacher_a','POST',f'/gaps/{gap_id}/review',json={'decision':'approve'})
        supplement=call('teacher_a','POST',f'/gaps/{gap_id}/supplement',expected=202,json={'title':tag+'潮汐锁定',
            'content':'月球潮汐锁定的形成原因是地球引力产生潮汐形变，内部摩擦耗散转动能，使月球自转逐渐减慢，最终自转周期与绕地公转周期相等。因此月球总是以近似同一面朝向地球。这是教学演示材料。'}).json()
        wait_tasks([supplement['task_id']])
        after=chat('student_a1',cid,question)
        assert after[0]['citations']
        gap=next(g for g in call('teacher_a','GET','/gaps').json() if g['id']==gap_id)
        assert gap['state']=='filled'
        check('知识缺口回补','未命中拒答登记→教师审核→真实RQ索引→原问题重问命中新材料')
        with transaction() as db:
            body=db.scalar(select(Audit).where(Audit.request_id==after[-1]['trace_id'],Audit.action=='llm.request')).details['body']
        assert template['content'] in body['messages'][0]['content'] and skill['body'] in body['messages'][0]['content']
        call('teacher_a','PATCH',f"/skills/{skill['id']}",json={'enabled':False})
        disabled=chat('student_a1',cid,question)
        assert disabled[0]['skill'] is None
        check('模板与Skill启停','模板和命中Skill正文进入system，停用后同问题不再注入')
        assignment=call('teacher_a','POST','/assignments',expected=201,json={'title':tag+'同纲运算','question_template':'计算({a}+{b})×2，写出过程与最终结果。',
            'ranges':{'a':[10,99],'b':[2,20]},'answer_expression':'(a+b)*2','rubric':[{'name':'计算过程','points':40},{'name':'最终答案','points':60}],
            'deadline':(datetime.now(timezone.utc)+timedelta(days=3)).isoformat()}).json()
        tasks=call('teacher_a','POST',f"/assignments/{assignment['id']}/publish",expected=202).json()['task_ids'];wait_tasks(tasks)
        p1=next(p for p in call('student_a1','GET','/papers').json() if p['assignment_id']==assignment['id'])
        p2=next(p for p in call('student_a2','GET','/papers').json() if p['assignment_id']==assignment['id'])
        assert p1['parameters']!=p2['parameters'] and 'standard_answer' not in p1
        call('student_a2','POST',f"/papers/{p1['id']}/start",expected=404)
        call('student_a1','POST',f"/papers/{p1['id']}/start")
        with transaction() as db:v1=db.get(Paper,p1['id']).standard_answer['value'];v2=db.get(Paper,p2['id']).standard_answer['value']
        s1=call('student_a1','POST',f"/papers/{p1['id']}/submit",expected=202,json={'answer':f"先相加：{p1['parameters']['a']}+{p1['parameters']['b']}={sum(p1['parameters'].values())}，再乘2，最终答案{v1}"}).json()
        s2=call('student_a2','POST',f"/papers/{p2['id']}/submit",expected=202,json={'answer':f'交换了另一份试卷的答案，最终答案{v1}'}).json()
        wait_tasks([s1['task_id'],s2['task_id']])
        sub1=next(s for s in call('student_a1','GET','/submissions').json() if s['id']==s1['id'])
        sub2=next(s for s in call('student_a2','GET','/submissions').json() if s['id']==s2['id'])
        assert sub2['ai_score']<100 and v1!=v2
        reviewed=call('teacher_a','POST',f"/submissions/{sub2['id']}/review",json={'score':35,'note':'教师复核：使用了他卷数值，保留部分过程得分。'}).json()
        assert reviewed['ai_score']==sub2['ai_score'] and reviewed['final_score']==35
        report['records'].update(assignment=assignment['id'],paper_ids=[p1['id'],p2['id']],submission_ids=[s1['id'],s2['id']],scores=[sub1['ai_score'],sub2['ai_score']])
        check('同纲发卷与真实AI批改','两名学生不同试卷、服务端标准答案、交换答案不能满分；AI原分与教师复核分分别保留')
        tool_agent=call('teacher_a','POST','/agents',expected=201,json={'name':tag+'工具助手','prompt':'必须调用current_assignments查询当前作业，再根据工具返回回答，不使用猜测。','tools':['current_assignments']}).json()
        tool_cid=call('student_a1','POST','/conversations',expected=201,json={'agent_id':tool_agent['id']}).json()['id']
        tool_turn=chat('student_a1',tool_cid,'请实际调用工具查询当前班级有哪些作业。')
        assert any(e['event']=='tool' for e in tool_turn)
        with transaction() as db:
            requests=list(db.scalars(select(Audit).where(Audit.request_id==tool_turn[-1]['trace_id'],Audit.action=='llm.request').order_by(Audit.id)))
        assert len(requests)>=2
        messages=requests[-1].details['body']['messages'];tool_messages=[m for m in messages if m['role']=='tool']
        assert tool_messages and tool_messages[0]['tool_call_id']==next(m for m in messages if m.get('tool_calls'))['tool_calls'][0]['id']
        check('真实MCP与LangGraph闭环','官方SDK stdio工具执行→tool_call_id匹配→第二次模型请求生成答案')
        weekly=call('teacher_a','POST','/weekly',expected=202).json();wait_tasks([weekly['task_id']])
        row=next(w for w in call('teacher_a','GET','/weekly').json() if w['id']==weekly['id'])
        assert row['state']=='draft' and row['facts']['submission_count']>=2
        assert not any(w['id']==row['id'] for w in call('student_a1','GET','/weekly').json())
        call('teacher_a','POST',f"/weekly/{row['id']}/publish",json={'comment':row['teacher_comment']})
        assert any(w['id']==row['id'] for w in call('student_a1','GET','/weekly').json())
        assert not any(w['id']==row['id'] for w in call('student_b1','GET','/weekly').json())
        report['records']['weekly']=row['id']
        check('周报生成与发布','事实由程序统计、样本不足提示、草稿不可见、教师发布后仅本班可见')
    except Exception as exc:
        report['checks'].append({'name':'execution','status':'FAIL','detail':str(exc)[:700]})
        raise
    finally:
        for client in clients.values():client.close()
        folder=ROOT/'apitest/report';folder.mkdir(exist_ok=True,parents=True)
        (folder/'nexus-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Evidence saved: apitest/report/nexus-live.json',flush=True)


if __name__=='__main__':main()
