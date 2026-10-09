"""One kit receipt as a page: the system, the star, the candidate.

``python -m lab.planetkit_dashboard receipt.json`` writes a single static HTML
file next to the receipt. It needs nothing but the receipt: no network, no
CDN, no script (the page carries none, so it passes a ``script-src 'self'``
policy and opens from a USB stick). Everything it shows is read from the
receipt, from light curves whose SHA-256 matches the receipt, or from an
optional star file you fill in yourself; anything it works out is labelled
as worked out, with the inputs named.

What it will not do is show more than the verdict says:

* The receipt is checked with :func:`lab.planetkit.check_receipt` first, and
  the finished page is checked against the same claim pattern.
* The thing blocking the light is drawn only for ``lead-awaiting-human-review``
  and ``already-known``, and only as a dashed outline labelled "not measured".
  A refuted star shows the reason it was refuted instead; a star with nothing
  above threshold shows no orbit at all.
* A light curve passed with ``--fits`` or ``--csv`` must hash to the receipt's
  ``sha256`` for its sector, or the page is refused.

The worked example is TIC 374861595, the lab's open lead; its dashboard was
built from the dossier by hand and this module is that page, generalised.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

from . import a04, a05
from .a05_vocab import LEAD_DISPOSITION
from .planetkit import (PLAIN, STAR_STATUSES, KitError,
                        _CLAIM, check_receipt, curve_from_csv, identify_fits)

#: Star statuses for which a companion outline is drawn. Anything else gets
#: no object in the system panel, because the verdict says there is none to
#: draw (refuted, nothing found) or the run says nothing (control failed,
#: incomplete).
DRAW_COMPANION = (LEAD_DISPOSITION, "already-known")

#: Optional star-file keys, all copied verbatim into the star panel. Fill in
#: from the TIC or Gaia with the source named; the page prints the source.
STAR_KEYS = ("name", "r_star_sun", "m_star_sun", "teff_k", "tmag",
             "distance_pc", "ra_deg", "dec_deg", "source")

R_SUN_AU = 0.00465047
DAYS_PER_YEAR = 365.25

esc = html.escape


# --------------------------------------------------------------- inputs

def verify_curve(receipt: dict, sector: int, blob: bytes | None = None,
                 text: str | None = None) -> dict:
    """A light curve for one sector, refused unless it is the receipt's."""
    obs = {o["sector"]: o for o in receipt["observations"]}.get(sector)
    if obs is None:
        raise KitError(f"the receipt has no sector {sector}")
    if blob is not None:
        curve = a05.curve_from_blob(blob)
    else:
        curve = curve_from_csv(text or "")
    want = obs.get("sha256")
    if not want or curve.get("sha256") != want:
        raise KitError(f"sector {sector}: this light curve is not the one the "
                       "receipt searched (SHA-256 differs)")
    return curve


def fold_points(t, f, period: float, phase: float, half_hours: float,
                nbins: int = 72) -> list[tuple[float, float]]:
    """Median-binned fold, hours from the dip's centre, inside +/-half_hours.
    Same phase convention as the search: ``phase`` is the box centre as a
    fraction of ``t mod P``."""
    t, f = np.asarray(t, float), np.asarray(f, float)
    x = (np.mod(t / period - phase + 0.5, 1.0) - 0.5) * period * 24.0
    keep = np.abs(x) <= half_hours
    x, f = x[keep], f[keep]
    edges = np.linspace(-half_hours, half_hours, nbins + 1)
    idx = np.clip(np.digitize(x, edges) - 1, 0, nbins - 1)
    out = []
    for k in range(nbins):
        sel = idx == k
        if sel.sum() >= 3:
            out.append((float(0.5 * (edges[k] + edges[k + 1])),
                        float(np.median(f[sel]))))
    return out


def dossier_points(row: dict, half_hours: float) -> list[tuple[float, float]]:
    """The survey's dossier carries a 120-bin fold; recentre and crop it."""
    fp = (row.get("dossier") or {}).get("fold_p")
    if not fp:
        return []
    p = fp["period_days"]
    pts = [((((ph - row["phase"] + 0.5) % 1.0) - 0.5) * p * 24.0, fl)
           for ph, fl in zip(fp["phase"], fp["flux"])]
    return sorted((h, fl) for h, fl in pts if abs(h) <= half_hours)


def half_window(period: float) -> float:
    """Hours either side of the dip: a quarter orbit, between 3 and 8 h."""
    return float(min(8.0, max(3.0, 0.25 * period * 24.0)))


# --------------------------------------------------------------- drawing

def _fmt(v, nd=3):
    return "—" if v is None else f"{v:.{nd}f}"


def svg_fold(points, *, sector: int, depth: float | None,
             half: float) -> str:
    W, H, L, R, T, B = 520, 240, 56, 14, 14, 36
    ys = [p[1] for p in points]
    lo = min(ys + [1 - (depth or 0)]) - 0.004
    hi = max(ys + [1.0]) + 0.004
    X = lambda v: L + (v + half) / (2 * half) * (W - L - R)  # noqa: E731
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)  # noqa: E731
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Sector '
             f'{sector}: brightness folded on the search period">']
    for v in np.linspace(lo + 0.004, hi - 0.004, 4):
        parts.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{Y(v):.1f}"'
                     f' y2="{Y(v):.1f}"/><text x="{L - 6}" y="{Y(v) + 4:.1f}" '
                     f'text-anchor="end">{v:.3f}</text>')
    step = 2 if half <= 4 else 4
    for h in range(-int(half) // step * step, int(half) + 1, step):
        parts.append(f'<text x="{X(h):.1f}" y="{H - B + 16}" '
                     f'text-anchor="middle">{h:+d}</text>')
    parts.append(f'<line class="axis" x1="{L}" x2="{W - R}" y1="{H - B}" '
                 f'y2="{H - B}"/><text class="dim" x="{(L + W - R) / 2}" '
                 f'y="{H - 4}" text-anchor="middle">hours from the middle of '
                 'the dip</text>')
    if depth:
        parts.append(f'<line class="ref" x1="{L}" x2="{W - R}" '
                     f'y1="{Y(1 - depth):.1f}" y2="{Y(1 - depth):.1f}"/>'
                     f'<text class="dim" x="{W - R - 4}" '
                     f'y="{Y(1 - depth) - 5:.1f}" text-anchor="end">search box '
                     f'depth {depth * 100:.2f} %</text>')
    pts = " ".join(f"{X(h):.1f},{Y(v):.1f}" for h, v in points)
    parts.append(f'<polyline class="curve" points="{pts}"/>')
    for h, v in points:
        parts.append(f'<circle class="bin" cx="{X(h):.1f}" cy="{Y(v):.1f}" '
                     f'r="2.6"><title>{h:+.2f} h: {(1 - v) * 100:.2f} % dimmer'
                     '</title></circle>')
    parts.append("</svg>")
    return "".join(parts)


def svg_system(status: str, r_star: float | None, a_rstar: float | None,
               k: float | None, reason: str) -> str:
    """Top-down, to scale in star radii when the orbit is known."""
    span = (a_rstar or 4.0) * 1.18
    K = 200 / span
    p = [f'<svg viewBox="-230 -230 460 460" role="img" aria-label="The star '
         'from above, with the orbit when it can be drawn">',
         '<defs><radialGradient id="limb"><stop offset="0" '
         'stop-color="var(--star-core)"/><stop offset=".65" '
         'stop-color="var(--star-mid)"/><stop offset="1" '
         'stop-color="var(--star-limb)"/></radialGradient></defs>']
    if a_rstar:
        p.append(f'<circle class="orbit" r="{a_rstar * K:.1f}"/>'
                 f'<text class="ink" x="0" y="{-a_rstar * K - 7:.1f}" '
                 f'text-anchor="middle">orbit {a_rstar:.2f} R★ (worked out)'
                 '</text>')
    p.append(f'<circle r="{K:.1f}" fill="url(#limb)"/>'
             f'<text class="ink" x="0" y="{-K - 6:.1f}" '
             'text-anchor="middle">the star</text>')
    if status in DRAW_COMPANION and k:
        cy = (a_rstar or 2.4) * K
        p.append(f'<circle class="unknown" cx="0" cy="{cy:.1f}" '
                 f'r="{max(k * K, 4):.1f}"/><text class="ink" x="0" '
                 f'y="{cy + 4:.1f}" text-anchor="middle">?</text>'
                 f'<text class="dim" x="{-max(k * K, 4) - 8:.1f}" '
                 f'y="{cy - 6:.1f}" text-anchor="end">not measured;</text>'
                 f'<text class="dim" x="{-max(k * K, 4) - 8:.1f}" '
                 f'y="{cy + 8:.1f}" text-anchor="end">outlined at √depth'
                 '</text>')
    else:
        p.append(f'<text class="dim" x="0" y="{K + 30:.1f}" '
                 f'text-anchor="middle">{esc(reason)}</text>')
    p.append('<text class="dim" x="0" y="222" text-anchor="middle">'
             '↓ to Earth</text></svg>')
    return "".join(p)


# --------------------------------------------------------------- page

CSS = """
:root{color-scheme:dark;--bg:#1c1510;--panel:#241b13;--well:#18120d;
--line:#3a2f26;--ink:#ece1cc;--ink-2:#b8a98c;--ink-3:#a0926f;--brass:#c9a86a;
--ember:#e8833a;--moss:#8aa86b;--clay:#d08560;--star-core:#ffd2a1;
--star-mid:#f08a45;--star-limb:#9c3415;
--serif:'Fraunces',Georgia,'Times New Roman',serif;
--mono:'JetBrains Mono',ui-monospace,Consolas,monospace;
--sans:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
@media (prefers-color-scheme:light){:root{color-scheme:light;--bg:#f6efe2;
--panel:#fbf7ef;--well:#efe6d4;--line:#dccdb2;--ink:#2a1f14;--ink-2:#5c4a33;
--ink-3:#6f5b3e;--brass:#85652a;--ember:#b8561a;--moss:#4c6a30;--clay:#a24a22;
--star-core:#ffd9ae;--star-mid:#ef8240;--star-limb:#a83a16}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 var(--sans)}
.wrap{max-width:1080px;margin:0 auto;padding-inline:clamp(16px,4vw,32px);
padding-block:28px 56px}
a{color:var(--ember)}
h1,h2,h3{font-family:var(--serif);font-weight:600;margin:0;text-wrap:balance}
h1{font-size:clamp(28px,5vw,42px)}h2{font-size:26px}h3{font-size:18px}
.eyebrow{font:11.5px var(--mono);letter-spacing:.08em;text-transform:uppercase;
color:var(--brass)}
.lede{color:var(--ink-2);max-width:64ch}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.chip{font:12px var(--mono);padding:4px 10px;border:1px solid var(--line);
border-radius:999px;background:var(--panel);color:var(--ink-2)}
.chip.on{border-color:var(--brass);color:var(--ink)}
.word{font:13px var(--mono);background:var(--well);border:1px solid var(--line);
padding:1px 7px;border-radius:4px}
.warn{border:1px solid var(--clay);color:var(--ink);border-radius:8px;
padding:10px 14px;margin-top:14px;background:var(--panel)}
section{margin-top:38px}
.ph{border-bottom:1px solid var(--line);padding-bottom:8px;display:flex;
gap:14px;align-items:baseline;flex-wrap:wrap}
.ph p{margin:0;color:var(--ink-2)}
.grid2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px;
margin-top:16px}
@media (max-width:820px){.grid2{grid-template-columns:minmax(0,1fr)}}
figure{margin:0;background:var(--panel);border:1px solid var(--line);
border-radius:10px;padding:14px;min-width:0}
figure img,figure svg{display:block;width:100%;height:auto}
figcaption{font-size:13px;color:var(--ink-2);margin-top:8px}
.ft{font:12px var(--mono);color:var(--ink-3);margin-bottom:6px}
dl.facts{display:grid;grid-template-columns:max-content minmax(0,1fr);margin:0;align-self:start}
.facts dt,.facts dd{margin:0;padding:7px 0;border-bottom:1px dashed var(--line)}
.facts dt{color:var(--ink-2);padding-right:14px;font-size:13.5px}
.facts dd{font-variant-numeric:tabular-nums;min-width:0;overflow-wrap:anywhere}
.src{display:block;font:11px var(--mono);color:var(--ink-3)}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px;
font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);
white-space:nowrap}
th{font:11px var(--mono);color:var(--ink-3);text-transform:uppercase}
.folds{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));
gap:18px;margin-top:16px}
.verdict{margin-top:24px;border:1px solid var(--brass);border-radius:12px;
background:var(--panel);padding:20px;display:grid;
grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:22px}
@media (max-width:760px){.verdict{grid-template-columns:minmax(0,1fr)}}
.say{font:19px/1.45 var(--serif);margin:8px 0}
footer{margin-top:44px;border-top:1px solid var(--line);padding-top:16px;
color:var(--ink-2);font-size:13px}
svg text{font:11px var(--mono);fill:var(--ink-2)}
svg .ink{fill:var(--ink)}svg .dim{fill:var(--ink-3)}
svg .grid{stroke:var(--line);stroke-dasharray:2 4}
svg .axis{stroke:var(--line)}
svg .ref{stroke:var(--ink-3);stroke-dasharray:5 4}
svg .curve{fill:none;stroke:var(--ember);stroke-width:2;stroke-linejoin:round}
svg .bin{fill:var(--ember);stroke:var(--panel);stroke-width:1}
svg .orbit{fill:none;stroke:var(--ember);stroke-width:2}
svg .unknown{fill:var(--bg);stroke:var(--ink-2);stroke-width:1.2;
stroke-dasharray:3 3}
"""


def _crossed(receipt: dict) -> list[dict]:
    return [o for o in receipt["observations"]
            if o["row"]["sde"] >= a04.SDE_THRESHOLD]


def _system_numbers(receipt: dict, star: dict) -> dict:
    """Period, R★, a/R★ and the outline's radius ratio, each with its
    source. Only medians of crossing sectors; nothing for a quiet star."""
    rows = [o["row"] for o in _crossed(receipt)]
    phys = [((o["row"].get("disposition_evidence") or {}).get("physical")
             or {}) for o in receipt["observations"]]
    r_star = star.get("r_star_sun") or next(
        (p["r_star_sun"] for p in phys if p.get("r_star_sun")), None)
    r_src = ("star file" if star.get("r_star_sun") else
             "light-curve header (TIC)" if r_star else None)
    out = {"period": None, "depth": None, "k": None, "a_rstar": None,
           "a_au": None, "r_star": r_star, "r_src": r_src}
    if not rows:
        return out
    out["period"] = float(np.median([r["period_days"] for r in rows]))
    out["depth"] = float(np.median([r["depth"] for r in rows]))
    out["k"] = math.sqrt(max(out["depth"], 0.0))
    m = star.get("m_star_sun")
    if m and r_star:
        a_au = (m * (out["period"] / DAYS_PER_YEAR) ** 2) ** (1 / 3)
        out["a_au"] = a_au
        out["a_rstar"] = a_au / R_SUN_AU / r_star
    return out


def render(receipt: dict, *, curves: dict | None = None,
           star: dict | None = None, fold_images: dict | None = None) -> str:
    """Receipt (+ verified curves, star file, fold SVG files) -> HTML."""
    check_receipt(receipt)
    curves, star, fold_images = curves or {}, star or {}, fold_images or {}
    unknown = set(star) - set(STAR_KEYS)
    if unknown:
        raise KitError(f"star file: unknown keys {sorted(unknown)}; "
                       f"allowed: {', '.join(STAR_KEYS)}")
    tic = esc(str(receipt["tic"]))
    v = receipt["verdict"]
    status = receipt["star"]["status"]
    nums = _system_numbers(receipt, star)
    by = receipt["star"].get("by") or {}
    reason = {
        "nothing-above-threshold": "no repeating dip crossed the threshold, "
                                   "so there is no orbit to draw",
        "refuted": "refuted: " + "; ".join(
            PLAIN.get(w, w) for w in by.values()),
        "control-failed": "the placebo failed, so this run draws nothing",
        "incomplete": "a gate did not run, so this run draws nothing",
    }.get(status, "")
    if status in DRAW_COMPANION and not nums["a_rstar"]:
        reason = "orbit size needs the star's mass (add m_star_sun)"

    h = []
    w = h.append
    w(f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
      f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
      f"<title>TIC {tic} · planet kit dashboard</title><style>{CSS}</style>"
      "</head><body><div class=\"wrap\">")
    w(f'<header><div class="eyebrow">find-your-own-planet · the system, the '
      f'star, the candidate</div><h1>TIC {tic}</h1>'
      f'<p class="lede">One run of the kit on one star, drawn from its '
      f'receipt ({esc(receipt["created_utc"])}). Numbers marked "worked out" '
      'are computed on this page from the inputs named beside them.</p>'
      f'<div class="chips"><span class="chip on">{esc(status)}</span>'
      f'<span class="chip">{len(receipt["observations"])} sector'
      f'{"s" * (len(receipt["observations"]) != 1)} searched</span></div>')
    for warning in v.get("warnings", []):
        w(f'<div class="warn">{esc(warning)}</div>')
    w("</header>")

    # ---- system
    w('<section id="system"><div class="ph"><h2>The system</h2><p>A star '
      'and, when the search found a repeating dip, the orbit its period '
      'implies.</p></div><div class="grid2"><figure><div class="ft">FROM '
      'ABOVE · to scale in star radii</div>')
    w(svg_system(status, nums["r_star"], nums["a_rstar"], nums["k"], reason))
    w('<figcaption>The outline, when there is one, is the square root of the '
      'search box\'s depth: what a dark disc crossing the middle of the star '
      'would need. A grazing or blended dip breaks that, so it is a scale, '
      'not a size.</figcaption></figure><dl class="facts">')
    if nums["period"]:
        w(f'<dt>Period</dt><dd>{nums["period"]:.5f} d<span class="src">median '
          'of the sectors that crossed the threshold</span></dd>'
          f'<dt>Depth</dt><dd>{nums["depth"] * 100:.2f} %<span class="src">'
          'search box depth, median</span></dd>')
    if nums["a_rstar"]:
        w(f'<dt>Orbit radius</dt><dd>{nums["a_rstar"]:.2f} R★ = '
          f'{nums["a_au"]:.4f} AU<span class="src">worked out: Kepler III '
          'with the period and m_star_sun from the star file</span></dd>')
    if reason:
        w(f'<dt>Drawn</dt><dd>{esc(reason)}</dd>')
    w("</dl></div></section>")

    # ---- star
    w('<section id="star"><div class="ph"><h2>The star</h2><p>What the '
      'receipt and the light-curve files say about the host.</p></div>'
      '<div class="grid2"><dl class="facts">')
    w(f'<dt>TIC</dt><dd>{tic}</dd>')
    if star.get("name"):
        w(f'<dt>Name</dt><dd>{esc(str(star["name"]))}</dd>')
    if nums["r_star"]:
        w(f'<dt>Radius</dt><dd>{nums["r_star"]:.3f} R☉<span class="src">'
          f'{esc(nums["r_src"])}</span></dd>')
    for key, label, unit in (("m_star_sun", "Mass", " M☉"),
                             ("teff_k", "Temperature", " K"),
                             ("tmag", "TESS magnitude", ""),
                             ("distance_pc", "Distance", " pc"),
                             ("ra_deg", "RA", "°"), ("dec_deg", "Dec", "°")):
        if star.get(key) is not None:
            w(f'<dt>{label}</dt><dd>{esc(str(star[key]))}{unit}'
              '<span class="src">star file</span></dd>')
    if star.get("source"):
        w(f'<dt>Star file source</dt><dd>{esc(str(star["source"]))}</dd>')
    w('</dl><div class="scroll"><table><thead><tr><th>Sector</th>'
      '<th>CROWDSAP</th><th>Centroid offset</th><th>Light curve</th></tr>'
      '</thead><tbody>')
    for o in receipt["observations"]:
        ev = o["row"].get("disposition_evidence") or {}
        crowd = (ev.get("physical") or {}).get("crowdsap")
        cen = ((ev.get("blend") or {}).get("centroid") or {}).get(
            "implied_offset_px")
        sha = o.get("sha256") or ""
        w(f'<tr><td>{o["sector"]}</td><td>{_fmt(crowd)}</td>'
          f'<td>{_fmt(cen)}{" px" if cen is not None else ""}</td>'
          f'<td title="{esc(sha)}">{esc(sha[:12])}…</td></tr>')
    w('</tbody></table><p class="src" style="margin-top:8px">CROWDSAP: the '
      "target's share of the light in SPOC's aperture. Centroid offset: how "
      'far the light that dims sits from the target, in pixels. "—" means '
      'the gate did not run on this input.</p></div></div></section>')

    # ---- candidate
    w('<section id="candidate"><div class="ph"><h2>The candidate</h2><p>'
      'Every dip in a sector stacked on the others. A picture, not a verdict.'
      '</p></div><div class="folds">')
    for o in receipt["observations"]:
        r, s = o["row"], o["sector"]
        half = half_window(r["period_days"])
        word = r.get("disposition") or "below threshold"
        head = (f'<div class="ft">SECTOR {s} · SDE {r["sde"]:.1f} · '
                f'P {r["period_days"]:.4f} d · {esc(word)}</div>')
        if s in curves:
            pts = fold_points(curves[s]["t"], curves[s]["f"],
                              r["period_days"], r["phase"], half)
            src = "light curve verified against the receipt's SHA-256"
        else:
            pts, src = dossier_points(r, half), "the receipt's own fold"
        if pts:
            w(f'<figure>{head}{svg_fold(pts, sector=s, depth=r.get("depth"), half=half)}'
              f'<figcaption>Binned medians; {esc(src)}. Hover a dot for its '
              'value.</figcaption></figure>')
        elif s in fold_images:
            b64 = base64.b64encode(fold_images[s].encode()).decode()
            w(f'<figure>{head}<img alt="Sector {s} fold drawn by the kit" '
              f'src="data:image/svg+xml;base64,{b64}"><figcaption>The fold '
              'plot the kit wrote beside the receipt.</figcaption></figure>')
        else:
            w(f'<figure>{head}<p class="src">No fold for this sector: pass '
              'its light curve with --fits or --csv to draw one.</p></figure>')
    w('</div><div class="scroll" style="margin-top:16px"><table><thead><tr>'
      '<th>Sector</th><th>SDE</th><th>Period (d)</th><th>Depth</th>'
      '<th>Word</th><th>Placebo</th></tr></thead><tbody>')
    for o in receipt["observations"]:
        r = o["row"]
        pl = o.get("placebo") or {}
        w(f'<tr><td>{o["sector"]}</td><td>{r["sde"]:.2f}</td>'
          f'<td>{r["period_days"]:.5f}</td><td>{r["depth"] * 100:.2f} %</td>'
          f'<td><span class="word">{esc(r.get("disposition") or "below threshold")}'
          f'</span></td><td>{"passed" if pl.get("pass") else "FAILED"}</td></tr>')
    w('</tbody></table></div>')
    w(f'<div class="verdict"><div><div class="eyebrow">the verdict</div>'
      f'<h3>The kit\'s word for this star</h3><p><span class="word">'
      f'{esc(status)}</span></p><p class="src">One of six: '
      f'{esc(", ".join(STAR_STATUSES))}.</p></div>'
      f'<div><div class="eyebrow">in plain words</div><p class="say">'
      f'{esc(v["may_say"])}</p></div></div></section>')

    pre = receipt.get("prereg") or {}
    git = pre.get("git") or {}
    w(f'<footer><p>Preregistration <code>{esc(str(pre.get("path", "")))}</code>, '
      f'SHA-256 <code>{esc(str(pre.get("sha256", ""))[:12])}</code>, '
      f'{"committed" if git.get("committed") else "not committed"}. Kit '
      f'{esc(str(receipt.get("kit")))} v{esc(str(receipt.get("kit_version")))}'
      f'{" · quick mode" if receipt.get("quick") else ""}. Rules: '
      '<a href="https://github.com/benskamps/windowsill-lab/blob/main/kit/'
      'BEFORE-YOU-POST.md">before you post</a>.</p></footer>')
    w("</div></body></html>\n")
    page = "".join(h)
    # The page says the verdict once and holds every word of it, and the
    # receipt's boundary it no longer prints, to the receipt's own rule.
    if (_CLAIM.search(html.unescape(re_strip_tags(page)))
            or _CLAIM.search(str(receipt.get("claim_boundary") or ""))):
        raise KitError("the dashboard text makes a planet claim")
    return page


def re_strip_tags(page: str) -> str:
    page = re.sub(r"<(style|title)[^>]*>.*?</\1>", " ", page, flags=re.S)
    return re.sub(r"<[^>]+>", " ", page)


# --------------------------------------------------------------- cli

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="planetkit-dashboard",
                                description=__doc__.split("\n\n")[0])
    p.add_argument("receipt", type=Path)
    p.add_argument("--fits", type=Path, nargs="*", default=[],
                   help="SPOC light curves; each must match the receipt")
    p.add_argument("--csv", type=Path, nargs="*", default=[],
                   help="time,flux tables named ...-s<sector>.csv")
    p.add_argument("--star", type=Path,
                   help=f"optional JSON with any of: {', '.join(STAR_KEYS)}")
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    try:
        receipt = json.loads(a.receipt.read_text())
        curves = {}
        for path in a.fits:
            _, sector = identify_fits(path.name)
            if sector is None:
                raise KitError(f"{path.name}: not a SPOC light-curve name")
            curves[sector] = verify_curve(receipt, sector,
                                          blob=path.read_bytes())
        for path in a.csv:
            stem = path.stem.rsplit("-s", 1)
            if len(stem) != 2 or not stem[1].isdigit():
                raise KitError(f"{path.name}: name it ...-s<sector>.csv")
            curves[int(stem[1])] = verify_curve(receipt, int(stem[1]),
                                                text=path.read_text())
        star = json.loads(a.star.read_text()) if a.star else {}
        images = {}
        for o in receipt["observations"]:
            fig = a.receipt.with_name(f"{a.receipt.stem}-s{o['sector']}-fold.svg")
            if fig.exists():
                images[o["sector"]] = fig.read_text()
        page = render(receipt, curves=curves, star=star, fold_images=images)
        out = a.out or a.receipt.with_suffix(".html")
        out.write_text(page)
        print(f"dashboard: {out}")
    except KitError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
