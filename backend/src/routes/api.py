import os,json,logging
import redis
from fastapi import APIRouter,Depends,HTTPException,Response
from src.config.database import db
from src.models.entities import User,Metric,Fact,Snapshot,Audit,MonitorConfig,MonitorEvaluation,MonitorAlert,MonitorEvent
from src.schemas.business import Login,MetricInput,FactInput,RunInput,NoteInput,MonitorInput,ConfirmInput
from src.middlewares.auth import current,editor,admin
from src.utils.security import verify,token
from src.services.business import audit,dump
from src.services.repository import save_metric,save_fact
from src.services import monitor
from src.controllers import business as ensure
router=APIRouter()
@router.post('/auth/login')
def login(data:Login,s=Depends(db)):
 u=s.query(User).filter_by(email=data.email).first()
 if not u or not verify(data.password,u.password):raise HTTPException(401,'账号或密码错误')
 return {'token':token(u),'user':dump(u)}
@router.get('/me')
def me(u=Depends(current)):return dump(u)
@router.get('/metrics')
def metrics(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Metric).order_by(Metric.code,Metric.version).all()]
@router.post('/metrics')
def create_metric(data:MetricInput,u=Depends(editor),s=Depends(db)):
 r=save_metric(s,data);audit(s,u,'建立口径 '+r.code+' v'+str(r.version));enqueue_monitor();return dump(r)
@router.put('/metrics/{i}')
def edit_metric(i:int,data:MetricInput,u=Depends(editor),s=Depends(db)):
 r=save_metric(s,data,i);audit(s,u,'修订口径 '+str(i));enqueue_monitor();return dump(r)
@router.get('/facts')
def facts(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Fact).order_by(Fact.day.desc(),Fact.class_code).all()]
@router.post('/facts')
def create_fact(data:FactInput,u=Depends(editor),s=Depends(db)):
 r=save_fact(s,data);audit(s,u,'录入事实 '+str(r.id));enqueue_monitor();return dump(r)
@router.put('/facts/{i}')
def edit_fact(i:int,data:FactInput,u=Depends(editor),s=Depends(db)):
 r=save_fact(s,data,i);audit(s,u,'修订事实 '+str(i));enqueue_monitor();return dump(r)
@router.get('/snapshots')
def snapshots(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Snapshot).order_by(Snapshot.id.desc()).all()]
@router.post('/snapshots')
def run(data:RunInput,u=Depends(editor),s=Depends(db)):
 m=ensure.metric(s,data.metric_id);baseline=None
 if data.baseline_id:
  b=ensure.snapshot(s,data.baseline_id)
  if b.state!='done':raise HTTPException(409,'仅成功快照可作为比较基线')
  if b.result['metric']['code']!=m.code:raise HTTPException(409,'只能比较同一指标代码的口径版本')
  baseline=dict(id=b.id,date_from=b.date_from,date_to=b.date_to,result={k:b.result[k] for k in ['metric','value','facts_checksum']})
 values=data.model_dump(mode='json');rows=[dump(f) for f in s.query(Fact).filter(Fact.day>=values['date_from'],Fact.day<=values['date_to']).order_by(Fact.day,Fact.class_code).all()]
 frozen={'metric':dump(m),'facts':rows,'baseline':baseline,'date_from':values['date_from'],'date_to':values['date_to']}
 r=Snapshot(**values,result={'snapshot':frozen});s.add(r);s.commit()
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush('camp:snapshots',r.id)
 except redis.RedisError:r.state='failed';r.error='队列不可用，请恢复后重新试算';s.commit();raise HTTPException(503,r.error)
 audit(s,u,'提交试算 '+str(r.id));return dump(r)
@router.get('/snapshots/{i}')
def detail(i:int,u=Depends(current),s=Depends(db)):return dump(ensure.snapshot(s,i))
@router.put('/snapshots/{i}/note')
def note(i:int,data:NoteInput,u=Depends(editor),s=Depends(db)):
 r=ensure.snapshot(s,i)
 if r.state!='done' or r.approval=='approved':raise HTTPException(409,'仅成功且未签核快照可编辑意见')
 r.note=data.note;s.commit();audit(s,u,'起草签核意见 '+str(i));return dump(r)
@router.post('/snapshots/{i}/approve')
def approve(i:int,u=Depends(admin),s=Depends(db)):
 r=ensure.snapshot(s,i)
 if r.state!='done' or r.approval=='approved':raise HTTPException(409,'仅成功且未签核快照可签核')
 if r.result['value'] is None:raise HTTPException(409,'零分母undefined快照不能签核，请修正口径')
 if len(r.note)<8:raise HTTPException(409,'先填写至少8字业务解释')
 m=ensure.metric(s,r.metric_id)
 if any(getattr(m,k)!=v for k,v in r.result['metric'].items() if k not in ['locked']):raise HTTPException(409,'口径在试算后已变更，请用当前版本重新试算再签核')
 r.approval='approved';r.approved_by=u.email;m.locked=True;s.commit();audit(s,u,'签核冻结 '+str(i));return dump(r)
@router.get('/snapshots/{i}/export')
def export(i:int,u=Depends(current),s=Depends(db)):
 r=ensure.snapshot(s,i)
 if r.state!='done':raise HTTPException(409,'仅成功快照可导出')
 return Response(json.dumps(dump(r),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="camp-metric-{i}.json"'})
@router.get('/audits')
def audits(u=Depends(admin),s=Depends(db)):return [dump(r) for r in s.query(Audit).order_by(Audit.id.desc()).limit(100)]
MONITOR_QUEUE='camp:monitors'
def enqueue_monitor(monitor_id=None):
 # 提醒只是加速：即使入队失败，事实已保存，worker 的周期扫描仍会补齐评估
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush(MONITOR_QUEUE,0 if monitor_id is None else monitor_id);return True
 except redis.RedisError:logging.exception('monitor enqueue failed');return False
def monitor_events(s,i,limit=200):
 return [monitor.event_out(e) for e in s.query(MonitorEvent).filter_by(monitor_id=i).order_by(MonitorEvent.id.desc()).limit(limit).all()]
def monitor_payload(s,c,today=None):
 return {**dump(c),'summary':monitor.monitor_summary(s,c,today),'metric':dump(ensure.metric(s,c.metric_id))}
@router.get('/monitors')
def monitors(u=Depends(current),s=Depends(db)):
 return [monitor_payload(s,c) for c in s.query(MonitorConfig).order_by(MonitorConfig.id).all()]
@router.post('/monitors')
def create_monitor(data:MonitorInput,u=Depends(editor),s=Depends(db)):
 m=ensure.metric(s,data.metric_id);values=data.model_dump(mode='json')
 now=monitor.now_shanghai();c=MonitorConfig(**values,created_by=u.email,created=now,updated_by=u.email,updated=now)
 s.add(c);s.commit()
 audit(s,u,'建立滚动监测 '+str(c.id)+' / 口径 '+m.code+' v'+str(m.version)+' / 阈值 '+str(c.threshold)+'%')
 enqueue_monitor(c.id)
 return monitor_payload(s,c)
@router.put('/monitors/{i}')
def edit_monitor(i:int,data:MonitorInput,u=Depends(editor),s=Depends(db)):
 c=s.get(MonitorConfig,i)
 if not c:raise HTTPException(404,'监测配置不存在')
 m=ensure.metric(s,data.metric_id)
 for k,v in data.model_dump(mode='json').items():setattr(c,k,v)
 c.updated_by=u.email;c.updated=monitor.now_shanghai();s.commit()
 audit(s,u,'修订滚动监测 '+str(i)+' / 口径 '+m.code+' v'+str(m.version)+' / 阈值 '+str(c.threshold)+'%')
 enqueue_monitor(c.id)
 return monitor_payload(s,c)
@router.post('/monitors/{i}/run')
def run_monitor(i:int,u=Depends(editor),s=Depends(db)):
 c=s.get(MonitorConfig,i)
 if not c:raise HTTPException(404,'监测配置不存在')
 ok=enqueue_monitor(c.id);audit(s,u,'手动触发滚动监测 '+str(i));return {'queued':i,'enqueued':ok}
@router.get('/monitors/{i}')
def monitor_detail(i:int,u=Depends(current),s=Depends(db)):
 c=s.get(MonitorConfig,i)
 if not c:raise HTTPException(404,'监测配置不存在')
 return {**monitor_payload(s,c),'events':monitor_events(s,i)}
@router.get('/monitors/{i}/evaluations')
def monitor_evaluations(i:int,u=Depends(current),s=Depends(db)):
 if not s.get(MonitorConfig,i):raise HTTPException(404,'监测配置不存在')
 rows=s.query(MonitorEvaluation).filter_by(monitor_id=i).order_by(MonitorEvaluation.eval_date).all()
 return {'today':monitor.today_shanghai().isoformat(),'evaluations':[monitor.evaluation_out(r) for r in rows]}
@router.get('/monitors/{i}/evaluations/{day}')
def monitor_evaluation(i:int,day:str,u=Depends(current),s=Depends(db)):
 r=s.query(MonitorEvaluation).filter_by(monitor_id=i,eval_date=day).one_or_none()
 if not r:raise HTTPException(404,'该日期尚无评估结果')
 return {**monitor.evaluation_out(r),'evidence':r.evidence}
@router.get('/monitors/{i}/alerts')
def monitor_alerts(i:int,u=Depends(current),s=Depends(db)):
 if not s.get(MonitorConfig,i):raise HTTPException(404,'监测配置不存在')
 rows=s.query(MonitorAlert).filter_by(monitor_id=i).order_by(MonitorAlert.id.desc()).all()
 return [monitor.alert_out(r) for r in rows]
@router.get('/monitor-alerts')
def all_alerts(u=Depends(current),s=Depends(db)):
 rows=s.query(MonitorAlert).order_by(MonitorAlert.id.desc()).limit(200).all()
 return [monitor.alert_out(r) for r in rows]
@router.get('/monitor-alerts/{i}')
def alert_detail(i:int,u=Depends(current),s=Depends(db)):
 r=s.get(MonitorAlert,i)
 if not r:raise HTTPException(404,'预警不存在')
 events=[monitor.event_out(e) for e in s.query(MonitorEvent).filter_by(alert_id=i).order_by(MonitorEvent.id).all()]
 return {**monitor.alert_out(r,detail=True),'events':events}
@router.post('/monitor-alerts/{i}/confirm')
def confirm_monitor_alert(i:int,data:ConfirmInput,u=Depends(editor),s=Depends(db)):
 r,outcome=monitor.confirm_alert(s,i,u.email,data.note)
 if r is None:raise HTTPException(404,'预警不存在')
 if outcome=='recovered':raise HTTPException(409,'预警已恢复，不能确认')
 if outcome=='revoked':raise HTTPException(409,'预警已撤销，不能确认')
 s.commit()
 if outcome=='already_confirmed':return monitor.alert_out(r,detail=True)
 audit(s,u,'确认监测预警 '+str(i))
 return monitor.alert_out(r,detail=True)

