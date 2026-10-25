"""Run a real RQ worker; SpawnWorker also supports the local Windows environment."""
import os
from rq import Worker
from app.nexus.jobs import redis_connection

if __name__=='__main__':
    if os.name=='nt':raise RuntimeError('Run the RQ Worker in Linux, WSL or Docker; Windows child monitoring is not supported')
    worker=Worker([os.environ.get('NEXUS_QUEUE_NAME','nexus')],connection=redis_connection())
    worker.work(with_scheduler=False)
