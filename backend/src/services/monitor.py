import hashlib
import json
import logging
import math
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

try:
    from zoneinfo import ZoneInfo
    SHANGHAI = ZoneInfo('Asia/Shanghai')
except Exception:  # 精简镜像可能缺少 tzdata；上海当前无夏令时，固定 +08:00 等价
    SHANGHAI = timezone(timedelta(hours=8))

from src.models.entities import (
    Fact, Metric, MonitorAlert, MonitorConfig, MonitorEvaluation, MonitorEvent,
)
from src.services.business import dump
from src.services.expression import execute, parse

VERSION = 'camp-rolling-monitor-v1'
WINDOW_DAYS = 7
CONSECUTIVE_BELOW = 3
METHOD = (
    '按上海日期逐日评估：取评估日及之前共七个自然日的班级日事实，按口径分别过滤分子/分母的授课方式，'
    '逐行执行白名单表达式后分别求和，再求分子合计/分母合计。阈值按百分比比较；零分母为未知且打断连续段，'
    '连续三个已评日低于阈值形成一次预警，恢复（比值不低于阈值）后结束。不是日比率的简单平均。'
)


def now_shanghai():
    return datetime.now(SHANGHAI).isoformat(timespec='seconds')


def today_shanghai(now=None):
    if now is None:
        now = datetime.now(SHANGHAI)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=SHANGHAI)
    else:
        now = now.astimezone(SHANGHAI)
    return now.date()


def window_for(day):
    return day - timedelta(days=WINDOW_DAYS - 1), day


def _hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def metric_snapshot(metric):
    return {
        k: getattr(metric, k) for k in (
            'id', 'code', 'version', 'name', 'numerator', 'denominator',
            'numerator_mode', 'denominator_mode', 'note',
        )
    }


def _signature(metric, facts, threshold):
    return _hash({'metric': metric, 'facts': facts, 'threshold': round(float(threshold), 10)})


def _compute(metric, facts, threshold):
    """按滚动窗口事实计算；返回状态与分子分母。零分母为 unknown。"""
    try:
        n_tree = parse(metric['numerator'])
        d_tree = parse(metric['denominator'])
        nr = [r for r in facts if metric['numerator_mode'] == '全部' or r['mode'] == metric['numerator_mode']]
        dr = [r for r in facts if metric['denominator_mode'] == '全部' or r['mode'] == metric['denominator_mode']]
        numerator = sum(execute(n_tree, r) for r in nr)
        denominator = sum(execute(d_tree, r) for r in dr)
    except ValueError as exc:
        return {
            'numerator': None, 'denominator': None, 'numerator_rows': 0, 'denominator_rows': 0,
            'value': None, 'status': 'error', 'error': str(exc), 'undefined_reason': '',
        }
    value = None
    undefined = ''
    error = ''
    status = 'unknown'
    if denominator == 0:
        undefined = '滚动窗口外层分母为零，判定为未知，不补零且打断连续段'
    else:
        try:
            candidate = numerator / denominator
            if not math.isfinite(candidate) or abs(candidate) > 1e15:
                raise ValueError('指标比值超出允许范围，请检查极小分母与口径')
            value = candidate
            status = 'below' if value * 100 < float(threshold) else 'ok'
        except (ValueError, ZeroDivisionError) as exc:
            status = 'error'
            error = str(exc)
    return {
        'numerator': numerator, 'denominator': denominator,
        'numerator_rows': len(nr), 'denominator_rows': len(dr),
        'value': value, 'status': status, 'error': error, 'undefined_reason': undefined,
    }


def _facts_in_window(session, day_from, day_to):
    rows = session.query(Fact).filter(
        Fact.day >= day_from.isoformat(), Fact.day <= day_to.isoformat()
    ).order_by(Fact.day, Fact.class_code).all()
    return [dump(r) for r in rows]


def due_dates(config, today=None):
    today = today or today_shanghai()
    start = date.fromisoformat(config.start_date)
    if start > today:
        return []
    return [start + timedelta(days=i) for i in range((today - start).days + 1)]


def _event(session, monitor_id, action, actor, detail, alert_id=None):
    session.add(MonitorEvent(
        monitor_id=monitor_id, alert_id=alert_id, action=action,
        actor=actor, detail=detail, created=now_shanghai(),
    ))


def _evidence(config, metric, day, day_from, day_to, facts, threshold, signature, computed):
    return {
        'version': VERSION,
        'monitor': {
            'id': config.id, 'metric_id': config.metric_id,
            'threshold': float(threshold), 'start_date': config.start_date,
        },
        'metric': metric,
        'evaluation_date': day.isoformat(),
        'date_from': day_from.isoformat(),
        'date_to': day_to.isoformat(),
        'window_days': WINDOW_DAYS,
        'facts': facts,
        'facts_checksum': _hash(facts),
        'input_checksum': signature,
        'numerator': computed['numerator'],
        'denominator': computed['denominator'],
        'numerator_rows': computed['numerator_rows'],
        'denominator_rows': computed['denominator_rows'],
        'value': computed['value'],
        'status': computed['status'],
        'error': computed['error'],
        'undefined_reason': computed['undefined_reason'],
        'threshold': float(threshold),
        'method': METHOD,
    }


def evaluate_date(session, config, metric, day, facts):
    """计算或重算单日评估。输入未变则原样返回，重试幂等。"""
    day_from, day_to = window_for(day)
    rows = [r for r in facts if day_from.isoformat() <= r['day'] <= day_to.isoformat()]
    metricd = metric_snapshot(metric)
    threshold = float(config.threshold)
    signature = _signature(metricd, rows, threshold)
    existing = session.query(MonitorEvaluation).filter_by(
        monitor_id=config.id, eval_date=day.isoformat()
    ).one_or_none()
    if existing and existing.input_checksum == signature:
        return existing, False

    computed = _compute(metricd, rows, threshold)
    evidence = _evidence(config, metricd, day, day_from, day_to, rows, threshold, signature, computed)
    calculated = now_shanghai()
    if existing is None:
        row = MonitorEvaluation(
            monitor_id=config.id, eval_date=day.isoformat(), status=computed['status'],
            value=computed['value'], numerator=computed['numerator'],
            denominator=computed['denominator'], threshold=threshold,
            consecutive_below=0, revision=0, input_checksum=signature,
            evidence=evidence, error=computed['error'], calculated=calculated,
        )
        try:
            with session.begin_nested():
                session.add(row);session.flush()
        except IntegrityError:
            # 并发补评已插入同一 (monitor, 日期)：改为刷新同一条记录，不重复建行
            existing = session.query(MonitorEvaluation).filter_by(
                monitor_id=config.id, eval_date=day.isoformat()
            ).one()
            return _refresh(session, existing, config, computed, evidence, signature, threshold, calculated), True
        return row, True

    return _refresh(session, existing, config, computed, evidence, signature, threshold, calculated), True


def _refresh(session, existing, config, computed, evidence, signature, threshold, calculated):
    before = {
        'revision': existing.revision, 'status': existing.status, 'value': existing.value,
        'numerator': existing.numerator, 'denominator': existing.denominator,
        'input_checksum': existing.input_checksum, 'calculated': existing.calculated,
        'evidence': existing.evidence,
    }
    existing.status = computed['status']
    existing.value = computed['value']
    existing.numerator = computed['numerator']
    existing.denominator = computed['denominator']
    existing.threshold = threshold
    existing.input_checksum = signature
    existing.evidence = evidence
    existing.error = computed['error']
    existing.calculated = calculated
    existing.revision = (existing.revision or 0) + 1
    _event(session, config.id, 'recalculated', 'worker', {
        'evaluation_date': existing.eval_date,
        'reason': '事实、口径或阈值变化触发重算',
        'before': before,
        'after': {
            'revision': existing.revision, 'status': existing.status,
            'value': existing.value, 'numerator': existing.numerator,
            'denominator': existing.denominator,
            'input_checksum': existing.input_checksum,
            'evidence': evidence,
        },
    })
    session.flush()
    return existing, True


def derive_episodes(evals):
    """从按日期排序的评估重建连续段和预警 episode。

    低于阈值连续计数；未知/错误打断计数；已形成且未恢复的预警在未知日后仍保持活动，
    恢复（ok）才结束。返回每个 episode 的 anchor、trigger、恢复日和依据评估。
    """
    episodes = []
    run = []
    active = None
    for evaluation in evals:
        if evaluation.status == 'below':
            run.append(evaluation)
            if active is None and len(run) >= CONSECUTIVE_BELOW:
                active = {
                    'anchor_date': run[0].eval_date,
                    'trigger_date': evaluation.eval_date,
                    'evidence_evaluations': list(run),
                    'recovery_date': None,
                }
                episodes.append(active)
        elif evaluation.status == 'ok':
            if active:
                active['recovery_date'] = evaluation.eval_date
                active = None
            run = []
        else:  # unknown / error 打断连续段，但不把已形成的预警当作恢复
            run = []
    return episodes


def _alert_evidence(config, metric, episode):
    return {
        'version': VERSION,
        'monitor_id': config.id,
        'metric': metric,
        'threshold': float(config.threshold),
        'anchor_date': episode['anchor_date'],
        'trigger_date': episode['trigger_date'],
        'recovery_date': episode['recovery_date'],
        'evaluations': [{
            'id': e.id, 'eval_date': e.eval_date, 'status': e.status,
            'value': e.value, 'numerator': e.numerator, 'denominator': e.denominator,
            'threshold': e.threshold, 'input_checksum': e.input_checksum,
            'evidence': e.evidence,
        } for e in episode['evidence_evaluations']],
        'rule': '连续三个已评日低于阈值形成一次预警；恢复后结束；零分母未知打断连续段。',
    }


def _apply_episode(session, config, metric, alert, episode, actor):
    alert.anchor_date = episode['anchor_date']
    alert.start_date = episode['anchor_date']
    alert.end_date = episode['recovery_date']
    alert.updated = now_shanghai()
    if alert.status == 'open':
        # 未确认预警随重算刷新当前依据；已确认预警冻结确认时依据，不被后续重算覆盖
        alert.evidence = _alert_evidence(config, metric, episode)
    if episode['recovery_date']:
        if alert.status in ('open', 'confirmed'):
            alert.status = 'recovered'
            _event(session, alert.monitor_id, 'recovered', actor, {
                'alert_id': alert.id, 'recovery_date': episode['recovery_date'],
                'trigger_date': alert.trigger_date, 'note': '连续段外首个已评日不低于阈值，预警结束',
            }, alert.id)
    elif alert.status == 'recovered':
        # 更正后恢复的依据不再成立，预警回到活动状态；历史事件保留
        alert.status = 'confirmed' if alert.confirmed_by else 'open'
        _event(session, alert.monitor_id, 'reopened', actor, {
            'alert_id': alert.id, 'trigger_date': alert.trigger_date,
            'note': '更正后恢复依据不再成立，预警重新活动',
        }, alert.id)


def _revoke(session, alert, actor, reason):
    previous = alert.status
    alert.status = 'revoked'
    alert.revoked = now_shanghai()
    alert.revoke_reason = reason
    alert.updated = alert.revoked
    _event(session, alert.monitor_id, 'revoked', actor, {
        'alert_id': alert.id,
        'previous_status': previous,
        'reason': reason,
        'trigger_date': alert.trigger_date,
        'confirmed_by': alert.confirmed_by,
        'confirmed_at': alert.confirmed_at,
        'confirmed_evidence': alert.confirmed_evidence,
        'formation_evidence': alert.evidence,
        'note': '撤销保留原确认信息与当时依据，历史仍可查询',
    }, alert.id)


def reconcile(session, config, metric, evals, actor='worker'):
    """重建连续段并同步预警。重试幂等，不重复开警；不覆盖人工确认字段。"""
    episodes = derive_episodes(evals)
    alerts = session.query(MonitorAlert).filter_by(
        monitor_id=config.id
    ).order_by(MonitorAlert.id).with_for_update().all()
    live = [a for a in alerts if a.status != 'revoked']
    claimed = set()
    created = updated = revoked = 0
    epoch = date.max
    for episode in episodes:
        start = date.fromisoformat(episode['anchor_date'])
        end = date.fromisoformat(episode['recovery_date']) if episode['recovery_date'] else epoch
        alert = None
        for candidate in live:
            if candidate.id in claimed:
                continue
            c_start = date.fromisoformat(candidate.anchor_date)
            c_end = date.fromisoformat(candidate.end_date) if candidate.end_date else epoch
            # 连续段区间相交即视为同一次预警：迟报更正导致的起点/终点平移在原预警上重算
            if start <= c_end and c_start <= end:
                alert = candidate
                claimed.add(candidate.id)
                break
        if alert is None:
            alert = MonitorAlert(
                monitor_id=config.id, metric_id=config.metric_id,
                trigger_date=episode['trigger_date'], anchor_date=episode['anchor_date'],
                start_date=episode['anchor_date'], end_date=episode['recovery_date'],
                status='open', threshold=float(config.threshold),
                evidence=_alert_evidence(config, metric, episode),
                confirmed_by='', confirmed_at='', confirmed_evidence=None,
                revoked='', revoke_reason='', created=now_shanghai(),
                updated=now_shanghai(),
            )
            session.add(alert)
            session.flush()
            _event(session, config.id, 'formed', actor, {
                'alert_id': alert.id, 'anchor_date': alert.anchor_date,
                'trigger_date': alert.trigger_date, 'threshold': alert.threshold,
                'evidence': alert.evidence,
            }, alert.id)
            created += 1
        else:
            previous_trigger = alert.trigger_date
            alert.trigger_date = episode['trigger_date']
            alert.threshold = float(config.threshold)
            updated += 1
            if previous_trigger != alert.trigger_date:
                _event(session, config.id, 'recalculated', actor, {
                    'alert_id': alert.id,
                    'note': '连续段重建后触发日变化，预警沿用原记录',
                    'trigger_date_before': previous_trigger,
                    'trigger_date_after': alert.trigger_date,
                }, alert.id)
        _apply_episode(session, config, metric, alert, episode, actor)
    for alert in live:
        if alert.id not in claimed:
            _revoke(session, alert, actor, '更正或口径/阈值变化后，连续三个已评日低于阈值不再成立，预警撤销')
            revoked += 1
    session.flush()
    return {'formed': created, 'updated': updated, 'revoked': revoked}


def recompute_counts(evals):
    run = 0
    for evaluation in evals:
        if evaluation.status == 'below':
            run += 1
        else:
            run = 0
        evaluation.consecutive_below = run


def sweep_monitor(session, monitor_id, today=None, actor='worker'):
    """补齐应评估日、重算变化日、重建连续段。事务由调用方提交。"""
    config = session.query(MonitorConfig).filter_by(id=monitor_id).with_for_update().one_or_none()
    if not config:
        return {'monitor_id': monitor_id, 'skipped': 'not_found'}
    if not config.enabled:
        return {'monitor_id': monitor_id, 'skipped': 'disabled'}
    metric = session.get(Metric, config.metric_id)
    if not metric:
        _event(session, config.id, 'recalculated', actor, {
            'error': '绑定的口径版本不存在，无法评估，等待配置修正',
        })
        return {'monitor_id': monitor_id, 'skipped': 'metric_missing'}
    today = today or today_shanghai()
    due = due_dates(config, today)
    if not due:
        return {'monitor_id': monitor_id, 'due': 0, 'changed': 0, 'alerts': {}}
    facts_from = due[0] - timedelta(days=WINDOW_DAYS - 1)
    facts = _facts_in_window(session, facts_from, today)
    changed = []
    for day in due:
        _, did_change = evaluate_date(session, config, metric, day, facts)
        if did_change:
            changed.append(day.isoformat())
    session.flush()
    evals = session.query(MonitorEvaluation).filter(
        MonitorEvaluation.monitor_id == config.id,
        MonitorEvaluation.eval_date >= config.start_date,
    ).order_by(MonitorEvaluation.eval_date).all()
    recompute_counts(evals)
    result = reconcile(session, config, metric_snapshot(metric), evals, actor)
    return {
        'monitor_id': monitor_id, 'due': len(due),
        'evaluated': len(evals), 'changed': len(changed),
        'changed_dates': changed, 'alerts': result,
    }


def sweep_all(Session, today=None, actor='worker'):
    with Session() as session:
        ids = [r.id for r in session.query(MonitorConfig.id).filter_by(enabled=True).all()]
    results = []
    for monitor_id in ids:
        with Session() as session:
            try:
                results.append(sweep_monitor(session, monitor_id, today, actor))
                session.commit()
            except Exception:
                session.rollback()
                logging.exception('monitor sweep failed: %s', monitor_id)
    return results


def confirm_alert(session, alert_id, actor, note=''):
    alert = session.query(MonitorAlert).filter_by(id=alert_id).with_for_update().one_or_none()
    if not alert:
        return None, 'not_found'
    if alert.status == 'confirmed':
        return alert, 'already_confirmed'
    if alert.status == 'recovered':
        return alert, 'recovered'
    if alert.status == 'revoked':
        return alert, 'revoked'
    evals = session.query(MonitorEvaluation).filter(
        MonitorEvaluation.monitor_id == alert.monitor_id,
        MonitorEvaluation.eval_date >= alert.anchor_date,
        MonitorEvaluation.eval_date <= alert.trigger_date,
    ).order_by(MonitorEvaluation.eval_date).all()
    basis = {
        'version': VERSION,
        'at': now_shanghai(),
        'alert': {
            'id': alert.id, 'monitor_id': alert.monitor_id,
            'anchor_date': alert.anchor_date, 'trigger_date': alert.trigger_date,
            'threshold': alert.threshold, 'status': alert.status,
        },
        'evaluations': [{
            'eval_date': e.eval_date, 'status': e.status, 'value': e.value,
            'numerator': e.numerator, 'denominator': e.denominator,
            'threshold': e.threshold, 'input_checksum': e.input_checksum,
            'evidence': e.evidence,
        } for e in evals],
        'formation_evidence': alert.evidence,
    }
    alert.status = 'confirmed'
    alert.confirmed_by = actor
    alert.confirmed_at = basis['at']
    alert.confirmed_evidence = basis
    alert.updated = basis['at']
    _event(session, alert.monitor_id, 'confirmed', actor, {
        'alert_id': alert.id, 'note': note, 'evidence': basis,
    }, alert.id)
    session.flush()
    return alert, 'confirmed'


def monitor_summary(session, config, today=None):
    today = today or today_shanghai()
    due = due_dates(config, today)
    evals = session.query(MonitorEvaluation).filter(
        MonitorEvaluation.monitor_id == config.id,
        MonitorEvaluation.eval_date >= config.start_date,
    ).order_by(MonitorEvaluation.eval_date).all()
    by_date = {e.eval_date: e for e in evals}
    pending = [d.isoformat() for d in due if d.isoformat() not in by_date]
    latest = by_date.get(today.isoformat()) or (evals[-1] if evals else None)
    alerts = session.query(MonitorAlert).filter_by(monitor_id=config.id).all()
    statuses = {}
    for alert in alerts:
        statuses[alert.status] = statuses.get(alert.status, 0) + 1
    latest_alert = max(alerts, key=lambda a: a.id) if alerts else None
    return {
        'today': today.isoformat(),
        'start_date': config.start_date,
        'due_count': len(due),
        'evaluated_count': len(due) - len(pending),
        'pending_count': len(pending),
        'pending_dates': pending[:60],
        'pending_truncated': len(pending) > 60,
        'latest': evaluation_out(latest) if latest else None,
        'alert_counts': statuses,
        'active_alerts': statuses.get('open', 0) + statuses.get('confirmed', 0),
        'latest_alert': alert_out(latest_alert) if latest_alert else None,
    }


def evaluation_out(row):
    if not row:
        return None
    return {
        'id': row.id, 'monitor_id': row.monitor_id, 'eval_date': row.eval_date,
        'status': row.status, 'value': row.value, 'numerator': row.numerator,
        'denominator': row.denominator, 'threshold': row.threshold,
        'consecutive_below': row.consecutive_below, 'revision': row.revision,
        'input_checksum': row.input_checksum, 'error': row.error,
        'calculated': row.calculated,
    }


def alert_out(alert, detail=False):
    if not alert:
        return None
    data = {
        'id': alert.id, 'monitor_id': alert.monitor_id, 'metric_id': alert.metric_id,
        'anchor_date': alert.anchor_date, 'trigger_date': alert.trigger_date,
        'start_date': alert.start_date, 'end_date': alert.end_date,
        'status': alert.status, 'threshold': alert.threshold,
        'confirmed_by': alert.confirmed_by, 'confirmed_at': alert.confirmed_at,
        'revoked': alert.revoked, 'revoke_reason': alert.revoke_reason,
        'created': alert.created, 'updated': alert.updated,
        'has_confirmed_evidence': alert.confirmed_evidence is not None,
    }
    if detail:
        data['evidence'] = alert.evidence
        data['confirmed_evidence'] = alert.confirmed_evidence
    return data


def event_out(event):
    return {
        'id': event.id, 'monitor_id': event.monitor_id, 'alert_id': event.alert_id,
        'action': event.action, 'actor': event.actor, 'detail': event.detail,
        'created': event.created,
    }
