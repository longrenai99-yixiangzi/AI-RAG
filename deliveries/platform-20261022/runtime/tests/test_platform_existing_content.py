import hashlib
import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.trial.platform_app import create_app
from app.trial.platform_existing import ExistingKnowledge, source_extract

HEADERS = {"X-Platform-Request": "1"}


class ExistingFixture:
    def __init__(self, path):
        self.path = path
        path.write_text("协调会应记录责任人和期限。", encoding="utf-8")
        self.hash = hashlib.sha256(path.read_bytes()).hexdigest()
        self.source = {"source_id": "SRC_fixture", "file_name": path.name, "source_path": str(path), "current_hash": self.hash}
        self.calls = 0
        self.failed = False

    def status(self):
        return {"sources": 1, "records": 1, "candidate_hash": "fixture", "model_http_enabled": False}

    def sources(self, **kwargs):
        return {"items": [self.source], "total": 1}

    def catalog_source(self, source_id):
        if source_id != self.source["source_id"]:
            raise KeyError(source_id)
        return self.source

    def evidence(self, source_id):
        self.catalog_source(source_id)
        return {"items": [{"evidence_id": "E1", "excerpt": self.path.read_text(encoding="utf-8")}]}

    version_current = staticmethod(ExistingKnowledge.version_current)

    def retrieve(self, question, request_id):
        self.calls += 1
        if self.failed:
            raise RuntimeError("fixture failure")
        return {"answer_status": "SOURCES_ONLY", "citations": [{"citation_id": "S1", "source_id": self.source["source_id"], "source_version": self.hash,
                "source_path": str(self.path), "file_name": self.path.name, "display_location": "第1条", "excerpt": "协调会应记录责任人和期限。", "answer_usage": "PRIMARY"}]}


@pytest.fixture
def runtime(tmp_path):
    existing = ExistingFixture(tmp_path / "source.md")
    app = create_app(tmp_path / "state.json", existing=existing)
    with TestClient(app) as client:
        yield client, existing


def ask(client, question="协调会如何记录？", request_id=None):
    response = client.post("/api/platform/query", headers=HEADERS, json={"question": question, "request_id": request_id or uuid.uuid4().hex})
    assert response.status_code == 200, response.text
    return response.json()


def feedback(client, run, **changes):
    values = {"request_id": uuid.uuid4().hex, "query_run_id": run["query_run_id"], "kind": "ANSWER_CORRECTION", "comment": "合成验收", "citation_id": "S1",
              "expected_answer": "协调会应记录责任人和期限。", "required_terms": ["责任人", "期限"], "applicability": "仅本演示规定"}
    values.update(changes)
    response = client.post("/api/platform/query-feedback", headers=HEADERS, json=values)
    return response, values


def publish(client, candidate_id):
    row = next(c for c in client.get("/api/platform/state").json()["candidates"] if c["candidate_id"] == candidate_id)
    for action, extras in [("submit", {}), ("approve", {"note": "合成材料验收，不是业务审批", "confirmed": True}), ("publish", {})]:
        response = client.post(f'/api/platform/candidates/{candidate_id}/actions', headers=HEADERS,
                               json={"revision": row["revision"], "action": action, **extras})
        assert response.status_code == 200, response.text
        row = response.json()
    return row


def test_browse_query_feedback_review_publish_reuse_withdraw_restore(runtime):
    client, existing = runtime
    state = client.get("/api/platform/state").json()
    assert state["mode"] == "EXISTING_CONTENT_TRIAL" and state["runtime"]["sources"] == 1
    assert client.get("/api/platform/library").json()["total"] == 1
    assert client.get("/api/platform/library/SRC_fixture/evidence").json()["items"]
    assert client.get("/api/platform/library/SRC_fixture/original").text == "协调会应记录责任人和期限。"
    run = ask(client)
    assert run["result"]["answer_status"] == "SOURCE_EXTRACT"
    fb, values = feedback(client, run)
    assert fb.status_code == 200
    assert client.get("/api/platform/state").json()["knowledge"] == []
    row = publish(client, fb.json()["candidate_id"])
    result = ask(client)["result"]
    assert result["answer_status"] == "REVIEWED_ANSWER" and existing.calls == 1
    assert client.get("/api/platform/state").json()["feedback"][0]["status"] == "PUBLISHED"
    assert ask(client, "其他项目协调会如何记录？")["result"]["answer_status"] == "SOURCE_EXTRACT"
    assert existing.calls == 2
    knowledge = client.get("/api/platform/state").json()["knowledge"][0]
    path = f'/api/platform/knowledge/{row["knowledge_id"]}/actions'
    withdrawn = client.post(path, headers=HEADERS, json={"action": "withdraw", "revision": knowledge["revision"], "note": "合成验收撤回"}).json()
    assert ask(client)["result"]["answer_status"] == "SOURCE_EXTRACT" and existing.calls == 3
    restored = client.post(path, headers=HEADERS, json={"action": "rollback", "target_version": 1, "revision": withdrawn["revision"], "note": "合成恢复"})
    assert restored.status_code == 200
    assert ask(client)["result"]["answer_status"] == "REVIEWED_ANSWER" and existing.calls == 3


def test_query_and_feedback_retries_are_idempotent(runtime):
    client, existing = runtime
    key = uuid.uuid4().hex
    one, two = ask(client, request_id=key), ask(client, request_id=key)
    assert one == two and existing.calls == 1
    assert client.post("/api/platform/query", headers=HEADERS, json={"question": "不同问题", "request_id": key}).status_code == 409
    response, values = feedback(client, one)
    assert response.status_code == 200
    assert client.post("/api/platform/query-feedback", headers=HEADERS, json=values).json() == response.json()
    assert len(client.get("/api/platform/state").json()["candidates"]) == 1
    values["comment"] = "改动"
    assert client.post("/api/platform/query-feedback", headers=HEADERS, json=values).status_code == 409


def test_source_change_blocks_publish_reuse_restore_and_original(runtime):
    client, existing = runtime
    run = ask(client)
    fb, _ = feedback(client, run)
    publish(client, fb.json()["candidate_id"])
    existing.path.write_text("第二版已更改。", encoding="utf-8")
    assert client.get('/api/platform/search',params={'q':'责任人'}).json()['items']==[]
    assert ask(client)["result"]["answer_status"] != "REVIEWED_ANSWER"
    knowledge = client.get("/api/platform/state").json()["knowledge"][0]
    assert knowledge["status"] == "REVIEW_REQUIRED"
    assert client.get("/api/platform/library/SRC_fixture/original").status_code == 409
    assert client.post(f'/api/platform/knowledge/{knowledge["knowledge_id"]}/actions', headers=HEADERS,
                       json={"action": "rollback", "target_version": 1, "revision": knowledge["revision"], "note": "尝试恢复"}).status_code == 409
    assert feedback(client, run)[0].status_code == 409


def test_feedback_proof_cannot_be_forged_or_edited_into_unrelated_text(runtime):
    client, existing = runtime
    run = ask(client)
    assert feedback(client, run, citation_id="forged")[0].status_code == 422
    fb, _ = feedback(client, run)
    candidate = client.get("/api/platform/state").json()["candidates"][0]
    body = {k: candidate[k] for k in ("question", "answer", "source_id", "location", "excerpt", "required_terms", "applicability")}
    body.update(excerpt="另一份文件的责任人和期限。", revision=candidate["revision"])
    edited = client.put(f'/api/platform/candidates/{candidate["candidate_id"]}', headers=HEADERS, json=body).json()
    assert client.post(f'/api/platform/candidates/{candidate["candidate_id"]}/actions', headers=HEADERS,
                       json={"action": "submit", "revision": edited["revision"]}).status_code == 422
    source = client.get("/api/platform/state").json()["sources"][0]
    assert client.put(f'/api/platform/sources/{source["source_id"]}', headers=HEADERS,
                      json={"name": "伪造引用", "reference": "D:/other.pdf", "version_label": "x", "revision": source["revision"]}).status_code == 409


def test_system_feedback_never_creates_standard_answer_and_errors_persist(runtime):
    client, existing = runtime
    run = ask(client)
    response, _ = feedback(client, run, kind="RETRIEVAL_ERROR")
    assert response.status_code == 200 and "candidate_id" not in response.json()
    assert client.get("/api/platform/state").json()["candidates"] == []
    existing.failed = True
    result = ask(client, "新的失败问题")
    assert result["status"] == "ERROR" and result["result"]["answer_status"] == "PIPELINE_ERROR"
    assert client.get(f'/api/platform/runs/{result["query_run_id"]}').json() == result


def test_conflicting_reviewed_answers_do_not_choose_first(runtime):
    client, existing = runtime
    run = ask(client)
    for _ in range(2):
        response, _ = feedback(client, run)
        publish(client, response.json()["candidate_id"])
    assert ask(client)["result"]["answer_status"] == "REVIEW_CONFLICT"
    assert existing.calls == 1


def test_upstream_is_always_sources_only_and_incomplete_sse_fails_closed():
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, text='data: ' + json.dumps({"type": "result", "result": {"answer_status": "SOURCES_ONLY", "citations": []}}) + '\n\n')
    existing = ExistingKnowledge(httpx.Client(base_url="http://127.0.0.1:8894", transport=httpx.MockTransport(handler)))
    existing.retrieve("问题", "a" * 32)
    assert calls[0]["mode"] == "sources" and calls[0]["conversation_id"] == "platform-" + "a" * 32
    broken = ExistingKnowledge(httpx.Client(base_url="http://127.0.0.1:8894", transport=httpx.MockTransport(lambda _: httpx.Response(200, text='data: {"type":"status"}\n\n'))))
    with pytest.raises(ValueError, match="完整结果"):
        broken.retrieve("问题", "b" * 32)
    assert source_extract({"answer_status": "EVIDENCE_INSUFFICIENT", "citations": []})["generation_mode"] == "NO_GENERATION"
    assert source_extract({"answer_status": "SOURCES_ONLY", "citations": [{"excerpt": "背景", "answer_usage": "BACKGROUND"}]})["generation_mode"] == "NO_GENERATION"
