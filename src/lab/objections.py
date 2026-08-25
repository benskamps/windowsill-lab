"""The objection ledger — any voice may attach one, no voice may discharge one.

The 2026-08-25 adversarial audit refused adversarial *personas* with evidence:
two "rival" texts written by the same weights in the same session correlate near
1 on the only axis that matters — which answer is expected. The decisive
counter-example came from this repo: `k03.DAIDO` and `k03.HONG` were BOTH posed,
BOTH fully cited with journal, volume and year, as structured data — and K03
still received the asymmetric Millikan treatment. **Rival-count was never the
variable.**

But the audit's conclusion was framed too pessimistically as *"we cannot have an
adversary"*. We can. It cannot be a persona, and it does not have to be right.

## The three rules that keep this from being ceremony

1. **Additive only.** Any voice may RAISE an objection — Claude, Ember, Codex,
   Gemmi, Ben, a stranger reading the repo. **No voice may discharge one**,
   including the one that raised it. A 14B model handed clearing authority turns
   its inevitable failure to object into a rubber stamp with a receipt.

2. **Only an artifact answers.** An objection closes by pointing at something
   checkable — a receipt id, a commit sha, a URL, a measured number — never by
   prose. `answer()` refuses a bare assertion. This is the estate's own rule
   applied one level up: a verdict is an opinion, a re-derivation is a fact.

3. **They never expire and they are append-only.** The ledger is committed
   JSONL. An objection cannot be quietly dropped; withdrawing one appends a
   withdrawal that names who and why, and the original stays.

The consequence that makes it real: **a claim carrying an open objection cannot
publish as settled.** It publishes as `disputed`, visibly, on the feed the public
page reads. The objector does not have to win — they only have to be different
enough to notice something the author did not.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[2] / "objections.jsonl"

#: Voices that may raise. Deliberately open-ended in spirit but enumerated in
#: fact, so an objection's provenance is never ambiguous. `ben` is the only one
#: whose priors are genuinely uncorrelated with the author's.
VOICES = ("claude", "ember", "codex", "gemmi", "ben", "stranger")

RAISED = "raised"
ANSWERED = "answered"
WITHDRAWN = "withdrawn"

#: An answer must point at one of these. Prose is refused.
ARTIFACT_PREFIXES = ("receipt:", "commit:", "http://", "https://", "measured:")


@dataclass(frozen=True)
class Objection:
    """A recorded doubt about a claim, and who holds it."""

    id: str
    claim: str                    # receipt id, unknown id, or milestone id
    voice: str
    objection: str
    raised_at: str = ""
    status: str = RAISED
    answered_by: str = ""         # artifact reference, never prose
    answered_at: str = ""

    def __post_init__(self) -> None:
        for f in ("id", "claim", "objection"):
            if not str(getattr(self, f, "")).strip():
                raise ValueError(f"objection is missing {f}")
        if self.voice not in VOICES:
            raise ValueError(f"{self.voice!r} is not a known voice {VOICES}")
        if self.status not in (RAISED, ANSWERED, WITHDRAWN):
            raise ValueError(f"{self.status!r} is not a valid status")
        if self.status == ANSWERED and not self.answered_by:
            raise ValueError(
                f"{self.id}: an objection is answered by an ARTIFACT, not by "
                "saying it is answered — give a receipt:, commit:, http(s):// "
                "or measured: reference")

    @property
    def open(self) -> bool:
        return self.status == RAISED

    def to_json(self) -> dict:
        return {"id": self.id, "claim": self.claim, "voice": self.voice,
                "objection": self.objection, "raised_at": self.raised_at,
                "status": self.status, "answered_by": self.answered_by,
                "answered_at": self.answered_at}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load(path: Path | None = None) -> list[Objection]:
    """Replay the append-only ledger into current state.

    Later rows for an id supersede earlier ones, but the earlier rows remain on
    disk — that is the difference between a ledger and a database, and it is the
    whole point: an objection that was answered can still be read in the form it
    was raised.
    """
    p = path or LEDGER
    if not Path(p).exists():
        return []
    state: dict[str, Objection] = {}
    with Path(p).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                state[json.loads(line)["id"]] = Objection(**json.loads(line))
            except Exception:                                  # noqa: BLE001
                continue
    return list(state.values())


def _append(obj: Objection, path: Path | None = None) -> Objection:
    p = Path(path or LEDGER)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj.to_json()) + "\n")
    return obj


def raise_objection(claim: str, voice: str, objection: str,
                    path: Path | None = None) -> Objection:
    """Attach a doubt to a claim. Cheap on purpose — the cost of an objection
    must be lower than the cost of staying quiet, or nobody raises one."""
    existing = load(path)
    oid = f"O{len(existing) + 1:03d}"
    return _append(Objection(id=oid, claim=claim, voice=voice,
                             objection=objection, raised_at=_now()), path)


def answer(oid: str, artifact: str, path: Path | None = None) -> Objection:
    """Close an objection by pointing at something checkable.

    Deliberately does NOT take a voice: it does not matter who answers, because
    the answer is the artifact and the artifact is checkable by anyone. That is
    also why the objector cannot 'discharge' their own objection by fiat —
    there is no route through this function that does not produce a reference.
    """
    if not any(artifact.startswith(p) for p in ARTIFACT_PREFIXES):
        raise ValueError(
            f"{artifact!r} is not an artifact. An objection is answered by "
            f"evidence a stranger can check, not by assertion — use one of "
            f"{ARTIFACT_PREFIXES}")
    current = {o.id: o for o in load(path)}
    if oid not in current:
        raise ValueError(f"no objection {oid}")
    o = current[oid]
    return _append(Objection(id=o.id, claim=o.claim, voice=o.voice,
                             objection=o.objection, raised_at=o.raised_at,
                             status=ANSWERED, answered_by=artifact,
                             answered_at=_now()), path)


def withdraw(oid: str, voice: str, why: str, path: Path | None = None) -> Objection:
    """Take back an objection. The original row stays on disk."""
    current = {o.id: o for o in load(path)}
    if oid not in current:
        raise ValueError(f"no objection {oid}")
    o = current[oid]
    if voice != o.voice:
        raise ValueError(
            f"{voice!r} cannot withdraw an objection raised by {o.voice!r} — "
            "only the holder of a doubt may stop holding it")
    return _append(Objection(id=o.id, claim=o.claim, voice=o.voice,
                             objection=f"{o.objection} [withdrawn: {why}]",
                             raised_at=o.raised_at, status=WITHDRAWN), path)


def open_against(claim: str, path: Path | None = None) -> list[Objection]:
    return [o for o in load(path) if o.claim == claim and o.open]


def disputed(path: Path | None = None) -> dict:
    """The block that rides the public feed.

    A claim with an open objection publishes as DISPUTED. The objector does not
    have to be right — the reader is told a doubt exists and who holds it, which
    is strictly more than the reader had before.
    """
    all_ = load(path)
    open_ = [o for o in all_ if o.open]
    by_claim: dict[str, list] = {}
    for o in open_:
        by_claim.setdefault(o.claim, []).append(
            {"id": o.id, "voice": o.voice, "objection": o.objection})
    return {
        "total": len(all_),
        "open": len(open_),
        "answered": len([o for o in all_ if o.status == ANSWERED]),
        "withdrawn": len([o for o in all_ if o.status == WITHDRAWN]),
        "disputed_claims": by_claim,
        "voices": sorted({o.voice for o in all_}),
    }
