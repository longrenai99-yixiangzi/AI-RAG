"""Incremental ingestion and approved evidence retrieval, sharing the resident BGE models."""
import base64
import copy
import hashlib
import json
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np

from app.bm25 import BM25Index
from app.chunker import chunk_blocks
from app.domain import Chunk
from app.parsers import parse_file
from app.retrieval.named_source_scope import named_titles
from app.retrieval.section_scope import section_scope
from app.answer_engine.question_scope import personnel_count_query
from .knowledge_store import _now
from .platform_generation import file_hash
from .platform_store import PlatformConflict


class PlatformLifecycle:
    def __init__(self, store, existing):
        self.store, self.existing = store, existing
        self.root = store.path.parent / "runtime"
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="platform-import")
        self.lock = threading.RLock()
        def recover(state):
            for job in state["jobs"].values():
                if job["status"] in {"QUEUED", "PROCESSING"}:
                    job.update(status="INTERRUPTED", error="服务曾中断，需手动重试。")
            for preview in state['generations'].values():
                if preview['status']=='EXECUTING':preview['status']='INTERRUPTED_SPENT'
            for run in state['query_runs'].values():
                if run.get('status')=='RUNNING':run.update(status='INTERRUPTED',result={'answer_status':'INTERRUPTED','answer':'上次服务中断，本题未处理完成。可重新提交新问题，不会自动重试或再次调用模型。','citations':[]})
        store._mutate(recover)

    def close(self):
        self.pool.shutdown(wait=True)

    def _json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temp.replace(path)

    def enqueue(self, name, data, actor, existing_source_id=""):
        if (not name or Path(name).name != name or re.search(r'[\\/:<>"|?*]', name) or name.endswith((".", " "))
            or name.split('.')[0].upper() in {'CON','PRN','AUX','NUL', *(f'COM{i}' for i in range(1,10)), *(f'LPT{i}' for i in range(1,10))}):
            raise ValueError("文件名不合法。")
        if Path(name).suffix.lower() not in {".md", ".pdf", ".docx", ".xlsx", ".pptx"}:
            raise ValueError("支持Markdown、PDF、Word、Excel和PowerPoint文件。")
        if not data or len(data) > 25*1024*1024:
            raise ValueError("单份文件须非空且不超过25MB。")
        digest = hashlib.sha256(data).hexdigest()
        material_id = "MAT_" + hashlib.sha256(name.casefold().encode()).hexdigest()[:20]
        key = "JOB_" + hashlib.sha256((material_id + digest).encode()).hexdigest()[:24]
        path = self.root / "files" / material_id / digest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
            temp.write_bytes(data)
            temp.replace(path)
        if file_hash(path) != digest:
            raise ValueError("文件版本校验失败。")
        def action(state):
            if key in state["jobs"]:
                return copy.deepcopy(state["jobs"][key]), False
            row = {"job_id": key, "material_id": material_id, "file_name": name, "sha256": digest, "input_path": str(path),
                   "status": "QUEUED", "actor": actor, "created_at": _now(), "existing_source_id": existing_source_id,
                   "method": "REUSE_EXISTING_CHUNKS" if existing_source_id else "EXISTING_PARSER", "attempts": 0}
            state["jobs"][key] = row
            self.store._event(state, "增量入库任务建立", key, actor)
            return copy.deepcopy(row), True
        row, created = self.store._mutate(action)
        if created:
            self.pool.submit(self.process, key)
        return row

    def process(self, key):
        def start(state):
            job = state["jobs"][key]
            if job["status"] != "QUEUED":
                return None
            job.update(status="PROCESSING", attempts=job["attempts"]+1, error="")
            return copy.deepcopy(job)
        job = self.store._mutate(start)
        if not job:
            return
        try:
            path = Path(job["input_path"])
            if file_hash(path) != job["sha256"]:
                raise ValueError("上传副本版本已改变，未使用旧索引。")
            if path.suffix.lower()=='.md':
                from app.ingestion.normalization.markdown_normalizer import is_source_reference_note,is_navigation_only_note
                content=path.read_text(encoding='utf-8-sig')
                if is_source_reference_note(content) or is_navigation_only_note(content):
                    raise ValueError("仅链接登记卡不能作为正文入库。")
            if job["existing_source_id"]:
                snapshot = self.existing.source_snapshot(job["existing_source_id"])
                records = snapshot["records"]
                if any(r["source_version"] != job["sha256"] for r in records):
                    raise ValueError("已有片段版本与文件不一致。")
                vectors, model = snapshot["vectors"], snapshot["model_digest"]
            else:
                parsed = parse_file(path, 25)
                if parsed.parse_status != "parsed" or not parsed.blocks:
                    raise ValueError(f"未取得可用正文：{parsed.parse_status}；扫描件可能需要OCR。")
                chunks = chunk_blocks(parsed.blocks)
                records = [{"evidence_id": c.chunk_id, "text": c.text, "heading_path": c.heading_path, "location": c.location} for c in chunks]
                if not records or len(records) > 3000:
                    raise ValueError("正文为空或超过单份3000片段上限，未截断入库。")
                vectors, model = [], None
                for i in range(0, len(records), 16):
                    features = self.existing.features([r["text"] for r in records[i:i+16]])
                    if model and model != features["model_digest"]:
                        raise ValueError("编码模型在入库期间变化。")
                    model = features["model_digest"]
                    vectors.extend(features["vectors"])
            matrix = np.asarray(vectors, dtype=np.float32)
            if matrix.shape != (len(records), 1024) or not np.isfinite(matrix).all() or np.any(np.linalg.norm(matrix, axis=1) < .001):
                raise ValueError("增量向量数量、维度或数值异常。")
            if file_hash(path) != job["sha256"]:
                raise ValueError("入库期间文件发生变化。")
            sid = "INC_" + key[4:]
            records = [{**r, "source_id": sid, "source_path": str(path), "source_version": job["sha256"], "file_name": job["file_name"]} for r in records]
            package = self.root / "index" / (key + ".json")
            self._json(package, {"records": records, "vectors": vectors, "model_digest": model})
            def finish(state):
                state["jobs"][key].update(status="READY", source_id=sid, package_path=str(package), package_hash=file_hash(package), chunk_count=len(records), model_digest=model)
                self.store._event(state, "增量解析与编码完成，等待加入检索", key, job["actor"])
            self.store._mutate(finish)
        except Exception as error:
            def failed(state):
                state["jobs"][key].update(status="FAILED", error=f"{type(error).__name__}: {error}")
            self.store._mutate(failed)

    def job_action(self, key, action, actor):
        def mutate(state):
            row = state["jobs"][key]
            if action == "retry":
                if row["status"] not in {"FAILED", "INTERRUPTED"}:
                    raise PlatformConflict("仅失败或中断任务可以重试。")
                row["status"] = "QUEUED"
            elif action == "cancel":
                if row["status"] not in {"QUEUED", "FAILED", "INTERRUPTED"}:
                    raise PlatformConflict("运行中任务不能取消，避免留下半成品。")
                row["status"] = "CANCELLED"
            elif action == "activate":
                if row["status"] not in {"READY", "WITHDRAWN", "SUPERSEDED"} or file_hash(row["input_path"]) != row["sha256"] or file_hash(row["package_path"]) != row["package_hash"]:
                    raise PlatformConflict("任务未就绪或版本已变，不能加入检索。")
                previous = state["materials"].get(row["material_id"])
                if previous and previous["job_id"] != key:
                    old = state["jobs"][previous["job_id"]]
                    old["status"] = "SUPERSEDED"
                    self._invalidate(state, old["source_id"])
                row["status"] = "ACTIVE"
                source=state['sources'].get(row['source_id'])
                if source and source.get('status')!='REGISTERED':
                    if (not source.get('external_bound') or source.get('external_hash')!=row['sha256']
                            or Path(source.get('external_path','')).resolve()!=Path(row['input_path']).resolve()):
                        raise PlatformConflict('来源登记与受管版本不一致，未恢复旧来源。')
                    source.update(status='REGISTERED',revision=source['revision']+1)
                state["materials"][row["material_id"]] = {"material_id": row["material_id"], "job_id": key, "source_id": row["source_id"], "file_name": row["file_name"], "status": "ACTIVE"}
            elif action == "withdraw":
                if row["status"] != "ACTIVE":
                    raise PlatformConflict("此版本不在检索中。")
                row["status"] = "WITHDRAWN"
                state["materials"][row["material_id"]]["status"] = "WITHDRAWN"
                self._invalidate(state, row["source_id"])
            else:
                raise ValueError("未知任务操作。")
            self.store._event(state, "入库任务:"+action, key, actor)
            return copy.deepcopy(row)
        row = self.store._mutate(mutate)
        if action == "retry":
            self.pool.submit(self.process, key)
        return row

    @staticmethod
    def _invalidate(state, sid):
        if sid in state["sources"]:
            state["sources"][sid].update(status="WITHDRAWN", revision=state["sources"][sid]["revision"]+1)
        for row in state["knowledge"].values():
            if row["source_id"] == sid and row["status"] == "ACTIVE":
                row.update(status="REVIEW_REQUIRED", revision=row["revision"]+1)

    def catalog(self, sid=None):
        jobs = self.store.snapshot()["jobs"]
        return [{"source_id": j["source_id"], "file_name": j["file_name"], "source_path": j["input_path"], "current_hash": j["sha256"],
                 "body_status": "增量正文·待业务核对", "chunk_count": j["chunk_count"], "version_note": "独立增量版本，不覆盖原件与原索引。", "status": j["status"]}
                for j in jobs if j.get("source_id") and (j["source_id"] == sid if sid else j["status"] == "ACTIVE")]

    def package(self, job):
        if file_hash(job["package_path"]) != job["package_hash"] or file_hash(job["input_path"]) != job["sha256"]:
            raise ValueError("增量文件或索引校验失败，停止使用。")
        return json.loads(Path(job["package_path"]).read_text(encoding="utf-8"))

    def retrieve(self, question):
        count_query = personnel_count_query(question)
        snapshot = self.store.snapshot()
        records, vectors, model = [], [], None
        for job in snapshot["jobs"]:
            if job["status"] != "ACTIVE":
                continue
            try:
                package = self.package(job)
            except (OSError,ValueError):
                def invalidate(state):
                    state['jobs'][job['job_id']].update(status='FAILED',error='增量文件或索引已变，已停止检索，需核查后手动重试。')
                    self._invalidate(state,job['source_id'])
                    if job['material_id'] in state['materials']:state['materials'][job['material_id']]['status']='WITHDRAWN'
                self.store._mutate(invalidate)
                continue
            if model and model != package["model_digest"]:
                raise ValueError("增量编码模型不一致。")
            model = package["model_digest"]
            records.extend(package["records"]); vectors.extend(package["vectors"])
        for knowledge in snapshot["knowledge"]:
            if knowledge["status"] != "ACTIVE" or not knowledge.get("origin_citation"):
                continue
            source = self.store.source(knowledge["source_id"])
            if source["status"] != "REGISTERED" or source["revision"] != knowledge["source_revision"] or not self.existing.version_current(source):
                continue
            text = knowledge["content"]
            cache = self.root / "index" / ("KN_" + hashlib.sha256(text.encode()).hexdigest() + ".json")
            if not cache.exists():
                self._json(cache, self.existing.features([text]))
            features = json.loads(cache.read_text(encoding="utf-8"))
            if model and model != features["model_digest"]:
                raise ValueError("审核知识向量模型与增量模型不同。")
            model = features["model_digest"]
            c = knowledge["origin_citation"]
            records.append({"evidence_id": knowledge["knowledge_id"], "source_id": c["source_id"], "source_path": source["external_path"], "source_version": source["external_hash"],
                            "text": text, "file_name": c["file_name"], "heading_path": knowledge["source_location"] if "source_location" in knowledge else knowledge["location"], "location": {"section": knowledge["location"]}, "knowledge_id": knowledge["knowledge_id"], "applicability": knowledge["applicability"]})
            vectors.extend(features["vectors"])
        if not records:
            return []
        titles = named_titles(question)
        selected = [i for i,r in enumerate(records) if (not titles or any(t.casefold().removesuffix(Path(t).suffix.casefold()) in r["file_name"].casefold() for t in titles)) and not any(v == "MISMATCH" for v in section_scope(question,r).values())]
        if not selected:
            return []
        features = self.existing.features([question])
        if features["model_digest"] != model:
            raise ValueError("查询编码模型已变，需重新编码增量库。")
        matrix = np.asarray(vectors, dtype=np.float32); q = np.asarray(features["vectors"][0], dtype=np.float32)
        dense = matrix @ q / (np.linalg.norm(matrix, axis=1)*np.linalg.norm(q))
        bm = BM25Index(Path("UNSAVED_PLATFORM_INCREMENT"))
        bm.build([Chunk(str(i),r["source_id"],i,r["source_path"],r["file_name"],r["text"],r.get("heading_path", ""),r.get("location",{})) for i,r in enumerate(records)])
        sparse = {int(i): score for i,score in bm.search(question,len(records))}
        fusion = {}
        for order in (sorted(selected,key=lambda i:-dense[i]), sorted(selected,key=lambda i:-sparse.get(i,0))):
            for rank,i in enumerate(order,1):fusion[i]=fusion.get(i,0)+1/(60+rank)
        chosen=sorted(fusion,key=lambda i:-fusion[i])[:12]
        scores=self.existing.features([records[i]["text"] for i in chosen],question)["scores"]
        ranked=[(i,score) for i,score in sorted(zip(chosen,scores),key=lambda p:-p[1]) if score>=0]
        if ranked and not (titles and len(titles)>1):
            top=records[ranked[0][0]]
            ranked=[(i,s) for i,s in ranked if (records[i]['source_id'],records[i].get('heading_path'))==(top['source_id'],top.get('heading_path'))]
        return [{**records[i],"reranker_score":float(score),"answer_usage":"BACKGROUND" if count_query else "PRIMARY"} for i,score in ranked][:3]
