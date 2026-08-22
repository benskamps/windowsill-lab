"""The A05 disposition vocabulary — ONE definition, two readers.

The engine (:mod:`lab.a05`) writes a machine disposition onto every
above-threshold row; the checker (:mod:`lab.checks`) refuses any row carrying
a word outside the vocabulary. For most of A05's life those were two separate
literals, and on 2026-08-19/20 the sky and blend gates taught the engine five
new honest words — ``eclipsing-binary-p2-alias``, ``companion-too-large``,
``blended-known-planet``, ``blend-favours-neighbour``, ``ctoi-known`` — while
the checker kept the old thirteen. The first honest refutation those gates
drew would therefore have failed gate 4 and quarantined the WHOLE receipt:
the slice lost, the targets silently re-eligible. A restated contract is not
a contract.

This module is the single source of truth. It is deliberately **stdlib only**
and imports nothing from the rest of the package, so ``lab.checks`` — which
re-derives receipts without trusting them, and must stay importable without
numpy or any engine code — can read the vocabulary without importing the
engine that produced the receipt it is grading.
"""
from __future__ import annotations

#: The machine's ENTIRE disposition vocabulary. "planet" is not in it, and
#: neither is bare "planet-candidate" — that is a vetting VERDICT, an
#: intermediate rung; the ladder must resolve it to a blend gate, a catalog
#: identification, or the terminal lead state before the receipt is written.
#: Ordered as the ladder walks it: series gates, then sky gates, then catalog,
#: then the terminal human-review state.
MACHINE_DISPOSITIONS = (
    "stellar-pulsation", "harmonic-alias", "eclipsing-binary-odd-even",
    "eclipsing-binary-secondary", "eclipsing-binary-p2-alias",
    "phased-brightening", "low-significance",
    "insufficient-coverage", "period-railed", "centroid-shift",
    "companion-too-large",
    # --- sky gates (2026-08-20): the ladder's first questions that are about
    # the field rather than the series. See lab.a05_sky and the TIC 77044472
    # investigation — a lead can be a real planet on the wrong star.
    "blended-known-planet", "blend-favours-neighbour",
    "recovery-or-known", "known-planet", "toi-known-fp", "ctoi-known",
    "lead-awaiting-human-review",
)

#: Set form, for the checker's membership test.
MACHINE_VOCABULARY = frozenset(MACHINE_DISPOSITIONS)

#: TFOPWG dispositions that mean "the community already refuted this signal".
#: FP = false positive (astrophysical impostor, e.g. a blend), FA = false
#: alarm (instrumental). Either way nothing real was re-found: the row is
#: neither a recovery nor a lead. Shared for the same reason as the above —
#: the checker's gate 5 and the engine's ladder must read one list.
TOI_REFUTED_DISPOSITIONS = ("FP", "FA")
