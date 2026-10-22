"""Reuse the resident read-only retrieval service; never request model generation."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote

import httpx


class ExistingKnowledge:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(base_url="http://127.0.0.1:8894", timeout=150, follow_redirects=False)

    def get(self, path: str, **params) -> dict:
        response = self.client.get(path, params=params, timeout=10)
        response.raise_for_status()
        return response.json()

    def status(self) -> dict:
        return self.get("/api/v2/unified/status")

    def features(self, texts, question=""):
        response=self.client.post('/api/v2/unified/local-features',headers={'X-Platform-Request':'1'},json={'texts':texts,'question':question})
        response.raise_for_status()
        return response.json()

    def source_snapshot(self,source_id):
        response=self.client.get('/api/v2/unified/source-snapshot/'+quote(source_id,safe=''),headers={'X-Platform-Request':'1'},timeout=150)
        response.raise_for_status()
        return response.json()

    def sources(self, query="", offset=0, limit=50, file_type="") -> dict:
        return self.get("/api/v2/knowledge/sources", query=query, offset=offset, limit=limit, file_type=file_type)

    def evidence(self, source_id: str) -> dict:
        return self.get(f"/api/v2/knowledge/sources/{quote(source_id, safe='')}/evidence", limit=100)

    def catalog_source(self, source_id: str) -> dict:
        offset = 0
        while True:
            page = self.sources(offset=offset, limit=100)
            row = next((s for s in page["items"] if s["source_id"] == source_id), None)
            if row:
                return row
            offset += len(page["items"])
            if not page["items"] or offset >= page["total"]:
                raise KeyError(source_id)

    @staticmethod
    def version_current(source: dict) -> bool:
        path = source.get("external_path") or source.get("source_path")
        expected = source.get("external_hash") or source.get("current_hash")
        if not path or not expected:
            return False
        try:
            digest = hashlib.sha256()
            with Path(path).open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest() == expected
        except OSError:
            return False

    def retrieve(self, question: str, request_id: str) -> dict:
        # sources mode exits before every provider branch, even if upstream generation is later enabled.
        response = self.client.post("/api/v2/assisted/query", headers={"Origin": "http://127.0.0.1:8894"}, json={
            "question": question, "mode": "sources", "trial_user": "reviewer-001",
            "conversation_id": "platform-" + request_id, "request_id": request_id,
        })
        response.raise_for_status()
        result = None
        for frame in response.text.replace("\r\n", "\n").split("\n\n"):
            payload = "\n".join(line[5:].lstrip() for line in frame.splitlines() if line.startswith("data:"))
            if payload:
                event = json.loads(payload)
                if event.get("type") == "result":
                    result = event["result"]
        if result is None:
            raise ValueError("检索服务未返回完整结果，不能当作已经回答。")
        return result


def source_extract(result: dict, question: str = '') -> dict:
    from .concise_extract import concise_text,readable_citations
    cards = readable_citations(result.get("citations", []))
    result={**result,'citations':cards}
    if result.get("answer_status") != "SOURCES_ONLY" or not cards:
        return {**result, "generation_mode": result.get('generation_mode', "NO_GENERATION")}
    primary = [c for c in cards if c.get("answer_usage") == "PRIMARY"]
    if not primary:
        return {**result, "answer_status": "SOURCES_ONLY", "answer": "本次只返回相关原文线索，尚未取得可用于本题答复的主证据。", "generation_mode": "NO_GENERATION"}
    from .source_field_answer import area_answer,subject
    field=area_answer(result,question or result.get('question',''))
    if field is not None:return {**result,**field}
    target=result.get('debug',{}).get('personnel_scope_audit',{}).get('target','')
    extracts=[(c, *concise_text(c['excerpt'],question or result.get('question',''),target)) for c in primary]
    query=question or result.get('question','')
    if (not target and subject(query) and re.search(r'多少|几人|几位|人数|金额|合计|计算|占比',query)
            and all(method=='FULL_SOURCE_FALLBACK' for _,_,method in extracts)):
        return {**result,'answer_status':'FIELD_EXTRACTION_REQUIRED','status_label':'相关原文已找到 · 所问字段尚未提取',
                'answer':'已找到相关原文，但尚未准确提取所问数值字段。本次只提供原文线索，不把整段当作直接答案；这不表示原文没有该信息。',
                'citations':[{**c,'answer_usage':'BACKGROUND'} for c in cards],'claims':[],
                'generation_mode':'NO_GENERATION','field_audit':{'reason':'PROJECT_NUMERIC_FIELD_NOT_EXTRACTED'}}
    answer = "\n\n".join(f'{text}\n[{c["citation_id"]}]' for c,text,_ in extracts)
    shortened=any(method!='FULL_SOURCE_FALLBACK' for _,_,method in extracts)
    return {**result, "answer_status": "SOURCE_EXTRACT", "status_label": "简明原文要点 · 待核对" if shortened else "原文摘录答复 · 待核对", "answer": answer,
            "generation_mode": "LOCAL_EXTRACTIVE_SUMMARY_NO_MODEL" if shortened else "VERBATIM_SOURCE_EXTRACT",
            "summary_audit":[{'citation_id':c['citation_id'],'method':method,'source_chars':len(c['excerpt']),'display_chars':len(text)} for c,text,method in extracts],
            "notice": "本地按原文结构提取要点或展示原表字段；条件或结构不清时保留全文，完整证据见下方引用。未运行生成模型，未自动业务审核；是否完整回答问题仍需核对。"}
