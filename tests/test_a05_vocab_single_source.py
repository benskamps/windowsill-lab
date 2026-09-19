"""One definition per contract, and the branch that makes it load-bearing.

`lab.a05_vocab` exists because a restated contract is not a contract: on
2026-08-19/20 the sky and blend gates taught the engine five new words while
`lab.checks` kept the old thirteen (VET-F1), and the first honest refutation
those gates drew would have quarantined a whole receipt. The module fixed
that surface. Two others went on restating contracts anyway, and these tests
hold all of them:

* **`lab.shelf`** hand-copied the vocabulary's gate/identity split, and
  `_gates_silent` had no final branch. A word the engine knew and shelf did
  not matched neither `if`, contributed no parking reason, and read exactly
  like "every gate silent" — which is the condition for
  `promotable-awaiting-ben`. Worse than VET-F1 in kind: the checker's drift
  was loud, this one recommended a star for ExoFOP on the strength of a gate
  nobody read.
* **`lab.checks`** hand-copied `DOSSIER_REQUIRED_PANELS`, and its own comment
  called it an echo. It could not import the producer, because gate 6 must
  stay readable without numpy — so the contract moved to the stdlib-only
  module and both sides read it there. The last test here guards that reason,
  which is the thing a future "just import it from a05_sensitivity" would
  break.

The drift tests do not assert that today's sets happen to agree — they did
agree, which is why the defect was invisible. They add a word to the
vocabulary and assert it ARRIVES at the reader, which is only true of a
derivation.
"""
from __future__ import annotations

import builtins
import importlib
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

from lab import a05_sensitivity, a05_vocab, checks, shelf

from tests.test_shelf_exit import TODAY, lead_row, receipt


def _probe(module_name: str):
    """A private copy of a `lab` module, executed fresh against the CURRENT
    `lab.a05_vocab` in `sys.modules`.

    Reloading the real module would leave the mutation behind for every other
    test in the session; this leaves the shared one untouched.
    """
    source = Path(sys.modules[module_name].__file__)
    probe_name = f"{module_name}__probe"
    spec = importlib.util.spec_from_file_location(probe_name, source)
    probe = importlib.util.module_from_spec(spec)
    sys.modules[probe_name] = probe
    try:
        spec.loader.exec_module(probe)
    finally:
        del sys.modules[probe_name]
    return probe


# ------------------------------------------- the vocabulary is a partition --

def test_the_vocabulary_is_exactly_its_three_groups():
    assert a05_vocab.MACHINE_DISPOSITIONS == (
        *a05_vocab.GATE_DISPOSITIONS,
        *a05_vocab.IDENTITY_DISPOSITIONS,
        a05_vocab.LEAD_DISPOSITION,
    ), "a word must enter the vocabulary through a group, or shelf cannot grade it"
    assert len(set(a05_vocab.MACHINE_DISPOSITIONS)) == \
        len(a05_vocab.MACHINE_DISPOSITIONS), "a word in two groups grades twice"


def test_shelf_reads_the_partition_rather_than_restating_it():
    assert shelf.GATE_VERDICTS == frozenset(a05_vocab.GATE_DISPOSITIONS)
    assert shelf.IDENTITY_VERDICTS == frozenset(a05_vocab.IDENTITY_DISPOSITIONS)
    assert shelf.LEAD == a05_vocab.LEAD_DISPOSITION
    assert (shelf.GATE_VERDICTS | shelf.IDENTITY_VERDICTS | {shelf.LEAD}) == \
        a05_vocab.MACHINE_VOCABULARY, \
        "_gates_silent's branches must be exhaustive over the vocabulary"


# ------------------------------------------------------------ drift tests --

def test_a_gate_word_added_to_the_vocabulary_reaches_shelf(monkeypatch):
    """The VET-F1 shape, on shelf. Fails against a hand-copied literal."""
    monkeypatch.setattr(
        a05_vocab, "GATE_DISPOSITIONS",
        a05_vocab.GATE_DISPOSITIONS + ("aurora-contamination",))
    monkeypatch.setattr(
        a05_vocab, "MACHINE_VOCABULARY",
        a05_vocab.MACHINE_VOCABULARY | {"aurora-contamination"})
    assert "aurora-contamination" in _probe("lab.shelf").GATE_VERDICTS


def test_a_panel_added_to_the_dossier_contract_reaches_the_checker(monkeypatch):
    """Same shape, on the dossier contract checks.py used to echo."""
    monkeypatch.setattr(
        a05_vocab, "DOSSIER_REQUIRED_PANELS",
        a05_vocab.DOSSIER_REQUIRED_PANELS + ("centroid_panel",))
    assert "centroid_panel" in _probe("lab.checks").A05_DOSSIER_PANELS


def test_the_producer_and_the_checker_read_one_dossier_contract():
    assert a05_sensitivity.DOSSIER_REQUIRED_PANELS is \
        a05_vocab.DOSSIER_REQUIRED_PANELS
    assert checks.A05_DOSSIER_PANELS is a05_vocab.DOSSIER_REQUIRED_PANELS


# --------------------------------- the silent promotion _gates_silent left --

def _two_clean_sectors(tmp_path):
    """The setup that grades `promotable-awaiting-ben` — every criterion clear.

    Mirrors test_shelf_exit's promotable case on purpose: the point of the
    tests below is that ONE extra row flips it, and that it did not.
    """
    receipt(tmp_path, "hunt-2026-08-14-s2.json", 2, "2026-08-14T10:00:00",
            [lead_row(depth_err=0.002)])
    return receipt(tmp_path, "hunt-2026-08-15-s3.json", 3,
                   "2026-08-15T10:00:00", [lead_row(depth_err=0.002)])


def test_the_baseline_star_really_is_promotable(tmp_path):
    (e,) = shelf.register(_two_clean_sectors(tmp_path), rulings=None,
                          today=TODAY)
    assert e["promotable"] is True and e["parked_on"] == []


def test_a_disposition_outside_the_vocabulary_parks_the_star(tmp_path):
    """An ungraded word is not a passed gate.

    Before 2026-09-19 this row fell through both branches of `_gates_silent`,
    added no parking reason, and left the star `promotable-awaiting-ben` —
    recommending it to ExoFOP on evidence the shelf could not read.
    """
    hunts = _two_clean_sectors(tmp_path)
    receipt(tmp_path, "hunt-2026-08-16-s4.json", 4, "2026-08-16T10:00:00",
            [lead_row(depth_err=0.002, disposition="aurora-contamination")])

    (e,) = shelf.register(hunts, rulings=None, today=TODAY)
    assert e["promotable"] is False
    assert e["state"] == "parked"
    assert any("aurora-contamination" in r and "ungraded" in r
               for r in e["parked_on"]), \
        f"the unreadable word must be NAMED in the reason: {e['parked_on']}"
    assert not any("refut" in r for r in e["parked_on"]), \
        "parking is not refutation — the shelf cannot read the word, that is all"


def test_lead_rows_themselves_are_not_parked_as_ungraded(tmp_path):
    """The terminal state is in the vocabulary and must stay exempt."""
    (e,) = shelf.register(_two_clean_sectors(tmp_path), rulings=None,
                          today=TODAY)
    assert not any("ungraded disposition" in r for r in e["parked_on"])


# ------------------------------------- why the contract lives in a05_vocab --

def test_the_checker_stays_importable_without_numpy():
    """Gate 6 re-derives receipts and must not need the engine that wrote them.

    This is the constraint that decided WHERE the dossier contract lives:
    importing `DOSSIER_REQUIRED_PANELS` from its producer would have dragged
    numpy into `lab.checks`, so the contract moved to the stdlib-only module.
    A future simplification that points checks.py back at `a05_sensitivity`
    passes every test above and fails this one.
    """
    real_import = builtins.__import__

    def no_numpy(name, *args, **kwargs):
        if name == "numpy" or name.startswith("numpy."):
            raise ImportError("numpy is unavailable in this test")
        return real_import(name, *args, **kwargs)

    stashed = {k: v for k, v in sys.modules.items()
               if k == "numpy" or k.startswith("numpy.")
               or k in ("lab.checks", "lab.a05_vocab")}
    for k in stashed:
        del sys.modules[k]
    builtins.__import__ = no_numpy
    try:
        fresh = importlib.import_module("lab.checks")
        assert fresh.A05_DOSSIER_PANELS
        assert fresh.A05_MACHINE_VOCABULARY
    finally:
        builtins.__import__ = real_import
        sys.modules.update(stashed)
        importlib.reload(importlib.import_module("lab.checks"))
