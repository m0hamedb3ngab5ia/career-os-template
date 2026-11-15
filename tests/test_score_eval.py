"""scripts/score_eval.py: only the comparison logic and the golden fixtures; the live run needs `claude`."""
from __future__ import annotations

import pytest

from careeros.models import Posting
from conftest import ROOT, load_script

pytestmark = pytest.mark.unit

ev = load_script("scripts/score_eval.py")


@pytest.mark.parametrize("expect,score,problems", [
    ({"decision": "skip", "fit": None}, {"decision": "skip", "fit": 0}, []),
    ({"decision": "prepare", "fit": [70, 89]}, {"decision": "prepare", "fit": 78}, []),
    ({"decision": "prepare", "fit": [70, 89]}, {"decision": "prepare", "fit": 95}, ["fit 95 not in 70-89"]),
    ({"decision": "skip", "fit": [0, 60]}, {"decision": "prepare", "fit": 72},
     ["decision prepare != skip", "fit 72 not in 0-60"]),
    ({"decision": "skip", "fails": ["yoe_gt_3"]}, {"decision": "skip", "fit": 0, "hard_filter_fails": []},
     ["hard_filter_fails missing yoe_gt_3"]),
    ({"decision": "skip"}, None, ["no score.json"]),
])
def test_compare(expect, score, problems):
    assert ev.compare(expect, score) == problems


def test_golden_cases_are_valid():
    cases = ev.load_cases(ROOT / "tests" / "fixtures" / "score_eval")
    assert len(cases) >= 4
    for name, case in cases:
        Posting.model_validate(case["posting"])
        assert case["expect"].get("decision") in (None, "prepare", "skip"), name
        fit = case["expect"].get("fit")
        assert fit is None or (len(fit) == 2 and 0 <= fit[0] <= fit[1] <= 100), name
    # L-030: at least one generic posting whose fit band stays under 90 (the fit-100 saturation bug)
    assert any(c["expect"].get("fit") and c["expect"]["fit"][1] < 90 for _, c in cases)
