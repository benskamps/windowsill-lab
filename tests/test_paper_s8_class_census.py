"""§8's class census — the prose checked against the committed output.

``scripts/paper_s8_class_census.py`` counts the class §8 of the survey paper
proposes to test, over public catalogues too large to commit. What is committed
is its output, ``docs/survey/2026-10-08-s8-class-census.json``, with the
SHA-256 of every catalogue file it read. These tests keep the draft's §8 in
agreement with that output, and keep the script's own arithmetic honest
without the catalogues: the self-test reproduces §6.3 from the exhibit's row.

Stdlib-only apart from the script's own numpy import, like its neighbours.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "paper_s8_class_census.py"
CENSUS = ROOT / "docs" / "survey" / "2026-10-08-s8-class-census.json"
TMAG = ROOT / "docs" / "survey" / "2026-10-08-s8-tic-tmag.csv"
PREREG = ROOT / "docs" / "preregistrations" / "2026-10-08-paper-s8-class-census.md"
DRAFT = ROOT / "docs" / "papers" / "2026-09-18-survey-methods-draft.md"

sys.path.insert(0, str(ROOT / "scripts"))
import paper_s8_class_census as s8                      # noqa: E402


def _census():
    return json.loads(CENSUS.read_text(encoding="utf-8"))


def _section8():
    text = DRAFT.read_text(encoding="utf-8")
    a = text.index("## 8 ·")
    b = text.index("## 9 ·")
    return text[a:b]


def test_selftest_passes():
    proc = subprocess.run([sys.executable, str(SCRIPT), "--selftest"],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SELFTEST PASSED" in proc.stdout


def test_script_cuts_are_the_preregistered_ones():
    """A cut changed in the script and not in the pre-registration is a defect."""
    pre = PREREG.read_text(encoding="utf-8")
    assert s8.PRIMARY == {"mes": 50.0, "b": 0.7, "rp_rj": 2.0,
                          "teff": 4000.0, "tmag": 12.0}
    for needle in ("≥ 50", "≥ 0.7", "≥ 22.42 R⊕", "≤ 4,000 K", "≥ 12.0",
                   "2,300 K", "Seed 2026", "< 7.1"):
        assert needle in pre, needle
    assert s8.H_BURNING_K == 2300.0 and s8.MC_SEED == 2026
    assert s8.GRID == {"mes": [20.0, 50.0, 100.0], "b": [0.6, 0.7, 0.8],
                       "rp_rj": [1.5, 2.0, 2.5], "teff": [3900.0, 4000.0, 4500.0],
                       "tmag": [11.0, 12.0, 13.0]}


def test_committed_tmag_table_is_the_one_the_census_read():
    import hashlib
    digest = hashlib.sha256(TMAG.read_bytes()).hexdigest()
    assert _census()["inputs"]["tic_tmag.csv"] == digest


def test_positive_control_holds_in_the_output():
    pc = _census()["positive_control"]
    assert pc["tic"] == 374861595 and pc["in_class"] is True


def test_section8_numbers_match_the_census():
    c = _census()
    sec = _section8()
    ex = c["exploratory_breadth_secondary_pass"]
    excluded = [s for s in ex["stars"] if s["verdict"] == "stellar-excluded"]
    oe_fail = sum(1 for s in excluded if s["odd_even_stat"] > 3)
    paired = [s for s in excluded if 0 < s["odd_even_stat"] <= 3]
    roche = sum(1 for s in paired if s["period_d"] < s["p_roche_13mj_d"])
    mc = c["monte_carlo"]
    g = c["grid"]
    b = c["breadth_union"]
    expect = [
        f"{c['primary_file_tces']:,} TCEs on {c['primary_file_stars']:,} stars",
        f"| in C | **{c['class_stars']}** ({c['class_tces']} TCEs) |",
        f"| promoted to TOI | {c['class_stars_promoted']} |",
        f"| **never promoted** | **{c['unpromoted_stars']}** (one is a CTOI) |",
        f"| — significant secondary found by SPOC | {c['secondary_pass']['secondary-detected']} |",
        f"| — stellar companion excluded by the §6.3 bound | **{c['secondary_pass']['stellar-excluded']}** |",
        f"| — not testable from the catalogue | {c['secondary_pass']['not-testable']} |",
        f"**{mc['class_stars']['median']:.0f} ({mc['class_stars']['p16']:.0f}–{mc['class_stars']['p84']:.0f})** stars",
        f"**{mc['unpromoted_stars']['median']:.0f} ({mc['unpromoted_stars']['p16']:.0f}–{mc['unpromoted_stars']['p84']:.0f})** unpromoted",
        f"{g['cells']} cut combinations",
        f"from {g['class_min']} to {g['class_max']} stars",
        f"from {g['unpromoted_min']} to {g['unpromoted_max']}",
        f"| in C in any product | **{b['class_stars']}** |",
        f"| never promoted | **{b['unpromoted_stars']}** ({b['unpromoted_ctoi']} are CTOIs) |",
        f"| significant secondary found by SPOC | {ex['verdicts']['secondary-detected']} |",
        f"| stellar companion **excluded** by the bound | {ex['verdicts']['stellar-excluded']} |",
        f"| not excluded | {ex['verdicts']['not-excluded']} |",
        f"**{oe_fail} of the {len(excluded)}",
        f"**{len(paired)} pass**",
        f"for {_num_word(roche)}, the period is shorter",
        f"{c['n_tce_files_breadth']} single- and multi-sector files",
    ]
    flat = re.sub(r"\s+", " ", sec)
    for e in expect:
        assert re.sub(r"\s+", " ", e) in flat, f"§8 does not say: {e!r}"
    assert ex["preregistered"] is False
    assert "**not pre-registered**" in sec


def _num_word(n):
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
             7: "seven", 8: "eight", 9: "nine", 10: "ten"}
    return words.get(n, str(n))


def test_section8_claims_no_planet():
    sec = _section8()
    assert "It does not\ncount planets." in sec or "It does not count planets." in sec
    banned = re.compile(r"\b(new planets?|planet candidates? (are|were) found|"
                        r"we (confirm|discover))\b", re.I)
    assert not banned.search(sec)
