"""Actual upstream streaming; no fabricated model fallback."""
import json
import os
import time
import httpx
from .db import transaction, audit
from .models import User


def call(messages, actor_id, trace_id, tools=None, emit=None, schema=None):
    key=os.environ.get('OPENAI_API_KEY')
    if not key:raise RuntimeError('模型密钥未配置')
    body={'model':os.environ.get('NEXUS_MODEL',os.environ.get('OPENAI_MODEL','deepseek-chat')),
          'messages':messages,'stream':True,'temperature':0.1,'max_tokens':1800}
    if tools:body.update(tools=tools,tool_choice='auto')
    if schema:body['response_format']={'type':'json_object'}
    endpoint=os.environ.get('OPENAI_BASE_URL','https://api.deepseek.com').rstrip('/')
    if not endpoint.endswith('/chat/completions'):endpoint+='/chat/completions'
    start=time.monotonic();content='';calls={};usage={};finish=None
    with transaction() as db:
        actor=db.get(User,actor_id);audit(db,actor,'llm.request',details={'body':body},request_id=trace_id)
    try:
        with httpx.Client(timeout=httpx.Timeout(120,connect=20),trust_env=False) as client:
            with client.stream('POST',endpoint,headers={'Authorization':'Bearer '+key},json=body) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith('data:'):continue
                    payload=line[5:].strip()
                    if payload=='[DONE]':break
                    data=json.loads(payload)
                    usage=data.get('usage') or usage
                    for choice in data.get('choices',[]):
                        delta=choice.get('delta',{})
                        if delta.get('content'):
                            content+=delta['content']
                            if emit:emit({'event':'delta','text':delta['content']})
                        for part in delta.get('tool_calls') or []:
                            current=calls.setdefault(part['index'],{'id':'','type':'function','function':{'name':'','arguments':''}})
                            current['id']+=part.get('id','')
                            current['function']['name']+=part.get('function',{}).get('name','')
                            current['function']['arguments']+=part.get('function',{}).get('arguments','')
                        finish=choice.get('finish_reason') or finish
        if finish=='length':raise RuntimeError('模型输出达到长度限制，请缩短问题后重试')
        if not content and not calls:raise RuntimeError('模型返回空内容')
        with transaction() as db:
            audit(db,db.get(User,actor_id),'llm.response',details={'content':content,'tool_calls':list(calls.values()),
                  'finish_reason':finish,'usage':usage,'duration_ms':round((time.monotonic()-start)*1000)},request_id=trace_id)
        return {'role':'assistant','content':content,**({'tool_calls':list(calls.values())} if calls else {})}
    except Exception as exc:
        with transaction() as db:
            audit(db,db.get(User,actor_id),'llm.error',details={'type':type(exc).__name__},success=False,request_id=trace_id)
        raise RuntimeError('模型调用失败，请稍后重试；请求记录已保存') from exc


def structured(prompt,payload,model,actor_id,trace_id):
    answer=call([{'role':'system','content':prompt+'\n只返回JSON。格式：'+json.dumps(model.model_json_schema(),ensure_ascii=False)},
                 {'role':'user','content':json.dumps(payload,ensure_ascii=False)}],actor_id,trace_id,schema=model)
    return model.model_validate_json(answer['content'])
