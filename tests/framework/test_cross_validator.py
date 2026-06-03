from auto_qc.framework.cross_validator import stratified_sample, compare_results


def test_stratified_sample():
    results = (
        [{"id": f"v{i}", "violations": [{"rule_id": "R01"}]} for i in range(50)] +
        [{"id": f"p{i}", "violations": []} for i in range(50)]
    )
    sample = stratified_sample(results, violation_ratio=0.2, non_violation_ratio=0.2)
    assert len(sample) > 0
    assert any(r.get("violations") for r in sample)
    assert any(not r.get("violations") for r in sample)


def test_compare_identical():
    original = [{"id": "1", "violations": [{"rule_id": "R01"}]}]
    recheck = [{"id": "1", "violations": [{"rule_id": "R01"}]}]
    result = compare_results(original, recheck)
    assert result.mismatches == 0
    assert result.discrepancy_rate == 0.0
    assert result.status == "ok"


def test_compare_different():
    original = [{"id": "1", "violations": [{"rule_id": "R01"}]}]
    recheck = [{"id": "1", "violations": []}]
    result = compare_results(original, recheck)
    assert result.mismatches == 1
    assert result.discrepancy_rate > 0
