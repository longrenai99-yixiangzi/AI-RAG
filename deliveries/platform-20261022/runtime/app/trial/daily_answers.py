"""One explicitly approved, version-bound local trial; reuse the existing generation protocol."""
import copy
import hashlib
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

import httpx

from app.answer_engine.llm.reviewed_packet_provider import wire
from .platform_generation import file_hash

PRICE_URL='https://api-docs.deepseek.com/quick_start/pricing/'
DIRECT_MODES={'HUMAN_REVIEWED_EXACT_QUESTION','VERIFIED_SCALAR_NO_MODEL','VERIFIED_TABLE_SCHEMA_NO_MODEL',
              'LOCAL_PROJECT_AREA_FIELD_NO_MODEL','LOCAL_PROJECT_MONEY_FIELD_NO_MODEL','VERIFIED_COMPLETE_LIST_NO_MODEL','REVIEWED_TABLE_FIELDS_NO_MODEL','NATIVE_FLOW_RELATION_NO_MODEL','SOURCE_BOUND_SPAN_NO_MODEL','REVIEWED_NATIVE_CLAUSE_NO_MODEL'}


class DailyAnswers:
    def __init__(self, store, generation, existing, policy, *, clock=None, price_reader=None):
        self.store,self.generation,self.existing=store,generation,existing
        self.policy=copy.deepcopy(policy)
        policy=self.policy
        for key,maximum in [('valid_days',7),('max_requests',1000),('max_budget_cents',100000),('max_request_cents',100),('max_request_bytes',32768)]:
            if type(policy.get(key)) is not int or not 1<=policy[key]<=maximum:raise ValueError('日常模型策略上限不正确。')
        if (policy.get('schema_version')!=1 or policy.get('model')!='deepseek-v4-flash'
                or not policy.get('policy_id') or not re.fullmatch('[a-f0-9]{64}',policy.get('candidate_hash',''))
                or not isinstance(policy.get('sources'),list) or not 1<=len(policy['sources'])<=20):
            raise ValueError('日常模型策略不完整。')
        self.sources={s['source_id']:s for s in policy['sources']}
        if len(self.sources)!=len(policy['sources']):raise ValueError('日常模型来源重复。')
        for s in self.sources.values():
            if (not s.get('display_file_name') or not Path(s['source_path']).is_absolute()
                    or not Path(s['original_path']).is_absolute()
                    or any(not re.fullmatch('[a-f0-9]{64}',s[k]) for k in ['source_version','original_version'])):
                raise ValueError('日常模型来源未绑定路径和版本。')
        price=policy['pricing']
        if price.get('source')!=PRICE_URL or not re.fullmatch('[a-f0-9]{64}',price.get('page_sha256','')):
            raise ValueError('日常模型没有官方价格依据。')
        for k in ['input_usd_per_million','output_usd_per_million','fx_ceiling']:
            value=Decimal(str(price[k]))
            if not value.is_finite() or value<=0:raise ValueError('日常模型核价不正确。')
        self.policy_hash=hashlib.sha256(json.dumps(policy,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.expires_at_limit=datetime.fromisoformat(policy['expires_at_limit']) if policy.get('expires_at_limit') else None
        if self.expires_at_limit is not None and self.expires_at_limit.tzinfo is None:raise ValueError('策略截止时间必须包含时区。')
        self.price_reader=price_reader or self._price_page
        self.price_lock=threading.Lock()
        self.verified_day=None

    @staticmethod
    def _price_page():
        with httpx.Client(timeout=20,follow_redirects=False) as client:
            response=client.get(PRICE_URL);response.raise_for_status();return response.content

    def _record(self):
        row=self.store._read().get('daily_answer_policy',{})
        return row if row.get('policy_sha256')==self.policy_hash else {}

    def _active(self,row):
        return bool(row.get('approved') and not row.get('paused') and self.clock()<datetime.fromisoformat(row['expires_at'])
                    and (self.expires_at_limit is None or self.clock()<self.expires_at_limit))

    def status(self):
        state=self.store._read();row=self._record();used=row.get('reservations',{})
        previous=state.get('daily_answer_policy',{})
        history=list(state.get('daily_answer_policy_history',{}).values())
        if previous and previous.get('policy_sha256')!=self.policy_hash:history.append(previous)
        return {'policy_sha256':self.policy_hash,'approved':bool(row.get('approved')),'active':self._active(row),
                'previous_policy_sha256':previous.get('policy_sha256') if previous and not row else None,
                'expired':bool(row.get('expires_at') and self.clock()>=datetime.fromisoformat(row['expires_at'])),
                'history':[{'policy_sha256':h['policy_sha256'],'expires_at':h['expires_at'],
                            'used_requests':len(h.get('reservations',{})),
                            'reserved_cny':sum(v['cents'] for v in h.get('reservations',{}).values())/100} for h in history],
                'expires_at':row.get('expires_at'),'valid_days':self.policy['valid_days'],
                'max_requests':self.policy['max_requests'],'used_requests':len(used),
                'max_budget_cny':self.policy['max_budget_cents']/100,
                'max_request_cny':self.policy['max_request_cents']/100,
                'material_count':len({s['original_path'] for s in self.sources.values()}),
                'reserved_cny':sum(x['cents'] for x in used.values())/100,
                'sources':[{'name':s['display_file_name'],'source_version':s['source_version']} for s in self.sources.values()],
                'notice':'仅在明确批准后自动组织白名单主证据。失败计次，不重试；预占额不等于实际账单。价格页改变或跨日无法核对则停止模型。'}

    def _versions(self):
        if self.existing.status()['candidate_hash']!=self.policy['candidate_hash']:raise ValueError('检索候选已变化，日常模型策略需重审。')
        disabled={s['source_id'] for s in self.store._read()['sources'].values() if s.get('status')!='REGISTERED'}
        if disabled.intersection(self.sources):raise ValueError('批准资料在平台已停用，日常模型停止。')
        for source in self.sources.values():
            for path,version in [('source_path','source_version'),('original_path','original_version')]:
                if file_hash(source[path])!=source[version]:raise ValueError('批准资料或原件版本已变化，日常模型停止。')

    def _price(self):
        day=self.clock().astimezone(timezone(timedelta(hours=8))).date().isoformat()
        with self.price_lock:
            expected={k:self.policy['pricing'][k] for k in ['input_usd_per_million','output_usd_per_million','fx_ceiling']}
            current=self.generation.pricing()
            if self.verified_day!=day or current['checked_on']!=day:
                if hashlib.sha256(self.price_reader()).hexdigest()!=self.policy['pricing']['page_sha256']:
                    raise ValueError('官方价格页已变化，暂停日常模型并重新核价。')
                self.generation.update_pricing(expected,'日常策略官方价格页核对')
                self.verified_day=day;current=self.generation.pricing()
            if current['checked_on']!=day or any(current[k]!=v for k,v in expected.items()):
                raise ValueError('核价日期或价格与批准策略不一致，未外发。')

    def approve(self,policy_hash,actor,*,previous_policy_hash=None):
        if policy_hash!=self.policy_hash:raise ValueError('策略内容已变化，请重新阅读。')
        if self.expires_at_limit is not None and self.clock()>=self.expires_at_limit:raise ValueError('策略限定截止时间已到，不能重新启用。')
        self._versions();self._price()
        def action(state):
            old=state.get('daily_answer_policy',{})
            history=state.get('daily_answer_policy_history',{})
            if self.policy_hash in history:raise ValueError('该策略已结束，不能重新启用或重置额度。')
            replacing=bool(old and old.get('policy_sha256')!=self.policy_hash)
            if replacing:
                if previous_policy_hash!=old.get('policy_sha256'):raise ValueError('续批需明确确认上一期策略，不能覆盖现有账本。')
                if self._active(old):raise ValueError('上一期仍在启用，请先暂停或等待到期后再续批。')
                if (any(r.get('status')=='RESERVED' for r in old.get('reservations',{}).values())
                        or any(g.get('status')=='EXECUTING' for g in state.get('generations',{}).values())
                        or any(r.get('status')=='RUNNING' for r in state.get('query_runs',{}).values())):
                    raise ValueError('仍有请求执行中或预占待对账，不能续批。')
                state.setdefault('daily_answer_policy_history',{})[old['policy_sha256']]=copy.deepcopy(old)
                old={}
            elif previous_policy_hash is not None:raise ValueError('续批须使用新的策略编号与新一期授权。')
            if old.get('approved'):
                if self.clock()>=datetime.fromisoformat(old['expires_at']):raise ValueError('策略已到期，不能恢复并重置额度。')
                old['paused']=False
            else:
                expiry=self.clock()+timedelta(days=self.policy['valid_days'])
                if self.expires_at_limit is not None:expiry=min(expiry,self.expires_at_limit)
                old={'policy_sha256':self.policy_hash,'approved':True,'paused':False,'approved_at':self.clock().isoformat(),
                     'expires_at':expiry.isoformat(),'actor':actor,'reservations':{},
                     'limits':{k:self.policy[k] for k in ['policy_id','max_requests','max_budget_cents','max_request_cents','valid_days']}}
            state['daily_answer_policy']=old
            self.store._event(state,'续批限额日常模型' if replacing else '批准或恢复限额日常模型',self.policy_hash,actor)
        self.store._mutate(action)
        return self.status()

    def pause(self,actor):
        def action(state):
            if state.get('daily_answer_policy',{}).get('policy_sha256')==self.policy_hash:
                state['daily_answer_policy']['paused']=True
                self.store._event(state,'暂停日常模型',self.policy_hash,actor)
        self.store._mutate(action)
        return self.status()

    def apply(self,run_id):
        run=self.store.query_run(run_id);result=run.get('result',{})
        if any(run_id in h.get('reservations',{}) for h in [self.store._read().get('daily_answer_policy',{}),*self.store._read().get('daily_answer_policy_history',{}).values()]):return run
        def local(route,notice):
            return self.store.finish_run(run_id,{**result,'daily_model':{'route':route,'notice':notice}},error=run['status']=='ERROR' or route=='OUTCOME_UNKNOWN')
        from app.retrieval.complete_lists import enforce_complete_list
        result=enforce_complete_list(run['question'],result)
        if result.get('answer_status')=='LIST_COVERAGE_REQUIRED':
            return local('LIST_COVERAGE_REQUIRED','完整清单尚未核齐，本次不调用模型。')
        from app.retrieval.evidence_applicability import enforce_applicability
        checked=enforce_applicability(run['question'],result)
        if checked.get('answer_status')=='SCOPE_CLARIFICATION_REQUIRED':
            result=checked
            return local('SCOPE_CLARIFICATION_REQUIRED','需要先明确资料依据或项目范围，本次未调用模型。')
        native=result.get('summary_audit',[])
        if (result.get('generation_mode') in DIRECT_MODES or result.get('support_check')=='EXACT_NATIVE_UNIT'
                or native and all(x.get('method') in {'NATIVE_ROLE_COUNT_CLAUSE','NATIVE_SINGLE_ROW_FIELDS'} for x in native)):
            return local('LOCAL_DIRECT','审核答案或明确字段直接返回，本次不调用模型。')
        if run['status']!='COMPLETED' or result.get('answer_status') not in {'SOURCE_EXTRACT','SOURCES_ONLY'}:
            return local('NO_SUPPORTED_EVIDENCE','本题证据或范围未核定，不调用模型补猜。')
        primary=[c for c in result.get('citations',[]) if c.get('answer_usage')=='PRIMARY']
        if not primary:return local('NO_SUPPORTED_EVIDENCE','没有可用于本题答复的主证据，未外发。')
        for c in primary:
            s=self.sources.get(c['source_id'])
            if (not s or c['source_version']!=s['source_version'] or Path(c['source_path']).resolve()!=Path(s['source_path']).resolve()):
                return local('OUTSIDE_APPROVED_SCOPE','主证据超出本次批准的资料版本，未外发。')
        if not self._active(self._record()):return local('NOT_ACTIVE','日常模型尚未批准、已暂停或已到期，本次保留本地结果。')
        try:
            self._versions();self._price()
            preview=self.generation.prepare(run_id,'CONCISE_V1',primary_only=True)
            if sum(len(u['text']) for u in preview['units'])>6000 or len(wire(preview['body']).encode())>self.policy['max_request_bytes']:
                raise ValueError('本题主证据过长，未外发；请缩小问题范围。')
            cents=int((Decimal(str(preview['estimated_ceiling_cny']))*100).to_integral_value(rounding=ROUND_CEILING))
            def reserve(row):
                self._versions();self._price()
                def action(state):
                    policy=state.get('daily_answer_policy',{})
                    if policy.get('policy_sha256')!=self.policy_hash or not self._active(policy):raise ValueError('日常模型批准状态已变化，未外发。')
                    if row['pricing_version']!=self.generation.pricing()['version']:raise ValueError('核价版本变化，未外发。')
                    used=policy['reservations']
                    if run_id in used:raise ValueError('本题已经预占过模型请求，不能重试。')
                    if any(v['status']=='RESERVED' for v in used.values()):raise ValueError('已有模型请求处理中或状态待对账，未追加调用。')
                    if len(used)>=self.policy['max_requests'] or cents>self.policy['max_request_cents'] or sum(v['cents'] for v in used.values())+cents>self.policy['max_budget_cents']:
                        raise ValueError('日常模型次数或预占预算已到上限，未外发。')
                    used[run_id]={'cents':cents,'status':'RESERVED','preview_id':row['preview_id'],'packet_sha256':row['packet_sha256'],'at':self.clock().isoformat()}
                    state['query_runs'][run_id]['status']='RUNNING'
                self.store._mutate(action)
            saved=self.generation.run(preview['preview_id'],preview['packet_sha256'],run['actor'],query_run_id=run_id,before_send=reserve)
            try:self._versions()
            except (ValueError,OSError,httpx.HTTPError):
                saved=self.store.finish_run(run_id,{'answer_status':'SOURCE_VERSION_UNCONFIRMED',
                    'answer':'生成结束后无法确认批准资料和检索版本仍有效，本题结果未采用；不自动重试。',
                    'citations':[],'generation_mode':'MODEL_RESULT_NOT_CURRENT'},error=True)
            def finish(state):
                policy=state.get('daily_answer_policy',{})
                reservation=policy.get('reservations',{}).get(run_id)
                if reservation:reservation['status']='COMPLETED' if saved['status']=='COMPLETED' else 'FAILED_COUNTED'
                saved['result']['daily_model']={'route':'MODEL_ATTEMPT' if reservation else 'NOT_SENT',
                    'notice':'按限额策略执行一次；保守预占已保留，失败不自动重试。' if reservation else '本次未取得预占额度，未发送模型请求。',
                    'reserved_cny':cents/100 if reservation else 0}
                state['query_runs'][run_id]=copy.deepcopy(saved)
            self.store._mutate(finish)
            return saved
        except (ValueError,OSError,httpx.HTTPError) as error:
            if run_id in self._record().get('reservations',{}):
                return local('OUTCOME_UNKNOWN','本题已预占调用，结果保存或状态未确认；保留额度并停止追加调用，请先对账。')
            return local('NOT_SENT',str(error) if isinstance(error,ValueError) else '资料或官方价格暂时无法核对，未外发。')
