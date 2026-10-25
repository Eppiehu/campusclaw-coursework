from datetime import datetime,timezone
import json
from app.nexus.models import week_start
from app.nexus import llm
from conftest import upload


def test_week_boundary_is_monday_beijing():
    monday=week_start(datetime(2026,10,18,18,0,tzinfo=timezone.utc))
    assert monday.isoformat()=='2026-10-19T00:00:00+08:00'


def test_model_sees_citation_labels_not_database_ids(system,monkeypatch):
    request,run,_=system
    material=upload(request);run()
    agent=request('teacher_a','GET','/agents').json[0]
    request('teacher_a','PATCH',f"/agents/{agent['id']}",json={'material_ids':[material['id']],'tools':[]})
    seen=[]
    def model(messages,actor,trace,emit=None,**kwargs):
        seen.append(json.loads(messages[-1]['content']))
        if emit:emit({'event':'delta','text':'应先通分。[1]'})
        return {'role':'assistant','content':'应先通分。[1]'}
    monkeypatch.setattr(llm,'call',model)
    cid=request('student_a1','POST','/conversations',json={'agent_id':agent['id']}).json['id']
    reply=request('student_a1','POST',f'/conversations/{cid}/messages',json={'question':'分数相加如何通分'})
    assert 'event: done' in reply.text
    assert seen[0]['sources'][0]['citation']=='[1]'
    assert all('material_id' not in h and 'chunk_id' not in h for h in seen[0]['sources'])
