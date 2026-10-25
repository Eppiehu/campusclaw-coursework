"""Weekly generation and persisted outbox recovery; one scheduler per deployment."""
from datetime import timedelta
import time
import uuid
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.nexus.db import transaction
from app.nexus.models import User, WeeklyReport, Task, now, week_start
from app.nexus.jobs import schedule, dispatch, redis_connection


def tick():
    start=week_start()
    # Generate the previous completed week, not a partially observed current week.
    start-=timedelta(days=7)
    with transaction() as db:
        classes=list(db.scalars(select(User.class_id).where(User.role=='teacher').distinct()))
        for klass in classes:
            statement=insert(WeeklyReport).values(class_id=klass,period_start=start,state='queued').on_conflict_do_nothing().returning(WeeklyReport.id)
            identifier=db.scalar(statement)
            if identifier:
                db.add(Task(id=uuid.uuid4().hex,kind='weekly',target_id=identifier,class_id=klass,state='pending'))
        pending=list(db.scalars(select(Task.id).where(Task.state.in_(['pending','dispatch_failed']))))
    for identifier in pending:
        try:dispatch(identifier)
        except ValueError:pass


if __name__=='__main__':
    while True:
        try:
            lock=redis_connection().lock('nexus:scheduler',timeout=240,blocking_timeout=0)
            if lock.acquire(blocking=False):
                try:tick()
                finally:lock.release()
        except Exception as exc:print('Scheduler unavailable:',type(exc).__name__,flush=True)
        time.sleep(60)
