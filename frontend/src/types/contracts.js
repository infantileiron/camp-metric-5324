/** @typedef {{id:number,code:string,version:number,name:string,numerator:string,denominator:string,locked:boolean}} Metric */
/** @typedef {{id:number,class_code:string,day:string,mode:string,enrolled:number,attended:number,completed:number,refunds:number}} Fact */
/** @typedef {{id:number,metric_id:number,state:string,result:object,approval:string,note:string}} Snapshot */
/**
 * @typedef {{id:number,name:string,metric_id:number,threshold:number,start_date:string,enabled:boolean,metric:Metric,summary:object}} Monitor
 * @typedef {{id:number,monitor_id:number,eval_date:string,status:'below'|'ok'|'unknown'|'error',value:number|null,numerator:number|null,denominator:number|null,threshold:number,consecutive_below:number,revision:number,input_checksum:string,error:string}} MonitorEvaluation
 * @typedef {{id:number,monitor_id:number,metric_id:number,anchor_date:string,trigger_date:string,start_date:string,end_date:string|null,status:'open'|'confirmed'|'recovered'|'revoked',threshold:number,confirmed_by:string,confirmed_at:string,revoked:string,revoke_reason:string,has_confirmed_evidence:boolean,evidence?:object,confirmed_evidence?:object,events?:object[]}} MonitorAlert
 * @typedef {{id:number,monitor_id:number,alert_id:number|null,action:'formed'|'confirmed'|'recovered'|'revoked'|'reopened'|'recalculated',actor:string,detail:object,created:string}} MonitorEvent
 */
