import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.trial.platform_app import create_app, seed_demo
from app.trial.platform_store import PlatformStore


HEADERS = {"X-Platform-Request": "1"}


def test_frontend_entry_is_not_cached_after_a_new_build(tmp_path):
    ui=tmp_path/'ui';ui.mkdir();(ui/'assets').mkdir()
    (ui/'platform.html').write_text('<html>current build</html>')
    with TestClient(create_app(tmp_path/'state.json',ui_dist=ui)) as result:
        response=result.get('/manage')
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert 'current build' in response.text


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "state.json")) as result:
        yield result


def source(client):
    response = client.post("/api/platform/sources", headers=HEADERS, json={
        "name": "演示制度", "version_label": "演示V1", "reference": "D:/DO_NOT_READ/original.pdf"})
    assert response.status_code == 200, response.text
    return response.json()


def candidate(client, source_id):
    response = client.post("/api/platform/candidates", headers=HEADERS, json={
        "question": "演示问题？", "answer": "记录责任人与期限。", "source_id": source_id,
        "location": "第1条", "excerpt": "记录责任人与期限。", "required_terms": ["责任人", "期限"],
        "applicability": "仅演示"})
    assert response.status_code == 200, response.text
    return response.json()


def act(client, row, action, **kwargs):
    return client.post(f'/api/platform/candidates/{row["candidate_id"]}/actions', headers=HEADERS,
                       json={"revision": row["revision"], "action": action, **kwargs})


def publish(client, row):
    row = act(client, row, "submit").json()
    row = act(client, row, "approve", note="已核对演示原文及范围", confirmed=True).json()
    response = act(client, row, "publish")
    assert response.status_code == 200, response.text
    return response.json()


def test_lifecycle_persists_and_audits_without_index_or_model(client):
    s = source(client)
    c = candidate(client, s["source_id"])
    assert act(client, c, "publish").status_code == 409
    c = act(client, c, "submit").json()
    assert act(client, c, "approve", note="缺少确认").status_code == 422
    c = act(client, c, "approve", note="已核对原文与范围", confirmed=True).json()
    assert client.get("/api/platform/state").json()["knowledge"] == []
    p = act(client, c, "publish").json()
    assert act(client, p, "publish").status_code == 409
    state = client.get("/api/platform/state").json()
    k = state["knowledge"][0]
    assert k["status"] == "ACTIVE" and k["content"] == c["answer"]
    assert state["sources"][0]["index_status"] == "NOT_CONNECTED"
    assert not any(state["capabilities"].values())
    persisted = PlatformStore(client.app.state.platform_store.path).snapshot()
    assert persisted["knowledge"] == state["knowledge"]
    assert [e["type"] for e in persisted["events"]][:3] == ["知识发布至隔离管理库", "人工审核通过", "候选提交审核"]
    assert client.get("/api/platform/export").json()["knowledge"] == state["knowledge"]


def test_stale_edit_does_not_overwrite_and_edit_resets_approval(client):
    s = source(client)
    c = candidate(client, s["source_id"])
    submitted = act(client, c, "submit").json()
    approved = act(client, submitted, "approve", note="已核对", confirmed=True).json()
    body = {key: c[key] for key in ("question", "answer", "source_id", "location", "excerpt", "required_terms", "applicability")}
    body["revision"] = c["revision"]
    url = f'/api/platform/candidates/{c["candidate_id"]}'
    assert client.put(url, headers=HEADERS, json=body).status_code == 409
    body["revision"] = approved["revision"]
    edited = client.put(url, headers=HEADERS, json=body).json()
    assert edited["status"] == "DRAFT" and edited["reviewer"] == ""
    assert act(client, edited, "publish").status_code == 409


@pytest.mark.parametrize("change", ["version", "withdraw"])
def test_source_change_blocks_approved_publish(client, change):
    s = source(client)
    c = candidate(client, s["source_id"])
    c = act(client, c, "submit").json()
    c = act(client, c, "approve", note="已核对", confirmed=True).json()
    if change == "version":
        response = client.put(f'/api/platform/sources/{s["source_id"]}', headers=HEADERS, json={
            "name": s["name"], "version_label": "V2", "revision": s["revision"]})
    else:
        response = client.post(f'/api/platform/sources/{s["source_id"]}/withdraw', headers=HEADERS,
                               json={"action": "withdraw", "revision": s["revision"], "note": "演示停用"})
    assert response.status_code == 200
    assert act(client, c, "publish").status_code == 422
    assert client.get("/api/platform/state").json()["knowledge"] == []


def test_withdraw_restore_and_changed_source_cannot_restore(client):
    s = source(client)
    publish(client, candidate(client, s["source_id"]))
    k = client.get("/api/platform/state").json()["knowledge"][0]
    url = f'/api/platform/knowledge/{k["knowledge_id"]}/actions'
    assert client.post(url, headers=HEADERS, json={"action": "withdraw", "revision": k["revision"]}).status_code == 422
    k = client.post(url, headers=HEADERS, json={"action": "withdraw", "revision": k["revision"], "note": "演示撤回"}).json()
    assert k["status"] == "WITHDRAWN" and k["version"] == 2
    assert client.post(url, headers=HEADERS, json={"action": "rollback", "revision": k["revision"], "target_version": 2, "note": "不可恢复撤回快照"}).status_code == 422
    k = client.post(url, headers=HEADERS, json={"action": "rollback", "revision": k["revision"], "target_version": 1, "note": "恢复演示V1"}).json()
    assert k["status"] == "ACTIVE" and k["version"] == 3
    response = client.put(f'/api/platform/sources/{s["source_id"]}', headers=HEADERS, json={
        "name": s["name"], "version_label": "V2", "revision": s["revision"]})
    assert response.status_code == 200
    k = client.get("/api/platform/state").json()["knowledge"][0]
    assert k["status"] == "REVIEW_REQUIRED"
    assert client.post(url, headers=HEADERS, json={"action": "rollback", "revision": k["revision"], "target_version": 1, "note": "来源过期"}).status_code == 409


def test_failed_structural_check_does_not_advance_state(client):
    s = source(client)
    c = candidate(client, s["source_id"])
    body = {key: c[key] for key in ("question", "answer", "source_id", "location", "excerpt", "required_terms", "applicability")}
    body.update(required_terms=["摘录不支持的数字"], revision=c["revision"])
    c = client.put(f'/api/platform/candidates/{c["candidate_id"]}', headers=HEADERS, json=body).json()
    assert act(client, c, "submit").status_code == 422
    assert client.get("/api/platform/state").json()["candidates"][0]["status"] == "DRAFT"


def test_rejection_and_published_edit_guards(client):
    s = source(client)
    c = candidate(client, s["source_id"])
    c = act(client, c, "submit").json()
    assert act(client, c, "reject").status_code == 422
    c = act(client, c, "reject", note="需补原文").json()
    assert c["status"] == "REJECTED"
    p = publish(client, c)
    body = {key: p[key] for key in ("question", "answer", "source_id", "location", "excerpt", "required_terms", "applicability")}
    body["revision"] = p["revision"]
    assert client.put(f'/api/platform/candidates/{p["candidate_id"]}', headers=HEADERS, json=body).status_code == 409


def test_local_origin_header_host_and_validation_boundaries(client):
    body = {"name": "演示", "version_label": "v1"}
    assert client.post("/api/platform/sources", json=body).status_code == 403
    assert client.post("/api/platform/sources", json=body, headers={**HEADERS, "Origin": "https://external.test"}).status_code == 403
    assert client.get("/api/platform/state", headers={"Host": "external.test"}).status_code == 403
    assert client.post("/api/platform/sources", json={**body, "arbitrary_path": "no"}, headers=HEADERS).status_code == 422
    assert client.post("/api/platform/sources", json={"name": " ", "version_label": "v1"}, headers=HEADERS).status_code == 422
    assert client.get("/api/real-index").status_code == 404


def test_corrupt_registry_is_not_silently_overwritten(tmp_path):
    path = tmp_path / "state.json"
    original = '{"broken":'
    path.write_text(original, encoding="utf-8")
    store = PlatformStore(path)
    with pytest.raises(ValueError):
        store.save_source({"name": "no"}, "actor")
    assert path.read_text(encoding="utf-8") == original
    path.write_text(json.dumps({"platform_schema": 1, "sources": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="不完整"):
        store.snapshot()


def test_seed_is_idempotent_and_does_not_publish(tmp_path):
    store = PlatformStore(tmp_path / "state.json")
    seed_demo(store)
    before = store.path.read_bytes()
    seed_demo(store)
    assert store.path.read_bytes() == before
    assert len(store.snapshot()["candidates"]) == 1
    assert store.snapshot()["knowledge"] == []


def test_separate_store_instances_do_not_overwrite_events(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    def create(index):
        store = PlatformStore(tmp_path / "state.json")
        return store.save_project({"name": str(index), "status": "ACTIVE"}, "fixture")
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(create, range(8)))
    snapshot = PlatformStore(tmp_path / "state.json").snapshot()
    assert len(rows) == len(snapshot["projects"]) == len(snapshot["events"]) == 8


def test_project_assignment_archive_and_stale_edit(client):
    p = client.post("/api/platform/projects", headers=HEADERS, json={"name": "演示项目", "product_line": "学校", "stage": "策划"}).json()
    s = source(client)
    c = candidate(client, s["source_id"])
    body = {key: c[key] for key in ("question", "answer", "source_id", "location", "excerpt", "required_terms", "applicability")}
    body.update(project_id=p["project_id"], revision=c["revision"])
    c = client.put(f'/api/platform/candidates/{c["candidate_id"]}', headers=HEADERS, json=body).json()
    assert c["project_id"] == p["project_id"]
    updated = client.put(f'/api/platform/projects/{p["project_id"]}', headers=HEADERS,
                         json={"name": p["name"], "product_line": p["product_line"], "status": "ARCHIVED", "revision": p["revision"]})
    assert updated.status_code == 200
    assert act(client, c, "submit").status_code == 422
    body["revision"] = c["revision"]
    assert client.put(f'/api/platform/candidates/{c["candidate_id"]}', headers=HEADERS, json=body).status_code == 422
    assert client.put(f'/api/platform/projects/{p["project_id"]}', headers=HEADERS,
                      json={"name": "旧页面", "product_line": "学校", "revision": p["revision"]}).status_code == 409


def test_keyword_search_excludes_withdrawn_stale_and_unapproved(client):
    s = source(client)
    c = candidate(client, s["source_id"])
    assert client.get("/api/platform/search", params={"q": "责任人"}).json()["items"] == []


    published = publish(client, c)
    result = client.get("/api/platform/search", params={"q": "责任人 期限", "product_line": "通用"}).json()
    assert result["mode"] == "PUBLISHED_KEYWORD_SEARCH" and len(result["items"]) == 1
    assert client.get("/api/platform/search", params={"q": "责任人 缺失词"}).json()["items"] == []
    assert client.get("/api/platform/search", params={"q": "责任人", "action_id": "unknown"}).json()["items"] == []
    assert client.get("/api/platform/search", params={"q": "责任人", "project_id": "unknown"}).json()["items"] == []
    k = result["items"][0]
    client.post(f'/api/platform/knowledge/{published["knowledge_id"]}/actions', headers=HEADERS,
                json={"action": "withdraw", "revision": k["revision"], "note": "演示停用"})
    assert client.get("/api/platform/search", params={"q": "责任人"}).json()["items"] == []
    k = client.get("/api/platform/state").json()["knowledge"][0]
    client.post(f'/api/platform/knowledge/{k["knowledge_id"]}/actions', headers=HEADERS,
                json={"action": "rollback", "target_version": 1, "revision": k["revision"], "note": "恢复"})
    client.put(f'/api/platform/sources/{s["source_id"]}', headers=HEADERS,
               json={"name": s["name"], "version_label": "v2", "revision": s["revision"]})
    assert client.get("/api/platform/search", params={"q": "责任人"}).json()["items"] == []


def test_project_product_line_is_retained_on_published_knowledge(client):
    p = client.post("/api/platform/projects", headers=HEADERS, json={"name": "演示学校", "product_line": "学校"}).json()
    s = source(client)
    c = candidate(client, s["source_id"])
    body = {key: c[key] for key in ("question", "answer", "source_id", "location", "excerpt", "required_terms", "applicability")}
    body.update(project_id=p["project_id"], revision=c["revision"])
    c = client.put(f'/api/platform/candidates/{c["candidate_id"]}', headers=HEADERS, json=body).json()
    publish(client, c)
    items = client.get("/api/platform/search", params={"q": "责任人", "product_line": "学校", "project_id": p["project_id"]}).json()["items"]
    assert len(items) == 1 and items[0]["product_line"] == "学校"
    assert client.get("/api/platform/search", params={"q": "责任人", "product_line": "厂房"}).json()["items"] == []


def test_favorite_idempotency_recent_dedup_and_persistence(client):
    s = source(client)
    c = publish(client, candidate(client, s["source_id"]))
    path = f'/api/platform/knowledge/{c["knowledge_id"]}/personal'
    for _ in range(2):
        response = client.post(path, headers=HEADERS, json={"favorite": True, "visit": True})
        assert response.status_code == 200
    state = client.get("/api/platform/state").json()
    assert state["favorites"] == [c["knowledge_id"]] and len(state["recent"]) == 1
    assert PlatformStore(client.app.state.platform_store.path).snapshot()["recent"] == state["recent"]
    client.post(path, headers=HEADERS, json={"favorite": False})
    assert client.get("/api/platform/state").json()["favorites"] == []
    assert client.post("/api/platform/knowledge/nonexistent/personal", headers=HEADERS, json={"visit": True}).status_code == 404


def test_recent_is_bounded(tmp_path):
    store = PlatformStore(tmp_path / "state.json")
    state = store._read()
    state["knowledge"] = {str(i): {} for i in range(25)}
    store._write(state)
    for i in range(25):
        store.personal_action(str(i), visit=True)
    recent = store.snapshot()["recent"]
    assert len(recent) == 20 and recent[0]["knowledge_id"] == "24" and recent[-1]["knowledge_id"] == "5"


def test_shared_definitions_validate_without_reading_catalog(tmp_path):
    from app.trial.platform_app import load_definitions
    folder = tmp_path / ".ai-growth" / "config"
    folder.mkdir(parents=True)
    taxonomy = {"actions": [{"id": f"02.{i:02}", "name": f"动作{i}"} for i in range(13)], "nodes": []}
    architecture = {"product_lines": [{"id": str(i), "name": f"产品{i}"} for i in range(13)]}
    (folder / "taxonomy.json").write_text(json.dumps(taxonomy), encoding="utf-8")
    (folder / "architecture.json").write_text(json.dumps(architecture), encoding="utf-8")
    contract_path = folder / "contract.json"
    contract = {"taxonomy_ref": ".ai-growth/config/taxonomy.json", "architecture_ref": ".ai-growth/config/architecture.json", "catalog_ref": "DO_NOT_READ"}
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    definitions = load_definitions(contract_path)
    assert len(definitions["actions"]) == 13 and len(definitions["version"]) == 64
    with TestClient(create_app(tmp_path / "state.json", contract_path=contract_path)) as configured:
        assert configured.post("/api/platform/sources", headers=HEADERS, json={"name": "x", "version_label": "v1", "product_line": "错误产品"}).status_code == 422
        s = configured.post("/api/platform/sources", headers=HEADERS, json={"name": "x", "version_label": "v1", "product_line": "产品1"}).json()
        c = candidate(configured, s["source_id"])
        body = {key: c[key] for key in ("question", "answer", "source_id", "location", "excerpt", "required_terms", "applicability")}
        body.update(action_id="unrecognized", revision=c["revision"])
        assert configured.put(f'/api/platform/candidates/{c["candidate_id"]}', headers=HEADERS, json=body).status_code == 422
        body["action_id"] = "02.01"
        assert configured.put(f'/api/platform/candidates/{c["candidate_id"]}', headers=HEADERS, json=body).status_code == 200
    contract["taxonomy_ref"] = "../outside.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(ValueError, match="越界"):
        load_definitions(contract_path)
