from scripts.normalize_sarif import normalize_sarif


def test_keeps_valid_severity_scores_as_strings_and_removes_invalid_values() -> None:
    sarif = {
        "runs": [
            {
                "tool": {
                    "driver": {
                        "rules": [
                            {"properties": {"security-severity": "5.5"}},
                            {"properties": {"security-severity": 8.0}},
                            {"properties": {"security-severity": "null"}},
                            {"properties": {"security-severity": None}},
                            {"properties": {"security-severity": "11"}},
                        ]
                    }
                }
            }
        ]
    }

    normalized = normalize_sarif(sarif)
    rules = normalized["runs"][0]["tool"]["driver"]["rules"]

    assert rules[0]["properties"]["security-severity"] == "5.5"
    assert rules[1]["properties"]["security-severity"] == "8.0"
    assert all("security-severity" not in rule["properties"] for rule in rules[2:])
