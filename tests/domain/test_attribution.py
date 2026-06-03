from auto_qc.domain.attribution import get_attribution_rules_path, get_attribution_rules_text


def test_rules_path_exists():
    path = get_attribution_rules_path()
    assert path.endswith("attribution-rules.md")


def test_rules_text_contains_categories():
    text = get_attribution_rules_text()
    assert "A01" in text or "归因" in text
