"""pytest-bdd step definitions for verify_groundtruth.feature.

Binds scenarios to the reference verifier + T4 detector (no live server needed),
so the full behavioural spec runs in-process against the real corpus. Wire to a
live backend by swapping `verify_chain` for an HTTP call in `_verify` below.
"""
from __future__ import annotations

import pytest

bdd = pytest.importorskip("pytest_bdd")
from pytest_bdd import scenarios, given, when, then, parsers  # noqa: E402

from provtests import corpus, mutators as M  # noqa: E402
from provtests import ground_truth as G  # noqa: E402
from provtests.reference_verifier import (  # noqa: E402
    verify_chain, compute_percentage, compute_designation,
)
from provtests.t4_detector import suspicious_ids, _models  # noqa: E402
from provtests.scoring import score_case  # noqa: E402

pytestmark = pytest.mark.corpus
scenarios("verify_groundtruth.feature")


def _verify(chain, with_t4=False):
    return verify_chain(chain, with_t4=with_t4)


def _f1(truth, flagged):
    tp = len(truth & flagged)
    p = tp / len(flagged) if flagged else 0.0
    r = tp / len(truth) if truth else 1.0
    return 2 * p * r / (p + r) if (p + r) else 0.0


@pytest.fixture
def ctx():
    return {}


# ---- Background -----------------------------------------------------------

@given("the training corpus is loaded")
def _loaded(ctx):
    ctx["n"] = len(corpus.load())
    assert ctx["n"] == 1000


# ---- A. core --------------------------------------------------------------

@when("I compute the percentage for every clean chain")
def _pct_all(ctx):
    bad = []
    for r in corpus.by_family("clean"):
        got = compute_percentage(corpus.attestations(r))
        lab = r["labels"]["canadian_content_percentage"]
        ok = (got is None and lab == 0) or (got is not None and abs(got - lab) <= G.PCT_TOL)
        if not ok:
            bad.append(r["chain"]["product_attestation_id"])
    ctx["bad_pct"] = bad


@then("each computed percentage should match its label within 0.5")
def _pct_ok(ctx):
    assert ctx["bad_pct"] == []


@when("I compute the designation for every clean chain")
def _desig_all(ctx):
    bad = [r["chain"]["product_attestation_id"] for r in corpus.by_family("clean")
           if compute_designation(corpus.attestations(r), corpus.leaf_id(r)) != r["labels"]["designation"]]
    ctx["bad_desig"] = bad


@then("each designation should equal its label")
def _desig_ok(ctx):
    assert ctx["bad_desig"] == []


@given(parsers.parse('a synthetic chain at {pct:g} percent Canadian finished in "{country}" with labour hours {hours:g}'))
def _syn_pct(ctx, pct, country, hours):
    ctx["chain"] = M.synthetic_pct(pct, country, hours)


@given(parsers.parse('a synthetic chain whose last node is "{action}" with labour hours {hours:g} in "{country}" at {pct:g} percent'))
def _syn_action(ctx, action, hours, country, pct):
    ctx["chain"] = M.synthetic_pct(pct, country, hours, action=action)


@when("I verify the synthetic chain")
def _verify_syn(ctx):
    ctx["resp"] = _verify(ctx["chain"], with_t4=False)


@then(parsers.parse('the designation should be "{value}"'))
def _desig_is(ctx, value):
    assert ctx["resp"]["designation"] == value


# ---- B. precision ---------------------------------------------------------

@when("I verify every clean chain with the reference verifier")
def _verify_clean(ctx):
    flagged = [r for r in corpus.by_family("clean")
               if _verify(r["chain"], with_t4=True)["anomalies"]]
    invalid = [r for r in corpus.by_family("clean")
               if not _verify(r["chain"], with_t4=True)["chain_valid"]]
    ctx["clean_flagged"] = flagged
    ctx["clean_invalid"] = invalid


@then("no clean chain should report an anomaly")
def _no_clean_anoms(ctx):
    assert ctx["clean_flagged"] == []


@then("every clean chain should be valid")
def _clean_valid(ctx):
    assert ctx["clean_invalid"] == []


# ---- C. hard-rule families ------------------------------------------------

@given(parsers.parse('the corpus cases for family "{family}"'))
def _family_rows(ctx, family):
    ctx["family"] = family
    ctx["rows"] = corpus.by_family(family)
    assert ctx["rows"], f"no rows for {family}"


@when("I verify each with the reference verifier")
def _verify_each(ctx):
    resps = []
    for r in ctx["rows"]:
        resps.append((r, _verify(r["chain"], with_t4=False)))
    ctx["resps"] = resps


@then(parsers.parse("the mean anomaly F1 should be at or above {floor:g}"))
def _mean_f1(ctx, floor):
    fs = [_f1(corpus.expected_anomaly_ids(r),
              {a["attestation_id"] for a in resp["anomalies"]})
          for r, resp in ctx["resps"]]
    mean = sum(fs) / len(fs)
    assert mean >= floor, f"{ctx['family']}: {mean:.3f} < {floor}"


@then("every flagged anomaly should use one of the eleven real type strings")
def _real_types(ctx):
    for _r, resp in ctx["resps"]:
        for a in resp["anomalies"]:
            assert a["type"] in G.ANOMALY_TYPES or a["type"] == "statistical_outlier"


@then("each such chain should be invalid")
def _each_invalid(ctx):
    for _r, resp in ctx["resps"]:
        assert resp["chain_valid"] is False


@then(parsers.parse('the union of flagged types should include "{t}"'))
def _union_includes(ctx, t):
    union = set()
    for _r, resp in ctx["resps"]:
        union |= {a["type"] for a in resp["anomalies"]}
    assert t in union


# ---- D. micro hard-rule ---------------------------------------------------

@given(parsers.parse("a synthetic node producing 10 units consumed 6 and 6 by two children"))
def _mb_over(ctx):
    ctx["chain"], ctx["inj"] = M.mass_balance_over()


@given(parsers.parse("a synthetic node producing 10 units consumed 4 by one child"))
def _mb_leftover(ctx):
    ctx["chain"], ctx["inj"] = M.mass_balance_leftover()


@given(parsers.parse('a synthetic parent output unit "kg" with a child consuming in "zz"'))
def _unit(ctx):
    ctx["chain"], ctx["inj"] = M.unit_mismatch()


@given("a synthetic chain referencing a parent id not in the array")
def _dangling(ctx):
    ctx["chain"], ctx["inj"] = M.dangling_parent()


@given("a synthetic parent mutated after its child committed its content hash")
def _phm(ctx):
    ctx["chain"], ctx["inj"] = M.parent_hash_mismatch()


@given("a synthetic chain with one attestation id appearing twice")
def _replay(ctx):
    ctx["chain"], ctx["inj"] = M.replay_duplicate()


@given("a synthetic parent timestamped after its child")
def _ts(ctx):
    ctx["chain"], ctx["inj"] = M.timestamp_inversion()


@given("a synthetic node whose supplier id never appears in genuine data")
def _unknown(ctx):
    ctx["chain"], ctx["inj"] = M.unknown_supplier()


@given("a synthetic node with a labour rate far above the genuine ceiling")
def _cost(ctx):
    ctx["chain"], ctx["inj"] = M.cost_anomaly()


@given(parsers.parse('a synthetic node violating shape rule "{rule}"'))
def _shape(ctx, rule):
    ctx["chain"], ctx["inj"] = M.transformation_implausible(rule)


def _flagged_type(ctx, t):
    resp = ctx["resp"]
    hits = {a["attestation_id"] for a in resp["anomalies"] if a["type"] == t}
    assert ctx["inj"] <= hits, f"expected {ctx['inj']} flagged as {t}, got {hits}"


@then(parsers.parse('the producing node should be flagged "{t}"'))
def _producing(ctx, t):
    _flagged_type(ctx, t)


@then(parsers.parse('the consuming node should be flagged "{t}"'))
def _consuming(ctx, t):
    _flagged_type(ctx, t)


@then(parsers.parse('the referring node should be flagged "{t}"'))
def _referring(ctx, t):
    _flagged_type(ctx, t)


@then(parsers.parse('the child should be flagged "{t}"'))
def _child(ctx, t):
    _flagged_type(ctx, t)


@then(parsers.parse('the duplicated id should be flagged "{t}"'))
def _dup(ctx, t):
    _flagged_type(ctx, t)


@then(parsers.parse('that node should be flagged "{t}"'))
def _that(ctx, t):
    _flagged_type(ctx, t)


@then("no mass balance anomaly should be reported")
def _no_mb(ctx):
    assert not [a for a in ctx["resp"]["anomalies"] if a["type"] == "mass_balance_violation"]


# ---- E. T4 ----------------------------------------------------------------

@when("I run the statistical detector on each")
def _t4_each(ctx):
    m = _models()
    ctx["t4f"] = [_f1(corpus.t4_ids(r), suspicious_ids(corpus.attestations(r), models=m))
                  for r in ctx["rows"]]


@then(parsers.parse("the mean perturbed-id F1 should be at or above {floor:g}"))
def _t4_floor(ctx, floor):
    mean = sum(ctx["t4f"]) / len(ctx["t4f"])
    assert mean >= floor, f"{ctx['family']}: {mean:.3f} < {floor}"


@then(parsers.parse("the mean perturbed-id F1 should be between {lo:g} and {hi:g}"))
def _t4_between(ctx, lo, hi):
    mean = sum(ctx["t4f"]) / len(ctx["t4f"])
    assert lo <= mean <= hi


@when("I run the statistical detector on every clean chain")
def _t4_clean(ctx):
    m = _models()
    ctx["t4_clean_fp"] = sum(1 for r in corpus.by_family("clean")
                             if suspicious_ids(corpus.attestations(r), models=m))


@then("no clean chain should be flagged by the statistical detector")
def _t4_clean_zero(ctx):
    assert ctx["t4_clean_fp"] == 0


# ---- F. contract ----------------------------------------------------------

@given("any corpus chain")
def _any(ctx):
    ctx["chain"] = corpus.load()[0]["chain"]


@when("I verify it with the reference verifier")
def _verify_any(ctx):
    ctx["resp"] = _verify(ctx["chain"], with_t4=True)


@then(parsers.parse("the response should have keys product_attestation_id, canadian_content_percentage, designation, chain_valid, anomalies"))
def _keys(ctx):
    for k in ("product_attestation_id", "canadian_content_percentage",
              "designation", "chain_valid", "anomalies"):
        assert k in ctx["resp"]


@then(parsers.parse("the designation should be one of product_of_canada, made_in_canada, none"))
def _desig_set(ctx):
    assert ctx["resp"]["designation"] in G.VALID_DESIGNATIONS


@then("every anomaly should include an attestation id and a type")
def _anom_shape(ctx):
    for a in ctx["resp"]["anomalies"]:
        assert "attestation_id" in a and "type" in a


@when("I score the reference verifier over the whole corpus")
def _score_all(ctx):
    total = 0.0
    clean_total = 0.0
    clean_n = 0
    for r in corpus.load():
        lab = r["labels"]
        resp = _verify(r["chain"], with_t4=True)
        s = score_case(lab.get("attack", "clean"), lab, lab.get("t4_perturbed", []), resp)
        total += s
        if lab.get("attack", "clean") == "clean":
            clean_total += s
            clean_n += 1
    ctx["overall"] = total / 1000
    ctx["clean_score"] = clean_total / clean_n


@then(parsers.parse("the overall score should be at or above {pct:g} percent"))
def _overall(ctx, pct):
    assert ctx["overall"] * 100 >= pct, f"overall {ctx['overall']*100:.1f}% < {pct}%"


@then(parsers.parse("the clean category score should be {pct:g} percent"))
def _clean_score(ctx, pct):
    assert ctx["clean_score"] * 100 >= pct - 0.01
