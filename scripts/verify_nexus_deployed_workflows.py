"""Create fresh demo papers and verify Docker grading and an explicitly scoped MCP call."""
from datetime import datetime,timedelta,timezone
import argparse
import json
import os
import time
import uuid
import httpx


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
    if not args.live:parser.error('--live required')
    url=os.environ.get('NEXUS_SMOKE_BASE_URL','http://api:8080')+'/api/nexus'
    clients={};result={'checks':[]};tag='Docker同纲演示-'+uuid.uuid4().hex[:6]
    for name in ['teacher_a','student_a1','student_a2']:
        client=httpx.Client(base_url=url,timeout=180,trust_env=False)
        response=client.post('/login',json={'username':name,'password':os.environ['NEXUS_TEACHER_PASSWORD' if name.startswith('teacher') else 'NEXUS_STUDENT_PASSWORD']})
        assert response.status_code==200
        client.headers['Authorization']='Bearer '+response.json()['token'];clients[name]=client
    def call(who,method,path,status=200,**kwargs):
        response=clients[who].request(method,path,**kwargs)
        assert response.status_code==status,(path,response.status_code,response.text[:300])
        return response
    def wait(identifiers):
        for _ in range(180):
            tasks=[t for t in call('teacher_a','GET','/tasks').json() if t['id'] in identifiers]
            if any(t['state'] in ('failed','dispatch_failed') for t in tasks):raise AssertionError([(t['state'],t['error']) for t in tasks])
            if len(tasks)==len(identifiers) and all(t['state']=='succeeded' for t in tasks):return
            time.sleep(1)
        raise TimeoutError('Tasks did not finish')
    try:
        assignment=call('teacher_a','POST','/assignments',201,json={'title':tag,'question_template':'计算({a}+{b})×2，写出步骤与最终结果。',
              'ranges':{'a':[10,99],'b':[2,20]},'answer_expression':'(a+b)*2',
              'rubric':[{'name':'计算过程','points':40},{'name':'最终答案','points':60}],
              'deadline':(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()}).json()
        wait(call('teacher_a','POST',f"/assignments/{assignment['id']}/publish",202).json()['task_ids'])
        papers=[next(p for p in call(name,'GET','/papers').json() if p['assignment_id']==assignment['id']) for name in ['student_a1','student_a2']]
        assert papers[0]['parameters']!=papers[1]['parameters'] and all('standard_answer' not in p for p in papers)
        tasks=[];submissions=[]
        for i,name in enumerate(['student_a1','student_a2']):
            p=papers[i];call(name,'POST',f"/papers/{p['id']}/start")
            a,b=p['parameters']['a'],p['parameters']['b']
            answer=f'先相加得到{a+b}，再乘2，最终答案{(a+b)*2}' if i==0 else '这是虚构错误答案，最终答案0'
            sub=call(name,'POST',f"/papers/{p['id']}/submit",202,json={'answer':answer}).json();submissions.append(sub['id']);tasks.append(sub['task_id'])
        wait(tasks)
        grades=[next(s for s in call(name,'GET','/submissions').json() if s['id']==sid) for name,sid in zip(['student_a1','student_a2'],submissions)]
        assert grades[1]['ai_score']<100
        reviewed=call('teacher_a','POST',f"/submissions/{submissions[1]}/review",json={'score':30,'note':'虚构演示的教师复核：最终数值错误，保留部分过程分。'}).json()
        assert reviewed['ai_score']==grades[1]['ai_score'] and reviewed['final_score']==30
        result['checks'].append({'name':'Docker unique papers, real AI grading and review','status':'PASS','scores':[g['ai_score'] for g in grades]})
        # Bind only a rubric tool with this newly created assignment ID. No list of
        # existing assignments, student histories or existing statistics is sent.
        agent=call('teacher_a','POST','/agents',201,json={'name':tag+'评分规则助手','tools':['assignment_rubric'],
            'prompt':f"必须实际调用assignment_rubric，参数assignment_id={assignment['id']}，然后仅根据工具结果解释评分标准。"}).json()
        cid=call('student_a1','POST','/conversations',201,json={'agent_id':agent['id']}).json()['id']
        response=call('student_a1','POST',f'/conversations/{cid}/messages',json={'question':f"请调用工具查询作业{assignment['id']}的评分规则。"})
        frames=[json.loads(line[5:]) for line in response.text.splitlines() if line.startswith('data:')]
        assert frames[-1]['event']=='done' and any(e['event']=='tool' for e in frames)
        result['checks'].append({'name':'Docker MCP SDK and LangGraph tool roundtrip','status':'PASS'})
        result.update(assignment_id=assignment['id'],paper_ids=[p['id'] for p in papers],submission_ids=submissions,
                      tool_events=frames,tag=tag)
    finally:
        for client in clients.values():client.close()
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
