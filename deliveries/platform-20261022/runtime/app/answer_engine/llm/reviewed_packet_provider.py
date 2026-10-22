"""Use the existing request budget for a sealed, explicitly approved generation batch."""
import hashlib
import json
from pathlib import Path
import re
import threading
import time

from app.answer_engine.llm.llm_provider import GenerationResult
from app.answer_engine.llm.provider_runtime_guard import ProviderRequestBudget
from app.config import Settings
from app.llm import LLMError


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def wire(body):return json.dumps(body,ensure_ascii=False,separators=(',',':'))


class ReviewedPacketProvider:
    name='reviewed_packet_once'
    def __init__(self,packet,approval,out,*,transport=None,max_requests=2):
        self.available=False;self.last_error='本批尚未授权。';self.last_diagnostics={};self.lock=threading.Lock();self.out=Path(out)
        approval=Path(approval)
        if not approval.is_file():return
        decision=json.loads(approval.read_text(encoding='utf-8'));packet=Path(packet)
        if not isinstance(max_requests,int) or max_requests<1:return
        if decision.get('approved') is not True or decision.get('packet_sha256')!=sha(packet) or decision.get('max_requests')!=max_requests or decision.get('max_budget_cny')!=1:
            return
        self.tasks=json.loads(packet.read_text(encoding='utf-8'))
        if len(self.tasks)!=max_requests or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',t['id']) or hashlib.sha256(wire(t['body']).encode()).hexdigest()!=t['request_sha256'] for t in self.tasks):return
        self.transport=transport or self._post_once
        self.out.mkdir(parents=True,exist_ok=True)
        self.budget=ProviderRequestBudget(self.out/'request_budget.json',task_id=sha(packet),provider='DeepSeek',model=self.tasks[0]['body']['model'],max_real_requests=max_requests)
        self.budget.create_or_load();self.events=self.out/'request_attempts.jsonl';self.available=True;self.last_error=None

    @staticmethod
    def _post_once(body):
        import httpx
        settings=Settings.load()
        if not settings.api_key:raise LLMError('未配置模型鉴权，未发送请求。')
        with httpx.Client(timeout=60) as client:
            response=client.post('https://api.deepseek.com/chat/completions',headers={'Authorization':'Bearer '+settings.api_key,'Content-Type':'application/json'},content=wire(body).encode())
            response.raise_for_status();return response.json()

    def generate(self,system_prompt,user_prompt,*,temperature=0.1,max_tokens=4096):
        if not self.available:raise LLMError(self.last_error or '未授权')
        task=next((t for t in self.tasks if t['body']['messages']==[{'role':'system','content':system_prompt},{'role':'user','content':user_prompt}] and t['body']['temperature']==temperature and t['body']['max_tokens']==max_tokens),None)
        if task is None:raise LLMError('请求不在本批批准清单，已阻止修复或改写调用。')
        with self.lock:
            previous=[json.loads(line) for line in self.events.read_text(encoding='utf-8').splitlines()] if self.events.exists() else []
            if any(e['request_sha256']==task['request_sha256'] for e in previous):raise LLMError('该请求已经计次，已阻止自动重试。')
            if self.budget.reserve() is None:raise LLMError('本批请求次数已用完。')
            with self.events.open('a',encoding='utf-8') as stream:stream.write(json.dumps({'id':task['id'],'request_sha256':task['request_sha256'],'state':'RESERVED_BEFORE_HTTP'},ensure_ascii=False)+'\n')
        started=time.perf_counter()
        try:
            raw=self.transport(task['body'])
            (self.out/(task['id']+'_raw.json')).write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf-8')
            choice=raw['choices'][0];content=choice['message'].get('content')
            if not isinstance(content,str) or not content.strip():raise ValueError('empty response body')
            self.last_diagnostics={'finish_reason':choice.get('finish_reason'),'usage':raw.get('usage',{})}
            return GenerationResult(content,raw.get('id'),round((time.perf_counter()-started)*1000),self.last_diagnostics)
        except Exception as error:
            self.last_error='本次模型调用失败，已计次且不会自动重试：'+type(error).__name__
            raise LLMError(self.last_error) from None
