"""C03 — the OEIS b-file extension instrument.

Every test here runs OFFLINE. ``fetch_bfile`` reads a pinned cache under
``LAB_HOME/oeis``, so the fixtures write a b-file there and no test touches
oeis.org — which matters twice: CI has no business depending on a third party's
uptime, and OEIS rate-limits a polite client to 403 under steady polling, so a
suite that fetched would poison the real runner's cache path for the box.

The instrument's whole claim is that it cannot fake an extension, so most of
this file is negative controls: the positive path is one test and the ways a
receipt can lie are six.
"""
import json

import pytest

from lab import c03
from lab.checks import check_c03


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def lab_home(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_HOME", str(tmp_path))
    return tmp_path


def _seed_cache(tmp_path, a_number, pairs):
    d = tmp_path / "oeis"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"b{a_number[1:]}.txt").write_bytes(
        "".join(f"{i} {v}\n" for i, v in pairs).encode("utf-8"))


def _truthful_bfile(a_number, n_terms):
    """The first ``n_terms`` of a registered target, per its own method A."""
    tgt = c03.TARGETS[a_number]
    vals = tgt.generate(tgt.offset + n_terms)
    return [(tgt.offset + k, vals[tgt.offset + k]) for k in range(n_terms)]


# ── the generators, and the independence contract ────────────────────────────

def test_motzkin_recurrence_reproduces_the_known_prefix():
    assert c03._motzkin_recurrence(10) == [
        1, 1, 2, 4, 9, 21, 51, 127, 323, 835]


def test_fibonacci_iterative_reproduces_the_known_prefix():
    assert c03._fibonacci_iterative(10) == [
        0, 1, 1, 2, 3, 5, 8, 13, 21, 34]


@pytest.mark.parametrize("a_number", sorted(c03.TARGETS))
def test_the_two_methods_are_independent_and_agree(a_number):
    """The contract that makes a cross-check worth running: for every target,
    the witness must reproduce method A across a wide index range. Two runs of
    ONE algorithm agree about their shared bug — that is why the registry
    stores a pair and why this is parametrized over the whole registry rather
    than written once for the seed target."""
    tgt = c03.TARGETS[a_number]
    n = 300
    a_vals = tgt.generate(tgt.offset + n)
    indices = list(range(tgt.offset, tgt.offset + n))
    b_vals = tgt.witness(indices)
    assert len(b_vals) == n
    assert all(b_vals[i] == a_vals[i] for i in indices)


def test_the_registry_pair_is_never_the_same_algorithm_twice():
    for a_number, tgt in c03.TARGETS.items():
        assert tgt.method_a != tgt.method_b, a_number
        assert tgt.generate is not tgt.witness, a_number


# ── the happy path ───────────────────────────────────────────────────────────

def test_a_truthful_bfile_reproduces_cross_checks_and_extends(lab_home):
    pairs = _truthful_bfile("A001006", 400)
    _seed_cache(lab_home, "A001006", pairs)
    r = c03.run_c03("A001006", extend_terms=16, budget_seconds=60.0)
    assert r.reproduced is True
    assert r.cross_checked is True
    assert r.reach_verdict == "in-reach"
    assert r.status == "pass"
    assert r.new_terms_agreed == 16
    assert all(t["index"] > r.known_last_index for t in r.new_terms)
    # the fragment is exactly the agreed terms, in b-file form
    lines = r.extension_fragment.strip().splitlines()
    assert len(lines) == 16
    assert lines[0].split()[0] == str(r.known_last_index + 1)
    assert check_c03(c03.to_report(r))[0] is True


def test_the_source_is_pinned_and_read_from_cache_not_the_network(lab_home):
    pairs = _truthful_bfile("A000045", 120)
    _seed_cache(lab_home, "A000045", pairs)
    r = c03.run_c03("A000045", extend_terms=8, budget_seconds=60.0)
    assert r.source_from_cache is True
    assert len(r.source_sha256) == 64


# ── refusals: the instrument must be able to say no ──────────────────────────

def test_a_bfile_it_cannot_reproduce_refuses_and_never_extends(lab_home):
    """We do not get to extend a sequence we cannot reproduce. One corrupted
    term anywhere in the known range must stop the run before stage 4 — and it
    must be graded UNRESOLVED, not failed: a refusal is the instrument working.
    """
    pairs = _truthful_bfile("A001006", 300)
    pairs[137] = (pairs[137][0], pairs[137][1] + 1)      # one wrong integer
    _seed_cache(lab_home, "A001006", pairs)
    r = c03.run_c03("A001006", extend_terms=16, budget_seconds=60.0)
    assert r.reproduced is False
    assert r.first_mismatch["index"] == 137
    assert r.cross_checked is False
    assert r.extension_attempted is False
    assert r.new_terms == []
    assert r.status == "refused"
    verdict, detail = check_c03(c03.to_report(r))
    assert verdict is None and "refused before extending" in detail


def test_an_out_of_reach_projection_is_a_result_not_an_attempt(lab_home):
    """A zero budget prices the work and declines it. `out-of-reach` is a
    RESULT (UNKNOWNS.md's rule) reported with its projection — the run still
    reproduces and cross-verifies, it simply does not extend."""
    pairs = _truthful_bfile("A001006", 300)
    _seed_cache(lab_home, "A001006", pairs)
    r = c03.run_c03("A001006", extend_terms=16, budget_seconds=0.0)
    assert r.reproduced is True and r.cross_checked is True
    assert r.reach_verdict == "out-of-reach"
    assert r.extension_attempted is False
    assert r.new_terms_agreed == 0
    assert r.status == "null"
    assert r.projected_seconds_for_extension >= 0.0


def test_an_unregistered_target_raises_rather_than_guessing(lab_home):
    with pytest.raises(KeyError):
        c03.run_c03("A999999")


# ── the check cannot be talked out of the arithmetic ─────────────────────────

@pytest.fixture
def truthful_report(lab_home):
    _seed_cache(lab_home, "A001006", _truthful_bfile("A001006", 300))
    return c03.to_report(
        c03.run_c03("A001006", extend_terms=12, budget_seconds=60.0))


def _mutated(report, fn):
    bad = json.loads(json.dumps(report))
    fn(bad)
    return check_c03(bad)


def test_check_confirms_a_truthful_receipt(truthful_report):
    verdict, detail = check_c03(truthful_report)
    assert verdict is True
    assert "re-derived and confirmed by both" in detail


def test_check_refuses_a_fabricated_new_term(truthful_report):
    verdict, detail = _mutated(
        truthful_report,
        lambda b: b["new_terms"][0].update(
            value=str(int(b["new_terms"][0]["value"]) + 1)))
    assert verdict is False and "receipt says" in detail


def test_check_refuses_a_reproduction_hash_that_does_not_regenerate(
        truthful_report):
    verdict, detail = _mutated(
        truthful_report,
        lambda b: b.update(generated_prefix_sha256="0" * 64))
    assert verdict is False and "regenerating" in detail


def test_check_refuses_an_unregistered_target(truthful_report):
    verdict, detail = _mutated(truthful_report,
                               lambda b: b.update(target="A999999"))
    assert verdict is False and "not in the registry" in detail


def test_check_refuses_an_extension_inside_the_known_range(truthful_report):
    verdict, detail = _mutated(
        truthful_report, lambda b: b["new_terms"][0].update(index=5))
    assert verdict is False and "not past the b-file's end" in detail


def test_check_refuses_an_inflated_agreed_count(truthful_report):
    verdict, detail = _mutated(truthful_report,
                               lambda b: b.update(new_terms_agreed=999))
    assert verdict is False and "re-derivation finds" in detail


def test_check_refuses_methods_the_registry_does_not_name(truthful_report):
    verdict, detail = _mutated(
        truthful_report, lambda b: b.update(method_b="forward iteration"))
    assert verdict is False and "does not" in detail


def test_check_refuses_an_index_range_that_does_not_span_its_terms(
        truthful_report):
    verdict, detail = _mutated(truthful_report,
                               lambda b: b.update(known_last_index=99))
    assert verdict is False and "does not" in detail


def test_check_bounds_the_work_a_hostile_receipt_can_buy(truthful_report):
    """A receipt is untrusted input, and 'regenerate n terms' with an
    attacker-chosen n is a denial of service with a check's name on it."""
    verdict, detail = _mutated(
        truthful_report,
        lambda b: b.update(known_terms=10 ** 9,
                           known_last_index=b["known_first_index"] + 10 ** 9 - 1))
    assert verdict is False and "bound" in detail


def test_check_ignores_a_report_that_is_not_c03(truthful_report):
    verdict, _ = _mutated(truthful_report,
                          lambda b: b.update(experiment="M01-ising"))
    assert verdict is None


# ── the reason this milestone exists: the planner can now reach it ───────────

def test_c03_has_a_runner_so_the_planner_can_dispatch_the_frontier():
    """The whole point of the 2026-09-09 reconcile. `plan_turn` admits an OPEN
    milestone only if it has a registered runner, so C02/C03/C04/A06/I02/I03/
    B01/B02 — the eight that ARE the redefined product — were skipped silently
    on every turn while the planner replayed verified canaries. C03 is the
    first of them to become dispatchable."""
    from lab import curriculum
    assert curriculum.RUNNERS.get("C03") == "c03"
    # …and it takes no scheduler seed/device, like C01, so an unattended
    # `lab next --seed N --device cuda` cannot abort it at argparse.
    assert curriculum.RUNNER_SCHEDULER_OPTIONS.get(
        "C03", frozenset()) == frozenset()
