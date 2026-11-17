import os,time,json,logging
from pathlib import Path
import redis
from src.config.database import Session
from src.models.entities import Snapshot
from src.services.analysis import calculate
from src.services import monitor
r=redis.Redis.from_url(os.environ['REDIS_URL'])
SNAPSHOT_QUEUE='camp:snapshots'
MONITOR_QUEUE='camp:monitors'
SWEEP_SECONDS=int(os.environ.get('MONITOR_SWEEP_SECONDS','30'))
last_sweep=time.time()

def recover_snapshots():
 with Session() as recovery:
  for pending in recovery.query(Snapshot).filter(Snapshot.state.in_(['queued','running'])).all():
   pending.state='queued';r.rpush(SNAPSHOT_QUEUE,pending.id)
  recovery.commit()

def snapshot_workflow(item):
 with Session() as s:
  row=s.get(Snapshot,int(item))
  if not row or row.state!='queued':return
  snapshot=row.result['snapshot'];row.state='running';s.commit()
  try:
   row.result={**calculate(snapshot),'snapshot':snapshot};row.state='done'
   Path('/artifacts/'+str(row.id)+'.json').write_text(json.dumps(row.result,ensure_ascii=False))
  except Exception as e:row.state='failed';row.error=str(e)
  s.commit()

def monitor_workflow(monitor_id):
 # 每次都会补齐所有应评估日：即使提醒/队列消息丢失，停机期间的日期也不会遗漏
 if monitor_id==0:monitor.sweep_all(Session)
 else:
  with Session() as s:
   try:
    monitor.sweep_monitor(s,monitor_id);s.commit()
   except Exception:
    s.rollback();logging.exception('monitor workflow failed: %s',monitor_id)

def sweep(today=None):
 last=monitor.sweep_all(Session,today=today)
 logging.info('monitor sweep %s',last)
 return last

recover_snapshots()
try:sweep()
except Exception:logging.exception('initial monitor sweep')
while True:
 Path('/tmp/heartbeat').touch()
 try:
  if time.time()-last_sweep>=SWEEP_SECONDS:
   last_sweep=time.time()
   try:sweep()
   except Exception:logging.exception('periodic monitor sweep')
  item=r.blpop([MONITOR_QUEUE,SNAPSHOT_QUEUE],timeout=3)
  if not item:continue
  queue,value=item
  if queue==MONITOR_QUEUE:monitor_workflow(int(value))
  else:snapshot_workflow(value)
 except Exception:logging.exception('worker');time.sleep(2)
