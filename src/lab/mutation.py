"""Auditing the auditor — a check that cannot be made to fail is not a check.

`checks.py` grades every number the lab reports. Nothing grades `checks.py`.
That asymmetry is the lab's largest unexamined assumption: the verification code
is written the same way the kernels are, by the same agents, and a systematic
error inside a check would be invisible to every receipt that check has ever
signed. A green gate proves the check ran. It does not prove the check looked.

This module makes the check look. Take a report the check currently passes,
corrupt one number in it, and ask the check again. If the verdict does not move,
the check is blind to that number — and a check blind to every number it reads
is a rubber stamp with a docstring.

### What a mutation means

Four corruptions, chosen so that at least one is unambiguously fatal for any
quantity a physics check could care about:

* ``scale_2x`` / ``scale_half`` — the number is wrong by a factor of two. No
  measured exponent, temperature, or depth survives that and stays correct.
* ``sign_flip`` — the number has the wrong sign.
* ``drop`` — the field is missing entirely. A check that grades a field it never
  requires will happily pass a report that does not contain it, which is how a
  gate silently becomes optional.

### Reading the output

Four outcomes per mutation, and the distinction matters:

* **killed** — the check returned False. The check saw it.
* **survived** — the check returned True. The check is blind to that field.
* **inapplicable** — the check returned None (not its experiment, or a
  precondition is unmet). Neither credit nor blame.
* **crashed** — the check raised. This is *not* a pass: a check that explodes on
  a malformed report cannot grade one, and the traceback is a finding.

**Survivals are not automatically defects.** A report carries wall-clock
seconds, provenance strings, and snapshots that no physics check should grade,
and corrupting those SHOULD leave the verdict alone. What the survivor list is
for is reading: the question it answers is "does this check notice its own
headline number", and that question has to be asked by a person looking at the
list, not by a threshold.

What *is* automatically a defect is a check that kills nothing at all. That one
is mechanical, and :func:`audit` reports it as ``vacuous``.

### What this does not do

It mutates REPORTS, not kernels. A kernel mutation — flip a sign inside
`ising.py`, re-run the experiment, confirm the check goes red — tests the whole
loop and is the stronger instrument; it also costs a full experiment run per
mutation, so it belongs in a scheduled campaign rather than a test suite. This
is the cheap half, and the cheap half is the half that runs on every commit.
"""
from __future__ import annotations

import copy
from typing import Any, Callable, Iterable

#: The corruptions applied to each numeric leaf. ``drop`` removes the key.
KINDS = ("scale_2x", "scale_half", "sign_flip", "drop")

#: Numbers this small are already indistinguishable from zero for grading
#: purposes, so scaling them is not a real corruption and would manufacture
#: bogus "survived" entries. Sign-flipping and dropping still apply.
NEGLIGIBLE = 1e-12

#: Keys whose subtrees are never mutated: bulk arrays that would explode the
#: path count without adding information, and the provenance block, which is
#: string metadata. Snapshots are lattice dumps — thousands of leaves that all
#: say the same thing about a check's sensitivity.
SKIP_KEYS = ("snapshots", "provenance", "reproduction")


def numeric_paths(obj: Any, prefix: tuple = (), *,
                  max_paths: int = 2000,
                  skip_keys: Iterable[str] = SKIP_KEYS) -> list[tuple]:
    """Every path to a numeric leaf, as a tuple of dict keys and list indices.

    Bools are excluded: ``True`` is an ``int`` in Python but a flag in a report,
    and scaling a flag by two is not a corruption anyone can reason about.
    """
    out: list[tuple] = []
    skip = set(skip_keys)

    def walk(node: Any, path: tuple) -> None:
        if len(out) >= max_paths:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                if key in skip:
                    continue
                walk(value, path + (key,))
        elif isinstance(node, (list, tuple)):
            for i, value in enumerate(node):
                walk(value, path + (i,))
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            out.append(path)

    walk(obj, prefix)
    return out


def get_path(obj: Any, path: tuple) -> Any:
    for key in path:
        obj = obj[key]
    return obj


def _parent(obj: Any, path: tuple):
    return get_path(obj, path[:-1]), path[-1]


def mutate(report: dict, path: tuple, kind: str) -> dict:
    """A deep copy of ``report`` with one leaf corrupted. Never mutates in place."""
    out = copy.deepcopy(report)
    container, key = _parent(out, path)
    if kind == "drop":
        if isinstance(container, list):
            del container[key]
        else:
            container.pop(key, None)
        return out
    value = container[key]
    if kind == "scale_2x":
        container[key] = value * 2
    elif kind == "scale_half":
        container[key] = value / 2
    elif kind == "sign_flip":
        container[key] = -value
    else:
        raise ValueError(f"unknown mutation kind {kind!r}")
    return out


def audit(check: Callable[[dict], tuple], report: dict, *,
          kinds: Iterable[str] = KINDS, max_paths: int = 2000,
          skip_keys: Iterable[str] = SKIP_KEYS) -> dict:
    """Corrupt every numeric leaf in turn; record what the check noticed.

    The baseline is graded first: auditing a check against a report it does not
    already pass says nothing, so ``baseline`` is reported and a non-True
    baseline short-circuits with ``usable: False``.
    """
    try:
        baseline, baseline_detail = check(report)
    except Exception as exc:                     # noqa: BLE001
        return {"usable": False, "baseline": None,
                "baseline_detail": f"{type(exc).__name__}: {exc}",
                "reason": "baseline-crashed"}
    if baseline is not True:
        return {"usable": False, "baseline": baseline,
                "baseline_detail": baseline_detail,
                "reason": "baseline-not-passing"}

    paths = numeric_paths(report, max_paths=max_paths, skip_keys=skip_keys)
    killed: list[tuple] = []
    survived: list[tuple] = []
    crashed: list[tuple] = []
    inapplicable: list[tuple] = []
    for path in paths:
        value = get_path(report, path)
        for kind in kinds:
            if kind in ("scale_2x", "scale_half") and abs(value) < NEGLIGIBLE:
                continue
            if kind == "sign_flip" and abs(value) < NEGLIGIBLE:
                continue
            try:
                verdict, _ = check(mutate(report, path, kind))
            except Exception:                    # noqa: BLE001 — a finding, see docstring
                crashed.append((path, kind))
                continue
            if verdict is False:
                killed.append((path, kind))
            elif verdict is None:
                inapplicable.append((path, kind))
            else:
                survived.append((path, kind))
    attempted = len(killed) + len(survived) + len(crashed) + len(inapplicable)
    graded = len(killed) + len(survived)
    return {
        "usable": True,
        "baseline": True,
        "n_paths": len(paths),
        "attempted": attempted,
        "killed": killed,
        "survived": survived,
        "crashed": crashed,
        "inapplicable": inapplicable,
        # Sensitivity is over the mutations that produced a VERDICT: a check
        # that answers "not applicable" to a corruption has not been tested by
        # it, and counting those either way would move the number for reasons
        # that have nothing to do with the check's eyesight.
        "sensitivity": (len(killed) / graded) if graded else 0.0,
        "vacuous": len(killed) == 0,
    }


def blind_fields(result: dict) -> list[str]:
    """Dotted field names the check never noticed, deduplicated and sorted.

    The survivor list is per (path, kind); this collapses it to the fields a
    person should read, which is the form the audit is actually used in.
    """
    fields = {".".join(str(p) for p in path) for path, _ in result.get("survived", ())}
    fields -= {".".join(str(p) for p in path) for path, _ in result.get("killed", ())}
    return sorted(fields)


def graded_fields(result: dict) -> list[str]:
    """Dotted field names whose corruption the check DID notice."""
    return sorted({".".join(str(p) for p in path)
                   for path, _ in result.get("killed", ())})
