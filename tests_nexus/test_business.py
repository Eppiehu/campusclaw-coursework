from datetime import timedelta
import io
import json
import pytest
from sqlalchemy import select
from app.nexus.db import transaction
from app.nexus.models import *
from app.nexus.jobs import calculate
from app.nexus import llm
from app.nexus.schemas import Grade
from conftest import upload


def assignment(request,**changes):
    payload=dict(title='同纲运算',question_template='计算{a}+{b}',ranges={'a':[10,99],'b':[2,20]},
                 answer_expression='a+b',rubric=[{'name':'过程','points':40},{'name':'答案','points':60}],deadline=(now()+timedelta(days=2)).isoformat())
    payload.update(changes)
    result=request('teacher_a','POST','/assignments',json=payload)
    assert result.status_code==201,result.json
    return result.json


def mock_grade(monkeypatch):
    def structured(prompt,payload,model,actor,trace):
        return Grade.model_validate({'items':[{'criterion':r['name'],'score':r['points'],'reason':'按项目规则核对'} for r in payload['rubric']],
                                     'feedback':'检查计算过程和最终结果。'})
    monkeypatch.setattr(llm,'structured',structured)


def test_authentication_and_revocation(system):
    request,_,app=system
    assert app.test_client().get('/api/nexus/agents').status_code==401
    assert app.test_client().post('/api/nexus/login',json={'username':'teacher_a','password':'bad'}).status_code==401
    assert request('student_a1','POST','/templates',json={'name':'x','content':'x'}).status_code==403
    assert request('teacher_a','POST','/logout').status_code==200
    assert request('teacher_a','GET','/agents').status_code==401


def test_class_and_binding_isolation(system):
    request,_,_=system
    foreign=request('teacher_b','GET','/agents').json[0]
    own=request('teacher_a','GET','/agents').json[0]
    assert request('teacher_a','PATCH',f"/agents/{foreign['id']}",json={'name':'x'}).status_code==404
    template=request('teacher_b','GET','/templates').json[0]
    assert request('teacher_a','PATCH',f"/agents/{own['id']}",json={'template_id':template['id']}).status_code==404
    assert all(a['class_id']=='A' for a in request('student_a1','GET','/agents').json)


def test_material_index_download_and_snapshot(system):
    request,run,_=system
    material=upload(request);run()
    rows=request('teacher_a','GET','/materials').json
    assert rows[0]['active_version_id']==material['version_id']
    assert request('student_a1','GET',f"/materials/{material['id']}/download").status_code==200
    assert request('student_b1','GET',f"/materials/{material['id']}/download").status_code==404
    assert request('student_a1','POST','/materials',data={'title':'x','file':(io.BytesIO(b'x'),'x.txt')}).status_code==403
    agent=request('teacher_a','GET','/agents').json[0]
    request('teacher_a','PATCH',f"/agents/{agent['id']}",json={'material_ids':[material['id']]})
    hits=request('student_a1','POST','/search',json={'query':'分数相加通分','agent_id':agent['id']}).json['hits']
    assert hits and hits[0]['version_id']==material['version_id']
    snapshot=hits[0].copy()
    response=request('teacher_a','POST',f"/materials/{material['id']}/versions",data={'file':(io.BytesIO('分数相减同样先通分。'.encode()),'v2.md')})
    assert response.status_code==202
    assert request('teacher_a','GET','/materials').json[0]['active_version_id']==material['version_id']
    run()
    assert request('teacher_a','GET','/materials').json[0]['active_version_id']==response.json['version_id']
    assert snapshot['content']=='分数相加需要先通分，再把分子相加。分母保持不变。'
    assert snapshot['sha256']!=request('teacher_a','GET','/materials').json[0]['versions'][0]['sha256']


def test_failed_index_preserves_active_version(system,monkeypatch):
    request,run,_=system
    material=upload(request);run()
    result=request('teacher_a','POST',f"/materials/{material['id']}/versions",data={'file':(io.BytesIO('更新材料'.encode()),'v2.md')})
    from app.nexus import retrieval
    monkeypatch.setattr(retrieval,'embed',lambda value:(_ for _ in ()).throw(RuntimeError('embedding unavailable')))
    run()
    row=request('teacher_a','GET','/materials').json[0]
    assert row['active_version_id']==material['version_id']
    assert row['versions'][0]['state']=='index_failed'


def test_gap_refusal_merge_review_and_fill(system):
    request,run,_=system
    agent=request('teacher_a','GET','/agents').json[0]
    cid=request('student_a1','POST','/conversations',json={'agent_id':agent['id']}).json['id']
    for _ in range(2):
        reply=request('student_a1','POST',f'/conversations/{cid}/messages',json={'question':'月球潮汐锁定的形成原因是什么'})
        assert reply.status_code==200 and '候选知识缺口' in reply.text and 'event: done' in reply.text
    gaps=request('teacher_a','GET','/gaps').json
    assert len(gaps)==1 and gaps[0]['heat']==2
    gap=gaps[0]
    assert request('teacher_b','POST',f"/gaps/{gap['id']}/review",json={'decision':'approve'}).status_code==404
    assert request('teacher_a','POST',f"/gaps/{gap['id']}/supplement",json={'title':'x','content':'x'}).status_code==409
    request('teacher_a','POST',f"/gaps/{gap['id']}/review",json={'decision':'approve'})
    result=request('teacher_a','POST',f"/gaps/{gap['id']}/supplement",json={'title':'潮汐锁定','content':'月球潮汐锁定的形成原因：地球引力造成潮汐形变，耗散转动能，最终自转与公转周期相同。'})
    assert result.status_code==202
    assert request('teacher_a','GET','/gaps').json[0]['state']=='indexing'
    run()
    gap=request('teacher_a','GET','/gaps').json[0]
    assert gap['state']=='filled' and gap['after_hits'] and gap['before_hits']==[]


def test_unique_papers_no_answer_leak_and_freeze(system):
    request,run,_=system
    a=assignment(request)
    assert 'answer_expression' not in a
    request('teacher_a','POST',f"/assignments/{a['id']}/publish");run()
    p1=request('student_a1','GET','/papers').json[0];p2=request('student_a2','GET','/papers').json[0]
    assert p1['state']=='ready' and p2['state']=='ready'
    assert p1['parameters']!=p2['parameters'] and 'standard_answer' not in p1
    assert request('student_a2','POST',f"/papers/{p1['id']}/start").status_code==404
    assert request('student_b1','POST',f"/papers/{p1['id']}/start").status_code==404
    start=request('student_a1','POST',f"/papers/{p1['id']}/start").json
    assert start['state']=='frozen' and start['frozen_at']
    assert request('student_a1','POST',f"/papers/{p1['id']}/start").json['question']==start['question']


def test_one_paper_failure_does_not_rollback_others(system):
    request,run,_=system
    a=assignment(request,ranges={'a':[1,1],'b':[1,1]})
    request('teacher_a','POST',f"/assignments/{a['id']}/publish");run()
    papers=request('teacher_a','GET','/papers').json
    assert sorted(p['state'] for p in papers)==['issue_failed','ready']


def test_grading_exchange_guard_and_review(system,monkeypatch):
    request,run,_=system;mock_grade(monkeypatch)
    a=assignment(request);request('teacher_a','POST',f"/assignments/{a['id']}/publish");run()
    p1=request('student_a1','GET','/papers').json[0];p2=request('student_a2','GET','/papers').json[0]
    with transaction() as db:wrong=db.get(Paper,p2['id']).standard_answer['value']
    response=request('student_a1','POST',f"/papers/{p1['id']}/submit",json={'answer':'最终答案 '+str(wrong)})
    assert response.status_code==202
    assert request('student_a1','POST',f"/papers/{p1['id']}/submit",json={'answer':'again'}).status_code==409
    run();sub=request('student_a1','GET','/submissions').json[0]
    assert sub['ai_score']<=40 and sub['ai_raw']['model_score']==100
    assert len(request('student_a1','GET','/wrong-questions').json)==1
    assert request('teacher_b','POST',f"/submissions/{sub['id']}/review",json={'score':80,'note':'x'}).status_code==404
    result=request('teacher_a','POST',f"/submissions/{sub['id']}/review",json={'score':75,'note':'过程有部分得分'})
    assert result.json['ai_score']==sub['ai_score'] and result.json['final_score']==75
    assert request('student_a2','GET','/submissions').json==[]


def test_deadline_and_invalid_template(system):
    request,run,_=system
    a=assignment(request);request('teacher_a','POST',f"/assignments/{a['id']}/publish");run()
    paper=request('student_a1','GET','/papers').json[0]
    with transaction() as db:db.get(Assignment,a['id']).deadline=now()-timedelta(seconds=1)
    assert request('student_a1','POST',f"/papers/{paper['id']}/submit",json={'answer':'1'}).status_code==409
    with pytest.raises(ValueError):calculate('__import__("os").system("x")',{})


def test_weekly_sparse_review_and_class_scope(system):
    request,run,_=system
    result=request('teacher_a','POST','/weekly');assert result.status_code==202;run()
    row=request('teacher_a','GET','/weekly').json[0]
    assert row['state']=='draft' and not row['facts']['sample_sufficient'] and '记录不够' in row['teacher_comment']
    assert request('student_a1','GET','/weekly').json==[]
    assert request('teacher_b','POST',f"/weekly/{row['id']}/publish",json={'comment':'x'}).status_code==404
    assert request('teacher_a','POST',f"/weekly/{row['id']}/publish",json={'comment':row['teacher_comment']}).status_code==200
    assert len(request('student_a1','GET','/weekly').json)==1
    assert request('student_b1','GET','/weekly').json==[]


def test_skill_upload_and_toggle(system):
    request,_,_=system
    source='---\nname: history\ndescription: 历史探究课程\n---\n# 提示\n先询问年代和主题。'
    row=request('teacher_a','POST','/skills',data={'file':(io.BytesIO(source.encode()),'SKILL.md')})
    assert row.status_code==201
    assert request('student_a1','POST','/skills',data={'file':(io.BytesIO(source.encode()),'SKILL.md')}).status_code==403
    assert request('teacher_a','PATCH',f"/skills/{row.json['id']}",json={'enabled':False}).json['enabled'] is False


def test_mcp_second_authorization(system):
    request,_,_=system
    from app.nexus.mcp_server import execute
    from app.nexus.security import issue
    with transaction() as db:
        user=db.scalar(select(User).where(User.username=='student_a1'));token=issue(user)
    a=request('teacher_a','GET','/agents').json[0];b=request('teacher_b','GET','/agents').json[0]
    with pytest.raises(PermissionError):execute('lecture_search',token,b['id'],query='x')
    with pytest.raises(PermissionError):execute('class_statistics',token,a['id'])
    assert 'assignments' in execute('current_assignments',token,request('teacher_a','GET','/agents').json[1]['id'])


@pytest.mark.parametrize('kind,question',[('guide','数学解题引导：方程怎么检查'),('grading','作业批改评分怎么核对'),('explain','错题错因讲解怎么进行')])
def test_three_builtin_skills_have_effect_and_can_be_disabled(system,monkeypatch,kind,question):
    request,run,_=system
    material=upload(request,content='数学解题引导：方程要检查条件。作业批改评分逐项核对标准。错题错因讲解从错误步骤分析。');run()
    skill=next(s for s in request('teacher_a','GET','/skills').json if s['kind']==kind)
    agent=request('teacher_a','GET','/agents').json[0]
    request('teacher_a','PATCH',f"/agents/{agent['id']}",json={'material_ids':[material['id']],'skill_ids':[skill['id']],'tools':[]})
    captured=[]
    def model(messages,actor,trace,tools=None,emit=None,**kwargs):
        captured.append(messages[0]['content'])
        if emit:emit({'event':'delta','text':'测试回答'})
        return {'role':'assistant','content':'测试回答'}
    monkeypatch.setattr(llm,'call',model)
    cid=request('student_a1','POST','/conversations',json={'agent_id':agent['id']}).json['id']
    response=request('student_a1','POST',f'/conversations/{cid}/messages',json={'question':question})
    assert 'event: done' in response.text and skill['body'] in captured[-1]
    request('teacher_a','PATCH',f"/skills/{skill['id']}",json={'enabled':False})
    response=request('student_a1','POST',f'/conversations/{cid}/messages',json={'question':question})
    assert 'event: done' in response.text and skill['body'] not in captured[-1]
