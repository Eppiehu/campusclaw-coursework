import hashlib
import os
from pathlib import Path
import uuid
import pytest
from sqlalchemy import text, select

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def system(monkeypatch):
    from app.nexus.db import engine,transaction
    from app.nexus.models import Base,Task
    original=os.environ['NEXUS_DATABASE_URL']
    schema='nexus_test_'+uuid.uuid4().hex[:12]
    with engine(original).begin() as db:
        db.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        db.execute(text('CREATE SCHEMA '+schema))
    monkeypatch.setenv('NEXUS_DATABASE_URL',original+'?options=-csearch_path%3D'+schema+',public')
    Base.metadata.create_all(engine(),checkfirst=False)
    from app.nexus.seed import seed
    seed()
    from app.nexus import create_app
    from app.nexus import retrieval,api,jobs
    def embedding(value):
        vector=[0.0]*512
        for word in retrieval.terms(value):vector[int(hashlib.md5(word.encode()).hexdigest(),16)%512]+=1.0
        norm=sum(x*x for x in vector)**.5 or 1
        return [x/norm for x in vector]
    monkeypatch.setattr(retrieval,'embed',embedding)
    def schedule(kind,target,klass):
        identifier=uuid.uuid4().hex
        with transaction() as db:db.add(Task(id=identifier,kind=kind,target_id=target,class_id=klass,state='queued'))
        return identifier
    monkeypatch.setattr(api,'schedule',schedule)
    app=create_app({'TESTING':True})
    from redis import Redis
    Redis.from_url(os.environ['NEXUS_REDIS_URL']).delete('nexus:login:'+hashlib.sha256(b'127.0.0.1').hexdigest())
    clients={}
    for name in ['teacher_a','teacher_b','student_a1','student_a2','student_b1']:
        client=app.test_client();response=client.post('/api/nexus/login',json={'username':name,'password':'Teacher123!' if name.startswith('teacher') else 'Student123!'})
        assert response.status_code==200,response.json
        clients[name]=(client,{'Authorization':'Bearer '+response.json['token']})
    def request(name,method,path,**kwargs):
        client,headers=clients[name]
        return client.open('/api/nexus'+path,method=method,headers=headers,**kwargs)
    def run():
        with transaction() as db:identifiers=list(db.scalars(select(Task.id).where(Task.state=='queued').order_by(Task.created_at)))
        for identifier in identifiers:
            try:jobs.perform(identifier)
            except Exception:pass
    yield request,run,app
    engine().dispose()
    with engine(original).begin() as db:db.execute(text('DROP SCHEMA '+schema+' CASCADE'))


def upload(request,teacher='teacher_a',title='分数运算',content='分数相加需要先通分，再把分子相加。分母保持不变。'):
    import io
    response=request(teacher,'POST','/materials',data={'title':title,'file':(io.BytesIO(content.encode()),'lecture.md')})
    assert response.status_code==202,response.json
    return response.json
