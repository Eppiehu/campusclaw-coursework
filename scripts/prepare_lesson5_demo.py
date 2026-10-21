"""Prepare the course's two-Agent acceptance data through normal teacher APIs."""
import argparse
import os
from pathlib import Path
import requests


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',default='http://127.0.0.1:8080');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    login=requests.post(args.base+'/api/login',json={'username':'teacher_a','password':os.environ.get('DEMO_TEACHER_PASSWORD','Teacher123!')},timeout=10)
    login.raise_for_status();headers={'Authorization':'Bearer '+login.json()['token']}
    def get(path):
        response=requests.get(args.base+path,headers=headers,timeout=10);response.raise_for_status();return response.json()
    for subject in ('数学','语文'):
        title=subject+'学习资料'
        material=next((item for item in get('/api/materials')['materials'] if item['title']==title),None)
        if material is None:
            source=root/'demo'/(title+'.md')
            with source.open('rb') as file:
                response=requests.post(args.base+'/api/materials/upload',headers=headers,data={'title':title},files={'file':(source.name,file,'text/markdown')},timeout=15)
            response.raise_for_status();material_id=response.json()['material_id']
        else:material_id=material['id']
        skill=next(item for item in get('/api/skills')['skills'] if item['name']==subject+'解题引导')
        name='课件演示-'+subject+'助手'
        existing=next((item for item in get('/api/agents')['agents'] if item['name']==name),None)
        path=f"/api/agents/{existing['id']}" if existing else '/api/agents'
        response=requests.request('PUT' if existing else 'POST',args.base+path,headers=headers,
            json={'name':name,'prompt':'你是数学学习助手。未命中技能时直接简短解答；命中技能时严格按技能说明回答。' if subject=='数学' else '',
                  'enabled':True,'skill_ids':[skill['id']],'material_ids':[material_id]},timeout=10)
        response.raise_for_status()
        print('PASS normal teacher API demo',subject.encode('unicode_escape').decode(),'Agent',response.json()['agent']['id'])


if __name__=='__main__':main()
