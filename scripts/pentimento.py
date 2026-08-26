#!/usr/bin/env python3
"""Pentimento — what a paper lost between v1 and its final arXiv version.

In painting, pentimento is the ghost of what the artist painted over, visible
under X-ray. arXiv keeps every version of every paper publicly and forever, and
between v1 and the published version claims soften, error bars widen and results
disappear — usually during peer review, usually silently. Nobody diffs them.

Why this survives the rules the lab learned the hard way on 2026-08-24/25:

* **No domain fluency required.** It is a text diff. The failure that cost four
  GPU-hours was not being able to tell two susceptibilities apart; nothing here
  asks us to.
* **Only positive claims.** "This sentence is in v1 and absent from v3" is
  checkable by anyone with the two PDFs. No negative claim about literature —
  the operation this lab is demonstrably worst at.
* **The corpus is real.** Measured 2026-08-26: 49.5% of 1,200 sampled papers
  (2022-23) carry a v2 or later; 62-66% in cond-mat.stat-mech, up to v8.

The observable is deliberately crude and mechanical: **words gained versus
decimal values lost.** A paper that grows while shedding numbers has had
something taken out of it.

## The honest caveat, stated up front

`pdftotext` on LaTeX-heavy physics is noisy. Equation rendering differs between
compilations, so some "removed" values are extraction artifacts rather than
removed results. That biases the raw removal count upward by an unknown amount.
The defence is comparative, not absolute: a *matched* rate is what matters, and
the same noise applies to additions — so a systematic gap between removals and
additions is harder to explain as rendering.
"""
from __future__ import annotations
import difflib, json, os, re, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

UA={"User-Agent":"windowsill-lab/0.1 (mailto:benjamin.schippers@outlook.com)"}
OUT=Path(__file__).resolve().parents[1]/"corpus"/"pentimento.jsonl"
#: Decimal values only. Bare integers are too often equation indices, years and
#: reference numbers to survive PDF extraction as meaningful measurements.
NUM=re.compile(r"[-+]?\d+\.\d+(?:\([0-9]+\))?")
DELAY=4.0

def pdftext(aid):
    for host in ("https://arxiv.org/pdf/","https://export.arxiv.org/pdf/"):
        try:
            with urllib.request.urlopen(urllib.request.Request(host+aid,headers=UA),timeout=70) as r:
                b=r.read()
            if not b.startswith(b"%PDF"): continue
            with tempfile.NamedTemporaryFile(suffix=".pdf",delete=False) as f: f.write(b); p=f.name
            t=subprocess.run(["pdftotext","-q",p,"-"],capture_output=True,timeout=120).stdout.decode("utf8","ignore")
            os.unlink(p); return t
        except Exception: continue
    return None

def candidates(cat, lo, hi, n=200):
    u=(f"https://export.arxiv.org/api/query?search_query=cat:{cat}"
       f"+AND+submittedDate:[{lo}+TO+{hi}]&start=0&max_results={n}"
       f"&sortBy=submittedDate&sortOrder=descending")
    with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=60) as r:
        x=r.read().decode("utf8","ignore")
    out=[]
    for i in re.findall(r"<id>http://arxiv\.org/abs/([^<]+)</id>", x):
        v=i.rsplit("v",1)[-1]
        if v.isdigit() and int(v)>=2: out.append(i)
    return out

def compare(full):
    base,last=full.rsplit("v",1)
    a=pdftext(base+"v1"); time.sleep(DELAY)
    b=pdftext(full);      time.sleep(DELAY)
    if not (a and b) or len(a)<2000 or len(b)<2000: return None
    wa,wb=a.split(),b.split()
    na,nb=set(NUM.findall(a)),set(NUM.findall(b))
    sm=difflib.SequenceMatcher(None,wa,wb,autojunk=False)
    dels=[i2-i1 for t,i1,i2,j1,j2 in sm.get_opcodes() if t in ("delete","replace") and i2-i1>=12]
    biggest=""
    for t,i1,i2,j1,j2 in sm.get_opcodes():
        if t in ("delete","replace") and i2-i1==max(dels or [0]):
            biggest=" ".join(wa[i1:i2])[:300]; break
    return {"id":base,"final_version":int(last),
            "words_v1":len(wa),"words_vN":len(wb),"words_delta":len(wb)-len(wa),
            "nums_v1":len(na),"nums_vN":len(nb),
            "nums_removed":len(na-nb),"nums_added":len(nb-na),
            "deleted_passages":len(dels),"largest_deletion_words":max(dels or [0]),
            "largest_deletion":biggest}

if __name__=="__main__":
    cap=int(os.environ.get("CAP","40"))
    windows=[("cond-mat.stat-mech","202301010000","202306302359"),
             ("physics.comp-ph","202301010000","202306302359"),
             ("cs.LG","202301010000","202302282359")]
    done=set()
    if OUT.exists():
        for l in OUT.open(encoding="utf-8"):
            try: done.add(json.loads(l)["id"])
            except Exception: pass
    OUT.parent.mkdir(parents=True,exist_ok=True)
    n=0
    with OUT.open("a",encoding="utf-8") as fh:
        for cat,lo,hi in windows:
            try: cands=candidates(cat,lo,hi)
            except Exception as e:
                print(f"  {cat}: {e}",file=sys.stderr); continue
            print(f"{cat}: {len(cands)} multi-version candidates",flush=True)
            for full in cands:
                if n>=cap: break
                if full.rsplit("v",1)[0] in done: continue
                try: r=compare(full)
                except Exception: r=None
                if not r: continue
                r["category"]=cat
                fh.write(json.dumps(r)+"\n"); fh.flush(); n+=1
                print(f"  [{n}/{cap}] {r['id']} v{r['final_version']}  "
                      f"words {r['words_delta']:+6,}  nums {r['nums_v1']:>3}->{r['nums_vN']:<3} "
                      f"(-{r['nums_removed']} +{r['nums_added']})",flush=True)
            if n>=cap: break
    print(f"\nwrote {n} comparisons -> {OUT}",flush=True)
