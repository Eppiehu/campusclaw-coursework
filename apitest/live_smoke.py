"""Explicit paid-model smoke test against a running Flask server."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.request import HTTPCookieProcessor, Request, build_opener
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--live',action='store_true');parser.add_argument('--base',default='http://127.0.0.1:8080');args=parser.parse_args()
    if not args.live:parser.error('paid model call requires --live')
    client=build_opener(HTTPCookieProcessor())
    def call(path,body=None,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        return client.open(Request(args.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method='POST' if body is not None else 'GET'),timeout=125)
    with call('/api/login',{'username':'teacher_a','password':os.environ.get('DEMO_TEACHER_PASSWORD','Teacher123!')}) as response:teacher=json.load(response)['token']
    # A smoke Agent intentionally has no bound material: lesson-5 no-evidence must still call LLM.
    with call('/api/agents',{'name':'live-smoke-'+__import__('uuid').uuid4().hex[:8],'prompt':'你是学习助手，简短给出学习建议。','material_ids':[],'skill_ids':[]},teacher) as response:agent=json.load(response)['agent']['id']
    with call('/api/login',{'username':'student_a1','password':os.environ.get('DEMO_STUDENT_PASSWORD','Student123!')}) as response:student=json.load(response)['token']
    with call('/api/conversations',{'agent_id':agent},student) as response:cid=json.load(response)['conversation']['id']
    with call(f'/api/conversations/{cid}/messages',{'question':'怎样安排今天的复习？请给两条简短建议。'},student) as response:
        assert response.headers['Content-Type'].startswith('text/event-stream')
        body=response.read().decode()
    frames=[]
    for frame in body.split('\n\n'):
        if not frame.strip():continue
        lines=frame.splitlines();frames.append((lines[0][6:].strip(),json.loads(lines[1][6:])))
    assert frames[0][0]=='meta' and frames[0][1]['citations']==[]
    assert sum(name=='delta' for name,_ in frames)>1 and frames[-1][0]=='done'
    text=''.join(data['text'] for name,data in frames if name=='delta')
    assert not __import__('re').search(r'\[\d+\]',text)
    with call(f'/api/conversations/{cid}',token=student) as response:saved=json.load(response)['messages'][-1]
    assert saved['id']==frames[-1][1]['message_id'] and saved['content']==text
    print('PASS real DeepSeek SSE; no evidence; multiple deltas; persisted body identical; conversation',cid)
    # Keep the successful conversation for user inspection, disable the smoke Agent for new sessions.
    request=Request(args.base+f'/api/agents/{agent}',data=b'{"enabled":false}',headers={'Authorization':'Bearer '+teacher,'Content-Type':'application/json'},method='PATCH')
    client.open(request,timeout=10).close()


if __name__=='__main__':main()
