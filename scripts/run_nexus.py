"""Select an explicit private environment for a Nexus process."""
import argparse
import os
from pathlib import Path
import runpy
import sys
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser()
parser.add_argument('mode',choices=['init','serve','worker','verify'])
parser.add_argument('--env',default='.env.nexus.local')
parser.add_argument('--port',type=int,default=8081)
parser.add_argument('--live',action='store_true')
args=parser.parse_args()
path=(ROOT/args.env).resolve()
if not path.is_relative_to(ROOT) or not path.name.endswith('.local'):parser.error('Use an explicit local private environment inside this project')
load_dotenv(path,override=True)
if args.mode=='serve':
    from app.nexus import create_app
    create_app().run(host='127.0.0.1',port=args.port,debug=False,threaded=True)
elif args.mode=='verify':
    if not args.live:parser.error('--live required')
    sys.argv=['verify_nexus_live.py','--live','--isolated','--url',f'http://127.0.0.1:{args.port}']
    runpy.run_path(str(ROOT/'scripts/verify_nexus_live.py'),run_name='__main__')
else:runpy.run_path(str(ROOT/('scripts/nexus_init.py' if args.mode=='init' else 'scripts/nexus_worker.py')),run_name='__main__')
