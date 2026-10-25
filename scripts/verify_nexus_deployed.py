"""Deployment smoke with a newly bound synthetic lecture and private new conversation."""
import json
import os
from pathlib import Path
import time
import uuid
import httpx


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
    if not args.live:parser.error('--live required for this synthetic-only model smoke')
    client=httpx.Client(base_url=os.environ.get('NEXUS_SMOKE_BASE_URL','http://api:8080')+'/api/nexus',timeout=180,trust_env=False)
    teacher=client.post('/login',json={'username':'teacher_a','password':os.environ['NEXUS_TEACHER_PASSWORD']})
    assert teacher.status_code==200;client.headers['Authorization']='Bearer '+teacher.json()['token']
    result={'checks':[]};tag='部署验收-'+uuid.uuid4().hex[:8]
    def call(method,path,status=200,**kw):
        r=client.request(method,path,**kw);assert r.status_code==status,(path,r.status_code,r.text[:250]);return r
    def wait(identifier):
        for _ in range(150):
            task=next(t for t in call('GET','/tasks').json() if t['id']==identifier)
            if task['state']=='succeeded':return
            if task['state'] in ('failed','dispatch_failed'):raise AssertionError(task['error'])
            time.sleep(1)
        raise TimeoutError('Deployment worker timed out')
    try:
        lecture='本讲义是虚构的教学演示材料。演示弹簧实验编号为NX-SPRING。测量步骤：先记录弹簧原长，再悬挂已知质量的砝码，静止后测量伸长量，最后比较不同载荷的结果。'
        upload=call('POST','/materials',202,data={'title':tag},files={'file':('spring.md',lecture.encode())}).json();wait(upload['task_id'])
        result['checks'].append({'name':'Docker RQ index','status':'PASS'})
        agent=call('POST','/agents',201,json={'name':tag,'prompt':'你是实验讲义助手，只根据本轮材料回答，注明编号。','material_ids':[upload['id']],'tools':[]}).json()
        cid=call('POST','/conversations',201,json={'agent_id':agent['id']}).json()['id']
        frames=[];timing={};start=time.monotonic()
        with client.stream('POST',f'/conversations/{cid}/messages',json={'question':'根据讲义，演示弹簧实验的编号和测量步骤是什么？'}) as response:
            assert response.status_code==200
            for line in response.iter_lines():
                if line.startswith('data:'):
                    event=json.loads(line[5:]);frames.append(event);timing.setdefault(event['event'],round(time.monotonic()-start,3))
        assert frames[-1]['event']=='done' and frames[0]['citations']
        answer=''.join(e['text'] for e in frames if e['event']=='delta')
        assert 'NX-SPRING' in answer and '[1]' in answer
        result['checks'].append({'name':'Docker LangGraph/DeepSeek/SSE','status':'PASS','timing':timing})
        saved=call('GET',f'/conversations/{cid}/messages').json()[-1]
        assert saved['content']==answer and saved['citations'][0]['version_id']==upload['version_id']
        replacement=call('POST',f"/materials/{upload['id']}/versions",202,files={'file':('spring-v2.md',(lecture+'\n新版本补充：每次测量前检查刻度零点。').encode())}).json();wait(replacement['task_id'])
        original=call('GET',f'/conversations/{cid}/messages').json()[-1]
        current=call('POST','/search',json={'query':'弹簧实验测量','agent_id':agent['id']}).json()['hits']
        assert original['citations'][0]['version_id']==upload['version_id'] and current[0]['version_id']==replacement['version_id']
        result['checks'].append({'name':'Atomic activation and historical citation','status':'PASS'})
        call('PATCH','/agents/2147483647',404,json={'name':'missing-resource-check'})
        result.update(agent_id=agent['id'],conversation_id=cid,material_id=upload['id'],answer=answer,citations=original['citations'],tag=tag)
        result['model_audit']=[row for row in call('GET','/audit').json()
                               if row['request_id']==frames[-1]['trace_id'] and row['action'].startswith('llm.')]
    finally:
        client.close();Path('/tmp/nexus-deployed-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
