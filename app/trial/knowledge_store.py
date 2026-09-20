from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


STATE_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_source_path(value: str | Path) -> str:
    return str(value).strip().replace("/", "\\").rstrip("\\")


def source_id_for_path(path: str | Path) -> str:
    return "SRC_" + uuid.uuid5(uuid.NAMESPACE_URL, normalize_source_path(path).casefold()).hex[:20]


def source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _default_node_id(question: str) -> str:
    if any(marker in question for marker in ("组织", "中心", "岗位", "职责")):
        return "design-system-4"
    if "任务书" in question:
        return "design-planning-3"
    return ""


class TrialKnowledgeStore:
    """Small, versioned 8010-only registry for sources, reviewed knowledge and feedback."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "schema_version": STATE_VERSION,
            "sources": {},
            "knowledge": {},
            "question_variants": {},
            "change_candidates": {},
            "feedback": {},
            "query_runs": {},
            "events": [],
        }

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self._empty()
        if not isinstance(value, dict):
            return self._empty()
        result = self._empty()
        result.update(value)
        return result

    def _write(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def _mutate(self, action: Any) -> Any:
        with self._lock:
            state = self._read()
            result = action(state)
            self._write(state)
            return result

    def register_source(
        self,
        path: str | Path,
        *,
        approval_status: str = "USER_APPROVED_SHADOW_READ",
        source_root: str = "Root-002",
        configured: bool = False,
        version_note: str = "",
        registration_path: str = "",
        source_type: str = "",
        reactivate: bool = False,
    ) -> dict[str, Any]:
        source_path = normalize_source_path(path)
        local_path = Path(source_path)
        exists = local_path.is_file()
        digest = source_hash(local_path) if exists else ""
        source_id = source_id_for_path(source_path)

        def action(state: dict[str, Any]) -> dict[str, Any]:
            sources = state["sources"]
            current = dict(sources.get(source_id) or {})
            versions = list(current.get("versions") or [])
            previous_hash = str(current.get("current_hash") or "")
            changed = bool(current and exists and digest and previous_hash != digest)
            if not current:
                versions.append({"sha256": digest, "seen_at": _now(), "parse_status": "PENDING", "index_status": "PENDING", "active": True})
            elif changed:
                versions = [{**item, "active": False} for item in versions]
                versions.append({"sha256": digest, "seen_at": _now(), "parse_status": "PENDING", "index_status": "PENDING", "active": True})
                for knowledge in state["knowledge"].values():
                    if knowledge.get("source_id") == source_id and knowledge.get("status") == "ACTIVE":
                        candidate_id = "KC_" + uuid.uuid5(uuid.NAMESPACE_URL, f"{knowledge['knowledge_id']}|{digest}").hex[:20]
                        state["change_candidates"][candidate_id] = {
                            "candidate_id": candidate_id,
                            "knowledge_id": knowledge["knowledge_id"],
                            "status": "PROPOSED",
                            "reason": "SOURCE_VERSION_CHANGED",
                            "existing_content": knowledge.get("content", ""),
                            "previous_source_version": previous_hash,
                            "proposed_source_version": digest,
                            "edit_origin": "AUTO_SOURCE_REFRESH",
                            "created_at": _now(),
                        }
                        knowledge["status"] = "REVIEW_REQUIRED"
                        knowledge["updated_at"] = _now()
            row = {
                **current,
                "source_id": source_id,
                "source_path": source_path,
                "file_name": local_path.name,
                "file_type": local_path.suffix.lower(),
                "knowledge_root_id": source_root,
                "source_type": source_type or current.get("source_type", "待分类"),
                "version_note": version_note or current.get("version_note", "[待核实]"),
                "registration_path": normalize_source_path(registration_path) if registration_path else current.get("registration_path", ""),
                "approval_status": approval_status,
                "configured": bool(current.get("configured")) or configured,
                "exists": exists,
                "current_hash": digest,
                "versions": versions,
                "body_status": "PENDING" if exists and (not current or changed) else current.get("body_status", "MISSING" if not exists else "PENDING"),
                "index_status": "PENDING" if exists and (not current or changed) else current.get("index_status", "MISSING" if not exists else "PENDING"),
                "index_generation": current.get("index_generation", ""),
                "created_at": current.get("created_at", _now()),
                "updated_at": _now(),
                "withdrawn": False if reactivate or not current else bool(current.get("withdrawn")),
                "error": None if exists else "SOURCE_FILE_NOT_FOUND",
            }
            sources[source_id] = row
            if not current or changed:
                state["events"].append({"event_id": "EV_" + uuid.uuid4().hex, "type": "SOURCE_REGISTERED" if not current else "SOURCE_VERSION_CHANGED", "source_id": source_id, "at": _now()})
            return dict(row)

        return self._mutate(action)

    def sync_configured_sources(self, sources: Iterable[dict[str, str]]) -> list[dict[str, Any]]:
        return [
            self.register_source(
                str(source["path"]),
                approval_status=str(source.get("approval_status") or "USER_APPROVED_SHADOW_READ"),
                configured=True,
                version_note=str(source.get("version_note") or ""),
                registration_path=str(source.get("registration_path") or ""),
                source_type=str(source.get("source_type") or ""),
            )
            for source in sources
            if source.get("path")
        ]

    def mark_indexed(
        self,
        source_id: str,
        *,
        source_hash_value: str,
        parse_status: str,
        chunk_count: int,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        def action(state: dict[str, Any]) -> dict[str, Any] | None:
            row = state["sources"].get(source_id)
            if not row or row.get("current_hash") != source_hash_value:
                return None
            status = "INDEXED" if parse_status == "parsed" and chunk_count else "FAILED"
            row.update({"body_status": "PARSED" if parse_status == "parsed" else parse_status.upper(), "index_status": status, "index_generation": source_hash_value[:12] if status == "INDEXED" else "", "chunk_count": chunk_count, "error": error, "updated_at": _now()})
            for version in row.get("versions", []):
                if version.get("active"):
                    version.update({"parse_status": parse_status, "index_status": status, "chunk_count": chunk_count, "error": error})
            return dict(row)

        return self._mutate(action)

    def active_sources(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._read()["sources"].values()
        return [dict(row) for row in rows if row.get("approval_status") == "USER_APPROVED_SHADOW_READ" and not row.get("withdrawn")]

    def list_sources(self, query: str = "", *, include_withdrawn: bool = False) -> list[dict[str, Any]]:
        query = query.casefold().strip()
        with self._lock:
            rows = [dict(row) for row in self._read()["sources"].values()]
        if not include_withdrawn:
            rows = [row for row in rows if not row.get("withdrawn")]
        if query:
            rows = [row for row in rows if query in " ".join(str(row.get(field) or "") for field in ("file_name", "source_path", "source_id")).casefold()]
        return sorted(rows, key=lambda row: (str(row.get("updated_at") or ""), str(row.get("source_id") or "")), reverse=True)

    def source(self, source_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._read()["sources"].get(source_id)
        return dict(row) if row else None

    def withdraw_source(self, source_id: str, *, reviewer: str) -> dict[str, Any] | None:
        def action(state: dict[str, Any]) -> dict[str, Any] | None:
            row = state["sources"].get(source_id)
            if row is None:
                return None
            row.update({"withdrawn": True, "index_status": "WITHDRAWN", "withdrawn_by": reviewer, "updated_at": _now()})
            for knowledge in state["knowledge"].values():
                if knowledge.get("source_id") == source_id and knowledge.get("status") == "ACTIVE":
                    knowledge["status"] = "REVIEW_REQUIRED"
                    knowledge["updated_at"] = _now()
            state["events"].append({"event_id": "EV_" + uuid.uuid4().hex, "type": "SOURCE_WITHDRAWN", "source_id": source_id, "at": _now()})
            return dict(row)

        return self._mutate(action)

    def record_query(self, query_run_id: str, value: dict[str, Any]) -> None:
        def action(state: dict[str, Any]) -> None:
            state["query_runs"][query_run_id] = {**value, "query_run_id": query_run_id, "recorded_at": _now()}

        self._mutate(action)

    def query_run(self, query_run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._read()["query_runs"].get(query_run_id)
        return dict(row) if row else None

    def last_query_for_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        if not conversation_id:
            return None
        with self._lock:
            rows = [dict(row) for row in self._read()["query_runs"].values() if row.get("conversation_id") == conversation_id]
        return max(rows, key=lambda row: str(row.get("recorded_at") or ""), default=None)

    def record_feedback(self, event: dict[str, Any], idempotency_key: str) -> tuple[dict[str, Any], bool]:
        def action(state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
            for row in state["feedback"].values():
                if row.get("idempotency_key") == idempotency_key:
                    return dict(row), False
            feedback_id = "FB_" + uuid.uuid4().hex
            value = {**event, "feedback_id": feedback_id, "idempotency_key": idempotency_key, "status": "RECORDED", "created_at": _now(), "updated_at": _now()}
            state["feedback"][feedback_id] = value
            state["events"].append({"event_id": "EV_" + uuid.uuid4().hex, "type": "FEEDBACK_RECORDED", "feedback_id": feedback_id, "at": _now()})
            return dict(value), True

        return self._mutate(action)

    def feedback(self, feedback_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._read()["feedback"].get(feedback_id)
        return dict(row) if row else None

    def list_feedback(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(row) for row in self._read()["feedback"].values()]
        return sorted(rows, key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)

    def record_regression(self, feedback_id: str, regression: dict[str, Any]) -> dict[str, Any] | None:
        def action(state: dict[str, Any]) -> dict[str, Any] | None:
            feedback = state["feedback"].get(feedback_id)
            if feedback is None:
                return None
            feedback["latest_regression"] = regression
            feedback["updated_at"] = _now()
            return dict(feedback)

        return self._mutate(action)

    def review_feedback(
        self,
        feedback_id: str,
        *,
        decision: str,
        source_id: str,
        location: str,
        required_terms: list[str],
        reviewer: str,
        standard_question: str = "",
        similar_questions: list[str] | None = None,
        negative_questions: list[str] | None = None,
        applicability: str = "",
        node_id: str = "",
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        def action(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
            feedback = state["feedback"].get(feedback_id)
            if feedback is None:
                raise KeyError(feedback_id)
            if decision == "APPROVE" and feedback.get("system_fix_required"):
                raise ValueError("SYSTEM_DEFECT_CANNOT_PUBLISH_AS_STANDARD_ANSWER")
            feedback.update({"status": {"APPROVE": "APPROVED", "REJECT": "REJECTED", "DEFER": "DEFERRED"}.get(decision, "RECORDED"), "reviewer": reviewer, "reviewed_at": _now(), "source_id": source_id or feedback.get("source_id", ""), "source_location": location or feedback.get("source_location", ""), "required_terms": required_terms or feedback.get("required_terms", []), "updated_at": _now()})
            knowledge = None
            if decision == "APPROVE" and feedback.get("expected_answer") and feedback.get("source_id"):
                knowledge_id = "KN_" + uuid.uuid5(uuid.NAMESPACE_URL, feedback_id).hex[:20]
                source = state["sources"].get(feedback["source_id"], {})
                content = str(feedback["expected_answer"]).strip()
                facts = required_terms or [sentence.strip() for sentence in content.split("。") if sentence.strip()]
                standard = standard_question.strip() or str(feedback.get("standard_question") or feedback.get("question") or "").strip()
                similar = list(dict.fromkeys(similar_questions or feedback.get("similar_questions") or []))
                negative = list(dict.fromkeys(negative_questions or feedback.get("negative_questions") or []))
                knowledge = {
                    "knowledge_id": knowledge_id,
                    "node_id": node_id or str(feedback.get("node_id") or "") or _default_node_id(standard),
                    "title": standard or "已审核更正",
                    "content": content,
                    "approved_answer": content,
                    "fact_items": facts,
                    "standard_question": standard,
                    "similar_questions": similar,
                    "negative_questions": negative,
                    "applicability": applicability.strip() or str(feedback.get("applicability") or ""),
                    "source_id": feedback["source_id"],
                    "source_version": source.get("current_hash", ""),
                    "source_location": feedback.get("source_location", ""),
                    "evidence_refs": [{"source_id": feedback["source_id"], "location": feedback.get("source_location", ""), "source_version": source.get("current_hash", "")}],
                    "required_terms": feedback.get("required_terms", []),
                    "status": "ACTIVE",
                    "review_status": "APPROVED",
                    "edit_origin": "HUMAN_REVIEWED",
                    "version": 1,
                    "versions": [],
                    "feedback_id": feedback_id,
                    "created_at": _now(),
                    "updated_at": _now(),
                }
                knowledge["versions"] = [{key: value for key, value in knowledge.items() if key != "versions"}]
                state["knowledge"][knowledge_id] = knowledge
                for usage, questions in (("STANDARD_ANSWER", [standard]), ("RETRIEVAL", knowledge["similar_questions"]), ("NEGATIVE", knowledge["negative_questions"])):
                    for question in questions:
                        if not question:
                            continue
                        variant_id = "QV_" + uuid.uuid5(uuid.NAMESPACE_URL, f"{knowledge_id}|{usage}|{question}").hex[:20]
                        state["question_variants"][variant_id] = {"question_variant_id": variant_id, "knowledge_id": knowledge_id, "text": question, "usage": usage, "review_status": "APPROVED", "source_version": source.get("current_hash", ""), "status": "ACTIVE"}
                feedback.update({"status": "ACTIVE", "knowledge_id": knowledge_id})
                state["events"].append({"event_id": "EV_" + uuid.uuid4().hex, "type": "KNOWLEDGE_ACTIVATED", "knowledge_id": knowledge_id, "source_id": feedback["source_id"], "at": _now()})
            return dict(feedback), dict(knowledge) if knowledge else None

        return self._mutate(action)

    def active_knowledge(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._read()["knowledge"].values()
        return [dict(row) for row in rows if row.get("status") == "ACTIVE"]

    def active_variants(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._read()["question_variants"].values()
        return [dict(row) for row in rows if row.get("status") == "ACTIVE"]

    def list_change_candidates(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = [dict(row) for row in self._read()["change_candidates"].values()]
        return sorted(rows, key=lambda row: str(row.get("created_at") or ""), reverse=True)

    def withdraw_knowledge(self, knowledge_id: str, *, reviewer: str) -> dict[str, Any] | None:
        def action(state: dict[str, Any]) -> dict[str, Any] | None:
            row = state["knowledge"].get(knowledge_id)
            if row is None:
                return None
            row["versions"] = [*row.get("versions", []), {**{key: value for key, value in row.items() if key != "versions"}, "version": int(row.get("version", 1)) + 1, "status": "WITHDRAWN", "updated_at": _now()}]
            row["version"] = int(row.get("version", 1)) + 1
            row.update({"status": "WITHDRAWN", "withdrawn_by": reviewer, "updated_at": _now()})
            feedback = state["feedback"].get(str(row.get("feedback_id") or ""))
            if feedback:
                feedback.update({"status": "WITHDRAWN", "updated_at": _now()})
            for variant in state["question_variants"].values():
                if variant.get("knowledge_id") == knowledge_id:
                    variant["status"] = "INACTIVE"
            state["events"].append({"event_id": "EV_" + uuid.uuid4().hex, "type": "KNOWLEDGE_WITHDRAWN", "knowledge_id": knowledge_id, "at": _now()})
            return dict(row)

        return self._mutate(action)

    def rollback_knowledge(self, knowledge_id: str, *, target_version: int, reviewer: str, reason: str) -> dict[str, Any] | None:
        def action(state: dict[str, Any]) -> dict[str, Any] | None:
            row = state["knowledge"].get(knowledge_id)
            if row is None:
                return None
            target = next((item for item in row.get("versions", []) if int(item.get("version", 0)) == target_version), None)
            if target is None:
                raise ValueError("KNOWLEDGE_VERSION_NOT_FOUND")
            source = state["sources"].get(str(target.get("source_id") or ""), {})
            source_valid = bool(source and not source.get("withdrawn") and source.get("current_hash") == target.get("source_version"))
            versions = list(row.get("versions", []))
            restored = {**target, "version": int(row.get("version", 1)) + 1, "status": "ACTIVE" if source_valid else "REVIEW_REQUIRED", "updated_at": _now(), "rollback_from_version": target_version, "rollback_reason": reason, "rollback_by": reviewer, "versions": versions}
            restored["versions"] = [*versions, {key: value for key, value in restored.items() if key != "versions"}]
            state["knowledge"][knowledge_id] = restored
            feedback = state["feedback"].get(str(restored.get("feedback_id") or ""))
            if feedback:
                feedback.update({"status": "ACTIVE" if source_valid else "REVIEW_REQUIRED", "updated_at": _now()})
            for variant in state["question_variants"].values():
                if variant.get("knowledge_id") == knowledge_id:
                    variant["status"] = "ACTIVE" if source_valid else "INACTIVE"
            state["events"].append({"event_id": "EV_" + uuid.uuid4().hex, "type": "KNOWLEDGE_ROLLED_BACK", "knowledge_id": knowledge_id, "target_version": target_version, "source_valid": source_valid, "at": _now()})
            return dict(restored)

        return self._mutate(action)

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        tokens = [term for term in query.casefold().split() if term]
        compact = "".join(query.casefold().split())
        rows: list[dict[str, Any]] = []
        for source in self.list_sources(query):
            rows.append({"type": "SOURCE", "score": 2.0 if compact and compact in str(source.get("file_name") or "").casefold() else 1.0, "source": source})
        variants_by_knowledge: dict[str, list[dict[str, Any]]] = {}
        for variant in self.active_variants():
            variants_by_knowledge.setdefault(str(variant["knowledge_id"]), []).append(variant)
        for knowledge in self.active_knowledge():
            haystack = " ".join(str(knowledge.get(field) or "") for field in ("title", "content")).casefold()
            variant_score = max((3 if compact and compact == "".join(str(item.get("text") or "").casefold().split()) else sum(term in str(item.get("text") or "").casefold() for term in tokens) for item in variants_by_knowledge.get(str(knowledge["knowledge_id"]), []) if item.get("usage") != "NEGATIVE"), default=0)
            score = max(sum(term in haystack for term in tokens) + (3 if compact and compact in haystack else 0), variant_score)
            if score:
                rows.append({"type": "KNOWLEDGE", "score": float(score), "knowledge": knowledge})
        return sorted(rows, key=lambda row: (-float(row["score"]), row["type"]))[:limit]

    def overview(self) -> dict[str, Any]:
        with self._lock:
            state = self._read()
        sources = list(state["sources"].values())
        knowledge = list(state["knowledge"].values())
        feedback = list(state["feedback"].values())
        return {
            "sources": len([row for row in sources if not row.get("withdrawn")]),
            "indexed_sources": len([row for row in sources if row.get("index_status") == "INDEXED" and not row.get("withdrawn")]),
            "active_knowledge": len([row for row in knowledge if row.get("status") == "ACTIVE"]),
            "pending_feedback": len([row for row in feedback if row.get("status") in {"RECORDED", "APPROVED"}]),
            "recent_events": list(reversed(state["events"][-10:])),
            "state_version": hashlib.sha256(json.dumps({key: state[key] for key in ("sources", "knowledge", "question_variants")}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12],
        }
