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

#: **Refutations.** A named astrophysical or instrumental explanation: the
#: ladder found a reason the signal is not a fresh planet candidate. Any of
#: these on any sector parks the star (``lab.shelf`` §4).
GATE_DISPOSITIONS = (
    "stellar-pulsation", "harmonic-alias", "eclipsing-binary-odd-even",
    "eclipsing-binary-secondary", "eclipsing-binary-p2-alias",
    "phased-brightening", "low-significance",
    "insufficient-coverage", "period-railed", "centroid-shift",
    "companion-too-large",
    # --- sky gates (2026-08-20): the ladder's first questions that are about
    # the field rather than the series. See lab.a05_sky and the TIC 77044472
    # investigation — a lead can be a real planet on the wrong star.
    "blended-known-planet", "blend-favours-neighbour",
)

#: **Catalog identities.** Somebody already filed this signal. Not a claim
#: about what it is; only "not a fresh lead".
IDENTITY_DISPOSITIONS = (
    "recovery-or-known", "known-planet", "toi-known-fp", "ctoi-known",
)

#: **The one terminal state the machine may assign.** Evidence, never a
#: promotion — only a human promotes (``docs/shelf-exit-contract.md``).
LEAD_DISPOSITION = "lead-awaiting-human-review"

#: The machine's ENTIRE disposition vocabulary. "planet" is not in it, and
#: neither is bare "planet-candidate" — that is a vetting VERDICT, an
#: intermediate rung; the ladder must resolve it to a blend gate, a catalog
#: identification, or the terminal lead state before the receipt is written.
#: Ordered as the ladder walks it: series gates, then sky gates, then catalog,
#: then the terminal human-review state.
#:
#: DERIVED from the three groups above rather than listed a fourth time, and
#: that is the load-bearing part: the groups are how ``lab.shelf`` decides
#: whether a word refutes a star, and a word can only enter the vocabulary
#: through one of them. Before 2026-09-19 shelf restated the split, so a word
#: added here alone was in the vocabulary, passed the checker, and fell
#: through shelf's grading silently — leaving the star PROMOTABLE. That is
#: VET-F1 again, one surface over.
MACHINE_DISPOSITIONS = (
    *GATE_DISPOSITIONS, *IDENTITY_DISPOSITIONS, LEAD_DISPOSITION,
)

#: Set form, for the checker's membership test.
MACHINE_VOCABULARY = frozenset(MACHINE_DISPOSITIONS)

#: Panels a lead's dossier must carry, in the order the dossier builds them.
#: THE contract, not a copy of it: ``lab.a05_sensitivity`` produces dossiers
#: against this tuple and ``lab.checks`` gate 6 refuses a lead that is missing
#: any of it. It lives here rather than beside the producer for the same
#: reason the vocabulary does — ``lab.checks`` must stay importable without
#: numpy, and the producer needs numpy, so a direct import would have made the
#: checker depend on the engine it grades.
DOSSIER_REQUIRED_PANELS = (
    "fold_p", "fold_half_p", "fold_2p",
    "odd_even", "secondary", "self_injection",
)

#: TFOPWG dispositions that mean "the community already refuted this signal".
#: FP = false positive (astrophysical impostor, e.g. a blend), FA = false
#: alarm (instrumental). Either way nothing real was re-found: the row is
#: neither a recovery nor a lead. Shared for the same reason as the above —
#: the checker's gate 5 and the engine's ladder must read one list.
TOI_REFUTED_DISPOSITIONS = ("FP", "FA")
