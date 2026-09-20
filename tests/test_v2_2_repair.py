from scripts.repair_v2_2_too_short import is_navigation, repair_text


def test_navigation_stays_quarantined_and_parent_context_repairs_text():
    assert is_navigation("- [[wiki/topics/设计支持|设计支持]]")
    assert "[章节上下文]" in repair_text("第一章 > 设计支持", "短正文")
