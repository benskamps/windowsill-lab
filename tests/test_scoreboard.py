"""The calibration scoreboard builds from report JSONs and stays honest vs verify."""
from __future__ import annotations

import math

from lab import scoreboard as sb
from lab.checks import ONSAGER_TC


def _m01_report():
    # χ peaks at the middle temperature → recovers ~Onsager T_c.
    return {"experiment": "M01-ising-verification",
            "T": [2.0, ONSAGER_TC, 2.5], "chi": [1.0, 9.0, 1.0]}


def _m07_report():
    per_q = []
    for q in (3, 4, 5, 6):
        tc = 1.0 / math.log(1.0 + math.sqrt(q))
        # A symmetric triple peaking exactly on the exact T_c.
        per_q.append({"q": q, "T": [tc - 0.1, tc, tc + 0.1], "chi": [1.0, 5.0, 1.0]})
    return {"experiment": "M07-potts", "per_q": per_q}


def test_collect_entries_from_fixture():
    entries = sb.collect_entries([_m01_report(), _m07_report()])
    by_id = {}
    for e in entries:
        by_id.setdefault(e.milestone, []).append(e)
    assert "M01" in by_id and "M07" in by_id
    m01 = by_id["M01"][0]
    assert abs(m01.measured - ONSAGER_TC) < 1e-6
    assert m01.exact == ONSAGER_TC
    assert m01.passed
    # M07 yields one entry per q, each landing on its exact T_c.
    assert len(by_id["M07"]) == 4
    for e in by_id["M07"]:
        assert e.passed
        assert abs(e.deviation) < 1e-6


def test_z_and_pass_semantics():
    e = sb.ScoreEntry("Mxx", "demo", measured=2.30, exact=2.2692, tol=0.1)
    assert math.isclose(e.z, (2.30 - 2.2692) / 0.1)
    assert e.passed
    far = sb.ScoreEntry("Mxx", "demo", measured=3.0, exact=2.2692, tol=0.1)
    assert not far.passed
    assert far.z > 1


def test_off_line_m14_point_is_ignored():
    # A calibration point off the Nishimori line has no exact identity → skipped;
    # a single valid on-line point is graded.
    T = 1.0
    on = -2.0 * math.tanh(1.0 / T)
    report = {"experiment": "M14-random-bond-nishimori", "calibration_points": [
        {"p": 0.5 * (1 - math.tanh(1.0 / T)), "T": T, "energy": on + 0.01},   # on-line
        {"p": 0.9, "T": T, "energy": -0.01},                                   # off-line
    ]}
    entries = sb.collect_entries([report])
    assert len(entries) == 1
    assert entries[0].milestone == "M14"
    assert entries[0].passed


def test_empty_reports_render_without_crashing():
    entries = sb.collect_entries([{"experiment": "unknown"}])
    assert entries == []
    fig = sb.build_figure(entries)
    assert fig is not None
    import matplotlib.pyplot as plt
    plt.close(fig)


def test_figure_and_png_bytes_build():
    entries = sb.collect_entries([_m01_report(), _m07_report()])
    fig = sb.build_figure(entries)
    # One y-tick per entry.
    assert len(fig.axes[0].get_yticks()) == len(entries)
    import matplotlib.pyplot as plt
    plt.close(fig)
    png = sb.figure_png_bytes(entries)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000


def test_data_uri_prefix():
    uri = sb.figure_data_uri([_m01_report_entry()])
    assert uri.startswith("data:image/png;base64,")


def _m01_report_entry():
    return sb.ScoreEntry("M01", "demo", measured=ONSAGER_TC, exact=ONSAGER_TC, tol=0.1)


def test_archive_index_embeds_scoreboard_when_png_present(tmp_path, monkeypatch):
    from lab import archive
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "scoreboard.png").write_bytes(b"\x89PNG\r\n\x1a\nfake-but-present")
    monkeypatch.setattr(archive, "REPORTS_DIR", reports)
    html = archive.render_index(runs=[])
    assert 'figure class="scoreboard"' in html
    assert "calibration scoreboard" in html
    assert "data:image/png;base64," in html


def test_archive_index_omits_scoreboard_when_png_absent(tmp_path, monkeypatch):
    from lab import archive
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(archive, "REPORTS_DIR", reports)
    html = archive.render_index(runs=[])
    assert 'figure class="scoreboard"' not in html


def test_committed_archive_scoreboard_all_within_tolerance():
    # The real committed archive (reports/ + receipts) must render a scoreboard whose
    # every point sits inside its own gate — the same verdict `lab verify` reaches.
    entries = sb.collect_entries()
    assert len(entries) >= 12, f"expected the full curriculum, got {len(entries)}"
    failing = [f"{e.milestone}·{e.observable} (z={e.z:+.2f})" for e in entries if not e.passed]
    assert not failing, f"scoreboard shows out-of-tolerance milestones: {failing}"
