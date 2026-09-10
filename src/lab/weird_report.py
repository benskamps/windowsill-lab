"""The eye's face: one page, ranked, with the distribution beside every claim.

A finding is a sentence about a shape. Reading the sentence without the shape is
how "79.4% sit on the minimum" stays abstract until you see the spike. Every row
here carries an inline histogram drawn from the same column the claim is about,
so the evidence and the assertion cannot drift apart — there is only one source.

Deterministic: no clock, no randomness, no counters that move between runs. The
same corpus renders byte-identical, so a diff means the DATA changed.
"""
from __future__ import annotations

import html
import math
from collections.abc import Sequence
from pathlib import Path

from . import weird as W

_CSS = """
:root{--bark:#1c1510;--panel:#241b13;--line:#4a3b28;--parchment:#ece1cc;
--dim:#b8a98c;--faint:#847660;--ember:#e8833a;--gold:#d9a441;--moss:#8aa86b;
--clay:#c4744a;--slate:#8fa3ad;--mono:'JetBrains Mono',ui-monospace,monospace;
--serif:'Fraunces',Georgia,serif}
*{box-sizing:border-box}
body{margin:0;background:var(--bark);color:var(--parchment);font-family:var(--serif);
font-size:16px;line-height:1.6}
body::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:1;opacity:.35;
background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3CfeColorMatrix values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.05 0'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)'/%3E%3C/svg%3E")}
.lamp{position:fixed;inset:0;pointer-events:none;z-index:0;background:
radial-gradient(ellipse 70% 38% at 50% -6%,rgba(232,166,74,.16),transparent 70%),
radial-gradient(ellipse 45% 30% at 12% 110%,rgba(138,168,107,.05),transparent 70%)}
.wrap{position:relative;z-index:2;max-width:1080px;margin:0 auto;padding:52px 26px 90px}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.42em;
text-transform:uppercase;color:var(--gold)}
h1{font-style:italic;font-weight:380;font-size:clamp(34px,6vw,60px);line-height:1;
margin:14px 0 0;letter-spacing:-.015em}
.dek{color:var(--dim);font-style:italic;margin:16px 0 0;max-width:62ch}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:1px;
background:var(--line);border:1px solid var(--line);margin:34px 0 10px}
.stat{background:var(--panel);padding:14px}
.stat b{display:block;font-family:var(--mono);font-size:26px;color:var(--ember);
font-weight:700;line-height:1.1}
.stat span{display:block;font-family:var(--mono);font-size:9px;letter-spacing:.16em;
text-transform:uppercase;color:var(--faint);margin-top:5px}
h2{font-style:italic;font-weight:440;font-size:24px;margin:44px 0 6px}
.sub{font-family:var(--mono);font-size:10px;letter-spacing:.18em;text-transform:uppercase;
color:var(--faint);margin-bottom:16px}
.f{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--slate);
padding:13px 16px;margin-bottom:9px;display:grid;grid-template-columns:1fr 190px;gap:16px;
align-items:center}
.f.free{border-left-color:var(--moss)}.f.cheap{border-left-color:var(--gold)}
.f.expensive{border-left-color:var(--clay)}
.f .subj{font-family:var(--mono);font-size:12px;color:var(--gold);word-break:break-all}
.f .detail{font-size:15px;color:var(--parchment);margin-top:5px}
.f .why{font-size:13.5px;color:var(--dim);margin-top:8px;font-style:italic}
.f .kill{font-size:13px;color:var(--moss);margin-top:6px}
.f .kill b{font-family:var(--mono);font-size:9px;letter-spacing:.14em;
text-transform:uppercase;color:var(--faint);font-weight:400;display:block}
.chip{font-family:var(--mono);font-size:9px;letter-spacing:.1em;text-transform:uppercase;
border:1px solid var(--line);padding:2px 6px;border-radius:3px;color:var(--faint);
margin-right:6px;white-space:nowrap}
.spark{display:flex;align-items:flex-end;gap:1px;height:52px}
.spark i{flex:1;background:var(--slate);min-height:1px;display:block}
.spark i.hot{background:var(--ember)}
.cap{font-family:var(--mono);font-size:8.5px;letter-spacing:.1em;color:var(--faint);
margin-top:5px;text-align:right}
.blind{border-left-color:var(--clay);background:rgba(196,116,74,.06)}
.note{font-family:var(--mono);font-size:11px;color:var(--faint);margin:6px 0}
footer{margin-top:56px;border-top:1px solid var(--line);padding-top:18px;
font-family:var(--mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;
color:var(--faint);line-height:1.9}
"""


def _spark(values: Sequence[float], bins: int = 34) -> tuple[str, str]:
    """Inline histogram + a caption naming where the mass actually is."""
    vals = [v for v in values if math.isfinite(v)]
    if len(vals) < 8:
        return "", ""
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return ('<div class="spark"><i class="hot" style="height:100%"></i></div>',
                f"constant at {lo:g}")
    w = (hi - lo) / bins
    hist = [0] * bins
    for v in vals:
        hist[min(bins - 1, int((v - lo) / w))] += 1
    peak = max(hist) or 1
    top = max(range(bins), key=lambda i: hist[i])
    bars = "".join(
        f'<i class="{"hot" if i == top else ""}" style="height:{max(1, round(100*h/peak))}%"></i>'
        for i, h in enumerate(hist))
    share = hist[top] / len(vals)
    where = "min" if top == 0 else ("max" if top == bins - 1 else "interior")
    return (f'<div class="spark">{bars}</div>',
            f"{share:.0%} in the modal bin ({where}) · n={len(vals)}")


def render(reports: dict[str, W.Report], rows: Sequence[dict],
           hypotheses: Sequence[W.Hypothesis], notes: Sequence[str],
           corpus_name: str, out: Path) -> Path:
    kept, _ = W.explain_away(reports)
    short = W.rank_by_surprise(kept)
    trusted = [n for n, r in reports.items() if r.saw_control]
    blind = [n for n, r in reports.items() if not r.saw_control]
    raw = sum(len(r.findings) for r in reports.values())

    def esc(s):
        return html.escape(str(s))

    parts = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>weird — {esc(corpus_name)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300..900;1,9..144,300..900&family=JetBrains+Mono:wght@300..700&display=swap" rel="stylesheet">
<style>{_CSS}</style></head><body><div class="lamp"></div><div class="wrap">
<div class="eyebrow">weird · anomaly sweep</div>
<h1>What nobody looked at</h1>
<p class="dek">{esc(corpus_name)}. No domain knowledge: every relation below was
learned from the corpus itself, and every finding is of the form
<em>&ldquo;this holds N times and not here&rdquo;</em> &mdash; a question with its own
falsifier attached.</p>
<div class="stats">
<div class="stat"><b>{len(rows):,}</b><span>rows</span></div>
<div class="stat"><b>{len(W._fields(rows))}</b><span>numeric fields</span></div>
<div class="stat"><b>{raw:,}</b><span>raw findings</span></div>
<div class="stat"><b>{len(short)}</b><span>distinct mechanisms</span></div>
<div class="stat"><b>{len(trusted)}/{len(reports)}</b><span>families that see</span></div>
</div>"""]

    for n in notes:
        parts.append(f'<div class="note">— {esc(n)}</div>')

    if blind:
        parts.append('<h2>Families that could not prove they see</h2>'
                     '<div class="sub">their silence proves nothing · findings withheld</div>')
        for name in blind:
            r = reports[name]
            parts.append(
                f'<div class="f blind"><div><div class="subj">{esc(name)}</div>'
                f'<div class="detail">withheld {len(r.findings)} finding(s) — failed '
                f'its control: {esc(r.control)}</div></div><div></div></div>')

    parts.append('<h2>Hypotheses</h2><div class="sub">rarest mechanism first · '
                 'cheapest test first · each with the observation that kills it</div>')
    for h in hypotheses[:24]:
        col = h.source.subject if h.source else ""
        spark, cap = _spark([r[col] for r in rows if col in r]) if col else ("", "")
        parts.append(f"""<div class="f {esc(h.cost)}"><div>
<span class="chip">{esc(h.source.family if h.source else '')}</span>
<span class="chip">{esc(h.cost)} to test</span>
<div class="detail">{esc(h.claim)}</div>
<div class="why">because {esc(h.because)}</div>
<div class="kill"><b>killed by</b>{esc(h.falsifier)}</div>
</div><div>{spark}<div class="cap">{esc(cap)}</div></div></div>""")

    parts.append('<h2>Mechanisms, rarest first</h2><div class="sub">'
                 'a thousand rows breaking one relation is one fact</div>')
    for f in short[:30]:
        n = f.evidence.get("cluster_size", 1)
        col = f.subject
        spark, cap = _spark([r[col] for r in rows if col in r])
        z = f"{f.z:.1f} MAD" if f.z and math.isfinite(f.z) else "—"
        parts.append(f"""<div class="f"><div>
<span class="chip">{esc(f.family)}</span><span class="chip">×{n}</span>
<span class="chip">{esc(z)}</span>
<div class="subj">{esc(f.subject)}</div>
<div class="detail">{esc(f.detail)}</div>
</div><div>{spark}<div class="cap">{esc(cap)}</div></div></div>""")

    parts.append(f"""<footer>
<div>weird · {esc(corpus_name)}</div>
<div>no clock, no randomness — the same corpus renders byte-identical</div>
<div>a family that cannot rediscover its control withholds everything it found</div>
</footer></div></body></html>""")

    out.write_text("\n".join(parts), encoding="utf-8")
    return out
