"""The eval sets with perfect extraction: the corpus and engine must reach the expected plan (spec 21.1)."""

import pytest

from eval.runner import MAX_QUESTIONS, load, passed, simulate

CASES = load()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_reaches_the_expected_result(case):
    result, asked = simulate(case, case["facts"], case.get("medical", False))

    assert passed(case, result, asked), (result.kind, asked, result.plan and [s["id"] for s in result.plan["services"]])


def test_the_set_is_large_enough_and_split():
    assert len(CASES) >= 15
    assert {c["split"] for c in CASES} == {"tuning", "held_out"}
    assert len({c["id"] for c in CASES}) == len(CASES)


def test_median_questions_until_the_plan_is_at_most_three():
    counts = sorted(simulate(c, c["facts"], False)[1] for c in CASES if c["expect"] == "plan")
    assert counts[len(counts) // 2] <= MAX_QUESTIONS
