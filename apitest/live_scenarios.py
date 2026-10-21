"""Explicit real-LLM evidence, binding, locked-Agent and Skill toggle acceptance."""
import argparse
import json
import re
import requests


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live',action='store_true');parser.add_argument('--base',default='http://127.0.0.1:8080');args=parser.parse_args()
    if not args.live:parser.error('real model calls require --live')
    base=args.base
    def login(user,password):
        response=requests.post(base+'/api/login',json={'username':user,'password':password},timeout=10);response.raise_for_status()
        return {'Authorization':'Bearer '+response.json()['token']}
    teacher=login('teacher_a','Teacher123!');student=login('student_a1','Student123!')
    def get(path,headers):
        response=requests.get(base+path,headers=headers,timeout=10);response.raise_for_status();return response.json()
    agents=get('/api/agents',teacher)['agents']
    math=next(agent for agent in agents if agent['name']=='课件演示-数学助手')
    language=next(agent for agent in agents if agent['name']=='课件演示-语文助手')
    assert all(agent['enabled'] for agent in get('/api/agents',student)['agents'])
    response=requests.post(base+'/api/conversations',headers=student,json={'agent_id':math['id']},timeout=10);response.raise_for_status();cid=response.json()['conversation']['id']
    def ask(question):
        with requests.post(base+f'/api/conversations/{cid}/messages',headers=student,json={'question':question,'agent_id':language['id']},stream=True,timeout=125) as response:
            response.raise_for_status();frames=[];event_name=None;data_lines=[]
            for raw in response.iter_lines(chunk_size=1,decode_unicode=True):
                line=raw if isinstance(raw,str) else raw.decode()
                if line.startswith('event:'):event_name=line[6:].strip()
                elif line.startswith('data:'):data_lines.append(line[5:].strip())
                elif not line and event_name:
                    frames.append((event_name,json.loads('\n'.join(data_lines))));event_name=None;data_lines=[]
        assert frames[0][0]=='meta' and frames[-1][0]=='done',frames[-1]
        assert sum(name=='delta' for name,_ in frames)>1
        text=''.join(data['text'] for name,data in frames if name=='delta')
        meta=frames[0][1];ids={item['id'] for item in meta['citations']}
        assert all(int(ref) in ids for ref in re.findall(r'\[(\d+)\]',text))
        saved=get(f'/api/conversations/{cid}',student)
        assert saved['conversation']['agent_id']==math['id']
        assert saved['messages'][-1]['content']==text and saved['messages'][-1]['id']==frames[-1][1]['message_id']
        return meta,text
    meta,_=ask('语文阅读题应先检查什么？')
    assert meta['skill'] is None and all(item['material_id'] in math['material_ids'] for item in meta['citations'])
    print('PASS real Agent binding intersection, no unbound language Skill/material; body Agent ignored')
    question='我解方程2x+3=7时直接写2x=7，错在哪一步？'
    enabled_meta,enabled=ask(question)
    assert enabled_meta['skill']=='数学解题引导' and enabled_meta['citations']
    assert '[1]' in enabled and not re.search(r'最终答案|选项|得数|完整解题过程|[=＝]\s*\d',enabled)
    assert all('title' in source and 'chunk_index' in source for source in enabled_meta['citations'])
    skill_id=math['skill_ids'][0]
    try:
        response=requests.patch(base+f'/api/skills/{skill_id}',headers=teacher,json={'enabled':False},timeout=10);response.raise_for_status()
        disabled_meta,disabled=ask(question)
        assert disabled_meta['skill'] is None
        assert enabled!=disabled
        print('PASS real guided response with title/chunk citations; disabled Skill changes next turn; conversation',cid)
        print('enabled_answer',enabled.encode('unicode_escape').decode())
        print('disabled_answer',disabled.encode('unicode_escape').decode())
    finally:
        requests.patch(base+f'/api/skills/{skill_id}',headers=teacher,json={'enabled':True},timeout=10).raise_for_status()


if __name__=='__main__':main()
