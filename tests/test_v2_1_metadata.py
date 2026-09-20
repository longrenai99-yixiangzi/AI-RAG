from scripts.audit_v2_1_metadata import value_state


def test_metadata_never_promotes_inferred_to_verified():
    assert value_state("project", {"project": {"value": ["项目A"], "confidence": 0.8}}, {}) == "INFERRED"
    assert value_state("project", {"project": {"value": ["项目A"], "verified": True}}, {}) == "VERIFIED"
    assert value_state("stage", {}, {}) == "MISSING"
