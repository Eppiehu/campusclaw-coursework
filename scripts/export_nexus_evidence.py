"""Export only the new synthetic verification records; never credentials or database URLs."""
import json
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import select

ROOT=Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT/'.env.nexus-live2.local',override=True)
    from app.nexus.db import transaction
    from app.nexus.models import Audit,Task
    core=json.loads((ROOT/'apitest/report/nexus-live.json').read_text(encoding='utf-8'))
    weekly=json.loads((ROOT/'apitest/report/nexus-weekly-live.json').read_text(encoding='utf-8'))
    assert all(c['status']=='PASS' for c in core['checks']) and weekly['status']=='PASS'
    traces={event['trace_id'] for turn in core['records']['turns'] for event in turn['events'] if 'trace_id' in event}
    with transaction() as db:
        traces.update(db.scalars(select(Task.id).where(Task.kind=='grade',Task.target_id.in_(core['records']['submission_ids']))))
        rows=db.scalars(select(Audit).where(Audit.request_id.in_(traces),Audit.action.in_(['llm.request','llm.response','agent.tools'])).order_by(Audit.id)).all()
        observations=[{'event':r.action,'trace_id':r.request_id,'details':r.details} for r in rows]
    value={'scope':'Only newly created synthetic teaching records from the isolated Nexus verification database.',
           'core':core,'weekly_sufficient_sample':weekly,'model_and_tool_observations':observations}
    deployed=ROOT/'apitest/report/nexus-deployed.json'
    if deployed.exists():value['docker_smoke']=json.loads(deployed.read_text(encoding='utf-8'))
    encoded=json.dumps(value,ensure_ascii=False,indent=2).encode()
    for marker in [b'"Authorization"',b'"auth_token"',b'"password"',b'postgresql+psycopg://',b'sk-']:
        assert marker not in encoded,marker
    target=ROOT/'docs/evidence/20261025-nexus-live.json';target.write_bytes(encoded)
    print('Exported synthetic evidence:',target.name)


if __name__=='__main__':main()
