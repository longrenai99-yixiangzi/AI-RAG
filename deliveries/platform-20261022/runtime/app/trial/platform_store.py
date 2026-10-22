"""Management workflow using the existing trial registry; no source IO or model calls."""
from __future__ import annotations

import copy
import json
import os
import uuid
from typing import Any

from .knowledge_store import TrialKnowledgeStore, _now


class PlatformConflict(ValueError):
    pass


class PlatformStore(TrialKnowledgeStore):
    # shortcut: one local worker owns this JSON registry; use a transactional DB before multi-worker deployment.
    def _mutate(self, action):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.with_suffix(".lock").open("a+b") as handle:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                return super()._mutate(action)
            finally:
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        if self.path.exists():
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("platform_schema") != 1:
                raise ValueError("平台状态格式不正确，已停止写入，请检查备份。")
            for key in ("sources", "knowledge", "candidates"):
                if not isinstance(value.get(key), dict):
                    raise ValueError("平台状态不完整，已停止写入。")
            value.setdefault("projects", {})
            value.setdefault("favorites", [])
            value.setdefault("recent", [])
            for key in ("materials", "jobs", "generations"):
                value.setdefault(key, {})
            return value
        return {**self._empty(), "platform_schema": 1, "candidates": {}, "projects": {}, "favorites": [], "recent": [], "materials": {}, "jobs": {}, "generations": {}}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            state = self._read()
        return {"sources": list(state["sources"].values()), "candidates": list(state["candidates"].values()),
                "knowledge": list(state["knowledge"].values()), "events": list(reversed(state["events"])),
                "projects": list(state["projects"].values()), "favorites": state["favorites"], "recent": state["recent"],
                "feedback": list(reversed(list(state["feedback"].values()))),
                "materials": list(state["materials"].values()), "jobs": list(reversed(list(state["jobs"].values()))),
                "generations": [{k:v for k,v in row.items() if k not in {"body","units","citations"}} for row in state["generations"].values()],
                "runs": [{k: row.get(k) for k in ("query_run_id", "question", "status", "recorded_at")} for row in reversed(list(state["query_runs"].values()))][:50]}

    @staticmethod
    def _expect(row: dict[str, Any], revision: int) -> None:
        if row["revision"] != revision:
            raise PlatformConflict("记录已经更新，请刷新后重新操作。")

    @staticmethod
    def _event(state: dict[str, Any], kind: str, target: str, actor: str, note: str = "") -> None:
        state["events"].append({"event_id": uuid.uuid4().hex, "type": kind, "target": target,
                                "actor": actor, "note": note, "at": _now()})

    def save_source(self, values: dict[str, Any], actor: str, *, source_id: str = "", revision: int = 0) -> dict[str, Any]:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            previous = state["sources"].get(source_id) if source_id else None
            if source_id and previous is None:
                raise KeyError(source_id)
            if previous:
                self._expect(previous, revision)
            key = source_id or "SRC_" + uuid.uuid4().hex[:20]
            if previous and previous.get("external_bound") and any(values.get(k) != previous.get(k) for k in ("name", "reference", "version_label")):
                raise PlatformConflict("绑定索引来源的名称、路径和版本不可覆盖，可维护产品线或停用。")
            row = {**(previous or {}), **values, "source_id": key, "revision": (previous or {}).get("revision", 0) + 1,
                   "status": "REGISTERED", "index_status": "NOT_CONNECTED", "updated_at": _now()}
            state["sources"][key] = row
            for knowledge in state["knowledge"].values():
                if knowledge["source_id"] == key and knowledge["status"] == "ACTIVE":
                    knowledge.update(status="REVIEW_REQUIRED", revision=knowledge["revision"] + 1)
            self._event(state, "来源登记" if not previous else "来源更新并暂停关联知识", key, actor)
            return copy.deepcopy(row)
        return self._mutate(action)

    def save_candidate(self, values: dict[str, Any], actor: str, *, candidate_id: str = "", revision: int = 0) -> dict[str, Any]:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            previous = state["candidates"].get(candidate_id) if candidate_id else None
            if candidate_id and previous is None:
                raise KeyError(candidate_id)
            if previous:
                self._expect(previous, revision)
                if previous["status"] == "PUBLISHED":
                    raise PlatformConflict("已发布候选不能覆盖，请复制为新候选。")
            source = state["sources"].get(values["source_id"])
            if not source:
                raise ValueError("请先登记来源。")
            project_id = values.get("project_id", "")
            if project_id and state["projects"].get(project_id, {}).get("status") != "ACTIVE":
                raise ValueError("项目不存在或已归档。")
            key = candidate_id or "C_" + uuid.uuid4().hex[:20]
            row = {**values, "candidate_id": key, "source_revision": source["revision"], "status": "DRAFT",
                   "revision": (previous or {}).get("revision", 0) + 1, "updated_at": _now(),
                   "checks": [], "reviewer": "", "review_note": ""}
            if previous and previous.get("source_id") == values["source_id"]:
                for field in ("origin_citation", "feedback_id", "origin_query_run_id"):
                    if field in previous:
                        row[field] = copy.deepcopy(previous[field])
            state["candidates"][key] = row
            self._event(state, "候选保存", key, actor)
            return copy.deepcopy(row)
        return self._mutate(action)

    @staticmethod
    def _checks(row: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
        source = state["sources"].get(row["source_id"], {})
        terms = row.get("required_terms") or []
        checks = [
            {"name": "来源仍有效", "passed": source.get("status") == "REGISTERED"},
            {"name": "来源版本与候选一致", "passed": source.get("revision") == row["source_revision"]},
            {"name": "问题、答案、摘录、定位与适用范围完整", "passed": all(str(row.get(k, "")).strip() for k in ("question", "answer", "excerpt", "location", "applicability"))},
            {"name": "关键事实同时出现在摘录和答案中", "passed": bool(terms) and all(t in row["excerpt"] and t in row["answer"] for t in terms)},
        ]
        if row.get("project_id"):
            checks.append({"name": "关联项目仍有效", "passed": state["projects"].get(row["project_id"], {}).get("status") == "ACTIVE"})
        if row.get("origin_citation"):
            citation = row["origin_citation"]
            checks.append({"name": "反馈证据仍来自原查询的同版摘录与定位", "passed": bool(row.get("excerpt")) and row["excerpt"] in citation["excerpt"] and row["location"] == citation["display_location"] and source.get("external_hash") == citation["source_version"]})
        return checks

    def save_project(self, values: dict[str, Any], actor: str, *, project_id: str = "", revision: int = 0) -> dict[str, Any]:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            previous = state["projects"].get(project_id) if project_id else None
            if project_id and previous is None:
                raise KeyError(project_id)
            if previous:
                self._expect(previous, revision)
            key = project_id or "P_" + uuid.uuid4().hex[:20]
            row = {**values, "project_id": key, "revision": (previous or {}).get("revision", 0) + 1, "updated_at": _now()}
            state["projects"][key] = row
            self._event(state, "项目更新" if previous else "项目建立", key, actor, row["status"])
            return copy.deepcopy(row)
        return self._mutate(action)

    def personal_action(self, knowledge_id: str, *, favorite: bool | None = None, visit: bool = False) -> dict[str, Any]:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            if knowledge_id not in state["knowledge"]:
                raise KeyError(knowledge_id)
            if favorite is not None:
                state["favorites"] = [key for key in state["favorites"] if key != knowledge_id]
                if favorite:
                    state["favorites"].append(knowledge_id)
            if visit:
                state["recent"] = [{"knowledge_id": knowledge_id, "at": _now()}, *[r for r in state["recent"] if r["knowledge_id"] != knowledge_id]][:20]
            return {"favorites": list(state["favorites"]), "recent": copy.deepcopy(state["recent"])}
        return self._mutate(action)

    def published_search(self, query: str, *, product_line: str = "", action_id: str = "", project_id: str = "", source_check=None) -> list[dict[str, Any]]:
        terms = query.casefold().split()
        if not terms:
            return []
        snapshot = self.snapshot()
        sources = {s["source_id"]: s for s in snapshot["sources"]}
        rows = []
        for knowledge in snapshot["knowledge"]:
            source = sources.get(knowledge["source_id"], {})
            if knowledge["status"] != "ACTIVE" or source.get("status") != "REGISTERED" or source.get("revision") != knowledge["source_revision"]:
                continue
            if source_check and source.get('external_bound') and not source_check(source):continue
            if product_line and knowledge.get("product_line", source.get("product_line")) != product_line:
                continue
            if action_id and knowledge.get("action_id") != action_id:
                continue
            if project_id and knowledge.get("project_id") != project_id:
                continue
            text = " ".join(str(knowledge.get(field, "")) for field in ("question", "answer", "excerpt", "applicability")).casefold()
            if all(term in text for term in terms):
                rows.append(knowledge)
        return rows

    def candidate_action(self, candidate_id: str, action_name: str, revision: int, actor: str,
                         note: str = "", confirmed: bool = False) -> dict[str, Any]:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            row = state["candidates"][candidate_id]
            self._expect(row, revision)
            allowed = {"submit": {"DRAFT", "REJECTED"}, "approve": {"IN_REVIEW"},
                       "reject": {"IN_REVIEW", "APPROVED"}, "publish": {"APPROVED"}}
            if row["status"] not in allowed.get(action_name, set()):
                raise PlatformConflict("当前状态不允许此操作。")
            checks = self._checks(row, state)
            if action_name in {"submit", "approve", "publish"} and not all(c["passed"] for c in checks):
                raise ValueError("结构检查未通过；请检查来源版本、摘录、定位和关键事实。")
            if action_name == "approve" and (not confirmed or not note.strip()):
                raise ValueError("需确认已核对原文、适用范围与答案，并填写审核意见。")
            if action_name == "reject" and not note.strip():
                raise ValueError("请填写退回原因。")
            if action_name == "publish":
                knowledge_id = "KN_" + candidate_id[2:]
                source = state["sources"][row["source_id"]]
                knowledge = {**copy.deepcopy(row), "knowledge_id": knowledge_id, "title": row["question"],
                             "content": row["answer"], "source_name": source["name"], "source_version_label": source["version_label"],
                             "product_line": state["projects"].get(row.get("project_id", ""), {}).get("product_line", source.get("product_line", "通用")),
                             "status": "ACTIVE", "version": 1, "revision": 1, "published_by": actor, "updated_at": _now()}
                knowledge["versions"] = [copy.deepcopy(knowledge)]
                state["knowledge"][knowledge_id] = knowledge
                row["knowledge_id"] = knowledge_id
                if row.get("feedback_id") in state["feedback"]:
                    state["feedback"][row["feedback_id"]].update(status="PUBLISHED", knowledge_id=knowledge_id)
            row.update(status={"submit": "IN_REVIEW", "approve": "APPROVED", "reject": "REJECTED", "publish": "PUBLISHED"}[action_name],
                       revision=row["revision"] + 1, checks=checks, updated_at=_now())
            if action_name in {"approve", "reject"}:
                row.update(reviewer=actor, review_note=note)
            self._event(state, {"submit": "候选提交审核", "approve": "人工审核通过", "reject": "候选退回", "publish": "知识发布至隔离管理库"}[action_name], candidate_id, actor, note)
            return copy.deepcopy(row)
        return self._mutate(action)

    def knowledge_action(self, knowledge_id: str, action_name: str, revision: int, actor: str,
                         note: str, target_version: int = 0) -> dict[str, Any]:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            row = state["knowledge"][knowledge_id]
            self._expect(row, revision)
            if not note.strip():
                raise ValueError("请填写操作原因。")
            if action_name == "withdraw":
                if row["status"] == "WITHDRAWN":
                    raise PlatformConflict("知识已撤回。")
                restored = {k: v for k, v in row.items() if k != "versions"}
                restored["status"] = "WITHDRAWN"
            elif action_name == "rollback":
                target = next((v for v in row["versions"] if v["version"] == target_version), None)
                if not target or target["status"] != "ACTIVE":
                    raise ValueError("只能恢复历史已发布版本。")
                source = state["sources"].get(target["source_id"], {})
                if source.get("status") != "REGISTERED" or source.get("revision") != target["source_revision"]:
                    raise PlatformConflict("历史版本来源已变更，需重新审核，不能直接恢复。")
                restored = copy.deepcopy(target)
            else:
                raise ValueError("未知操作。")
            restored.update(version=row["version"] + 1, revision=row["revision"] + 1, updated_at=_now())
            restored["versions"] = [*row["versions"], copy.deepcopy(restored)]
            state["knowledge"][knowledge_id] = restored
            if row.get("feedback_id") in state["feedback"]:
                state["feedback"][row["feedback_id"]].update(status=restored["status"])
            self._event(state, "知识撤回" if action_name == "withdraw" else "知识恢复历史版本", knowledge_id, actor, note)
            return copy.deepcopy(restored)
        return self._mutate(action)

    def begin_run(self, request_id: str, question: str, actor: str) -> tuple[dict[str, Any], bool]:
        key = "QR_" + request_id
        def action(state):
            previous = state["query_runs"].get(key)
            if previous:
                if previous["question"] != question:
                    raise PlatformConflict("请求编号已用于其他问题。")
                return copy.deepcopy(previous), False
            row = {"query_run_id": key, "question": question, "actor": actor, "status": "RUNNING", "recorded_at": _now()}
            state["query_runs"][key] = row
            return copy.deepcopy(row), True
        return self._mutate(action)

    def finish_run(self, key: str, result: dict[str, Any], *, error=False) -> dict[str, Any]:
        def action(state):
            row = state["query_runs"][key]
            row.update(status="ERROR" if error else "COMPLETED", result=result)
            return copy.deepcopy(row)
        return self._mutate(action)

    def existing_feedback(self, values: dict[str, Any], citation: dict | None, catalog_source: dict | None, actor: str) -> dict:
        def action(state):
            key = "FB_" + values["request_id"]
            if key in state["feedback"]:
                previous = state["feedback"][key]
                if previous["submitted_values"] != values:
                    raise PlatformConflict("反馈编号已使用，请刷新后重新提交。")
                return copy.deepcopy(previous)
            run = state["query_runs"][values["query_run_id"]]
            feedback = {"feedback_id": key, "submitted_values": values, "question": run["question"],
                        "query_run_id": run["query_run_id"], "kind": values["kind"], "comment": values["comment"],
                        "status": "RECORDED", "actor": actor, "created_at": _now()}
            if citation and catalog_source and values.get("expected_answer") and values["kind"] == "ANSWER_CORRECTION":
                sid = catalog_source["source_id"]
                source = state["sources"].get(sid)
                if source and source.get("status") != "REGISTERED":
                    raise PlatformConflict("此来源已经停用，请先核查后恢复。")
                if not source:
                    source = {"source_id": sid, "name": catalog_source["file_name"], "reference": catalog_source["source_path"],
                              "version_label": citation["source_version"][:12], "product_line": "通用", "revision": 1,
                              "status": "REGISTERED", "index_status": "EXISTING_READ_ONLY", "external_path": catalog_source["source_path"],
                              "external_hash": citation["source_version"], "external_bound": True, "updated_at": _now()}
                    state["sources"][sid] = source
                if source.get("external_hash") != citation["source_version"]:
                    raise PlatformConflict("已登记的来源版本与本次反馈不一致，需先核查。")
                cid = "C_" + values["request_id"]
                state["candidates"][cid] = {"candidate_id": cid, "question": run["question"], "answer": values["expected_answer"],
                    "source_id": sid, "source_revision": source["revision"], "location": citation["display_location"],
                    "excerpt": citation["excerpt"], "required_terms": values.get("required_terms", []), "applicability": values.get("applicability", "待审核确认"),
                    "status": "DRAFT", "revision": 1, "checks": [], "reviewer": "", "review_note": "", "action_id": "", "project_id": "",
                    "origin_citation": copy.deepcopy(citation), "origin_query_run_id": run["query_run_id"], "feedback_id": key, "updated_at": _now()}
                feedback.update(status="CANDIDATE_CREATED", candidate_id=cid)
            state["feedback"][key] = feedback
            self._event(state, "问答反馈已记录", key, actor, values["kind"])
            return copy.deepcopy(feedback)
        return self._mutate(action)

    def reviewed_answers(self, question: str, version_check) -> list[dict]:
        compact = lambda value: "".join(value.split()).rstrip("？?")
        def action(state):
            matches = []
            for row in state["knowledge"].values():
                if row["status"] != "ACTIVE" or not row.get("origin_citation") or compact(row["question"]) != compact(question):
                    continue
                source = state["sources"].get(row["source_id"], {})
                if source.get("status") != "REGISTERED" or source.get("revision") != row["source_revision"] or not version_check(source):
                    row.update(status="REVIEW_REQUIRED", revision=row["revision"] + 1)
                    self._event(state, "回答复用时发现来源失效，已暂停", row["knowledge_id"], "系统核对")
                    continue
                matches.append(copy.deepcopy(row))
            return matches
        return self._mutate(action)

    def source_withdraw(self, source_id: str, revision: int, actor: str, note: str) -> dict[str, Any]:
        def action(state: dict[str, Any]) -> dict[str, Any]:
            row = state["sources"][source_id]
            self._expect(row, revision)
            if row["status"] == "WITHDRAWN":
                raise PlatformConflict("来源已停用。")
            if not note.strip():
                raise ValueError("请填写停用原因。")
            row.update(status="WITHDRAWN", revision=row["revision"] + 1, updated_at=_now())
            for item in state["knowledge"].values():
                if item["source_id"] == source_id and item["status"] == "ACTIVE":
                    item.update(status="REVIEW_REQUIRED", revision=item["revision"] + 1)
            self._event(state, "来源停用并暂停关联知识", source_id, actor, note)
            return copy.deepcopy(row)
        return self._mutate(action)
