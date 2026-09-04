# evidence/literature — the sentences a citation actually rests on

`../README.md` holds the bytes a *measurement* was derived from. This holds the
bytes a **citation** was derived from: for each paper this repo names in public,
the verbatim sentences that carry the claim, the locator inside the paper, the
URL that was reached, and a SHA-256 over the committed record so a reader can
tell whether it has drifted since it was written down.

It is data, not a page. Nothing here renders, nothing here is generated on a
schedule, and nothing here supersedes an existing surface.

## Who reads it

* **A human about to publish a claim that cites one of these papers.** Open the
  record, read the quote, check the locator. If the claim is not in a quote, it
  is not pinned, and the record says which parts were never reached.
* **`docs/assays/2026-09-03-u-k02-prior-art-pinned.md`**, which cites into this
  directory rather than restating it, and **`UNKNOWNS.md` U-K02**, whose
  narrowed wording is derived from these records.

Neither consumer is a program. If one ever becomes one, the schema below is the
contract; until then this is read by people, on demand, and its correctness is
checked the same way — by reading it against the paper.

## Why it exists

`UNKNOWNS.md` and `src/lab/k03.py` both sourced Daido's asymmetric exponent pair
to *Prog. Theor. Phys.* **75**, 1460 (1986). On 2026-09-03 somebody read all
four pages of that paper. The pair is not in it — its only fluctuation-exponent
statement, Eq. (7), gives the *same* exponent on both sides of the transition and
differs only in the amplitudes. The citation had been sitting on a public page
for a month, and nothing in this repo could have caught it, because a citation
was a string and not a receipt.

That is the whole argument. This lab's claim is that its numbers can be checked
by someone who does not trust it. A number pinned by a SHA-256 next to a
citation pinned by nothing is only half of that.

## What belongs here

Narrow, deliberately:

> **A source lands here when a claim this repo makes in public depends on what
> that source says, and a reader cannot verify it by clicking a link** — because
> the paper is paywalled, pre-arXiv, a scan, or because the load-bearing sentence
> sits three sections deep in a forty-page PDF.

Not every paper an assay names. `docs/assays/` already cites dozens, and most of
them are one click from a reader's browser and one sentence from an abstract.
Copying those here would buy nothing and would make the directory a bibliography
instead of a receipt drawer.

**No paper text beyond the load-bearing quotes.** These are short excerpts kept
for verification, not redistribution. A record whose paper was never reached
says so in its `reached` field and carries no equation numbers on that authority.

## The schema

One JSON file per source, named `<first-author>-<year>-<venue-locator>.json`:

| key | meaning |
|---|---|
| `id` | the filename stem, repeated so a detached record identifies itself |
| `citation` | authors, title, venue, and arXiv id / DOI where they exist |
| `reached` | `primary-full-text`, `abstract-only`, or `not-reached` — **only the first licenses citing an equation number** |
| `how_reached` | the route, including what was *not* opened |
| `urls` | every URL actually fetched, in the order tried |
| `retrieved` | the date the bytes were read |
| `why_this_source` | what this record is load-bearing for |
| `observable` | which susceptibility the paper's exponents are defined on — the distinction U-K02 turns on |
| `frequency_class` | sampling rule and `g(ω)`, because an exponent comparison across classes is meaningless |
| `quotes` | `{locator, quote, bears_on}` — verbatim, with the sentence's address inside the paper |
| `numbers` | every exponent the paper states, tagged by observable, class and side |
| `caveats` | what the record does *not* establish |

`manifest.json` pins each file: name, byte count, SHA-256 — both taken over the
file's bytes with CRLF newlines normalized to LF, which is the form git stores
and therefore the only form that means the same thing on every checkout (see
"Checking a record" for why that distinction has teeth here). It does not hash
itself — a manifest never can — so it is the one file here whose integrity is
git's problem rather than its own.

## Checking a record

```sh
python - <<'PY'
import hashlib, json, pathlib
d = pathlib.Path("evidence/literature")
man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
for e in man["files"]:
    raw = (d / e["path"]).read_bytes()
    got = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    print("OK  " if got == e["sha256"] else "DRIFT", e["path"])
PY
```

**The normalization is load-bearing, not tidiness.** This repo is checked out on
a Windows box with `core.autocrlf=true` and carries no `.gitattributes`, so git
stores these records with LF and hands the working tree CRLF. A hash over the
raw working-tree bytes therefore pins *one platform's checkout*, not the commit:
pinned here it verifies here and reads `DRIFT` on all eight records on Loam, on
CI, and in any fresh clone on Linux — eight false alarms, each of which the
paragraph below instructs a reader to answer by re-opening a paywalled paper.
Hashing the LF form pins the bytes git actually stores, which is the thing the
receipt claims to pin. The `bytes` field counts the same normalized form.

A `DRIFT` line does not mean the citation is wrong. It means the record was
edited after it was pinned, so the quote in front of you is no longer the quote
somebody read the paper to write down — and it has to be re-checked against the
paper before it is used, not re-hashed to make the warning go away.
