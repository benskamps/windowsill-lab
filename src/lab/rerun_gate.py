"""No rerun when nothing changed: the scheduler's same-inputs gate.

Measured 2026-11-04. The campaign came back on 11-02 and spent all seven of
its experiment turns repeating itself: C03 computed the SAME 64 Motzkin terms
five times and A03 re-searched the SAME GW170817 strain file (same sha256)
twice for the same null. Every one of those receipts carries the same
``provenance.source_tree_sha256`` (1486855263…), the same Python and the same
libraries — the run could only ever reproduce its own receipt. Planner v2's
repeat decay does not stop that: it halves a rung per CONSECUTIVE repeat and
resets the moment anything else runs, so C03 / C03 / C03 / A03 / C03 … is a
two-member carousel the decay never breaks (it is symmetric across the pair —
see the saturation note in ``curriculum``).

The rule here is the one Ben set: **a scheduled run is skipped when nothing
that could change its answer has changed since its newest receipt.** "Could
change its answer" is, precisely:

* its code — the experiment's own module closure (the lab modules the CLI
  dispatch block for its subcommand imports, followed transitively), diffed
  with git between the receipt's ``provenance.source_commit`` and HEAD, plus
  any uncommitted edit to those files;
* its environment — Python, platform and the numpy/torch/matplotlib versions
  the receipt's provenance recorded;
* its declared inputs — for a milestone with several targets (C03), each
  target is its own run, so the milestone is unchanged only when EVERY
  registered target already has an unchanged receipt.

A seed is not a change: the campaign hands every pass a new one, and a new
sample of a verified verdict is exactly the repeat this gate exists to stop.

**Boundary, stated so a skip is never over-read.** The gate cannot see
upstream data change (an OEIS b-file edited by its editors, a MAST
reprocessing): it reads committed state and the local checkout, never the
network, so the planner stays re-derivable. A manual ``lab <cmd>`` always runs
— the gate sits in ``lab next`` only. And a gate that cannot see does not
pretend: a receipt with no provenance, a dirty source state at run time, or a
git that will not answer makes the milestone eligible again (the old
behaviour), never silently skipped. Running when unsure costs one repeat;
skipping when unsure could hide a regression.
"""

from __future__ import annotations

import ast
import functools
import json
import platform
import subprocess
from pathlib import Path
from typing import Iterable, Mapping

SRC = Path(__file__).resolve().parent
REPO_ROOT = SRC.parent.parent

#: Runs whose inputs are new by construction. The hunt searches a fresh slice
#: of sky every turn (the planner exempts it from the repeat law for the same
#: reason); I01 captures new frames from a camera each run.
EXEMPT: dict[str, str] = {
    "A05": "each hunt turn searches a fresh slice of sky",
    "A05-HUNT": "each hunt turn searches a fresh slice of sky",
    "I01": "each run captures new frames",
}


def _multi_target_inputs() -> dict[str, tuple[str, tuple[str, ...]]]:
    """``{mid: (receipt_field, every_registered_input)}`` for milestones whose
    runs differ by a declared input rather than by code."""
    from . import c03
    return {"C03": ("target", tuple(c03.TARGETS))}


#: The runner flag that selects one of a multi-target milestone's inputs, so
#: ``lab next`` can dispatch the next untried one instead of the default. This
#: is how C03 moves on: it ran A001006 fifteen times and A000045 never.
INPUT_FLAG: dict[str, str] = {"C03": "--target"}


# ── code closure ─────────────────────────────────────────────────────────────

def _lab_imports(tree: ast.AST) -> set[str]:
    """Lab module stems a parsed module imports (relative or ``lab.`` absolute)."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level == 1:
                if base:
                    found.add(base.split(".")[0])
                else:
                    found.update(a.name.split(".")[0] for a in node.names)
            elif node.level == 0 and (base == "lab" or base.startswith("lab.")):
                rest = base[len("lab."):] if base.startswith("lab.") else ""
                if rest:
                    found.add(rest.split(".")[0])
                else:
                    found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("lab."):
                    found.add(a.name.split(".")[1])
    return {m for m in found if (SRC / f"{m}.py").is_file()}


#: Modules that file, lay out or grade a report but never compute a number in
#: it. Every dispatch block imports ``render`` and ``publish``, and between
#: them they reach 28 other modules, so following them would make every
#: experiment depend on nearly the whole tree and any edit anywhere would
#: re-open every run. The numbers a receipt carries come from the science
#: module's own ``to_report``; a change to the grader (``checks``) is answered
#: by ``lab verify`` re-reading the stored receipts, which needs no rerun.
PLUMBING = frozenset({"cli", "render", "publish", "checks"})


@functools.lru_cache(maxsize=None)
def _parsed(stem: str) -> ast.AST | None:
    try:
        return ast.parse((SRC / f"{stem}.py").read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None


def _dispatch_roots(subcommand: str) -> set[str] | None:
    """Lab modules imported inside ``cli.main``'s ``if cmd == "<subcommand>"``
    block; ``None`` when no such block exists (the caller then falls back to
    the whole ``src/lab`` tree, which over-reports change, never under)."""
    tree = _parsed("cli")
    if tree is None:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        tests = [node.test]
        if isinstance(node.test, ast.BoolOp):
            tests = list(node.test.values)
        for t in tests:
            if (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
                    and t.left.id == "cmd" and len(t.comparators) == 1
                    and isinstance(t.comparators[0], ast.Constant)
                    and t.comparators[0].value == subcommand):
                block = ast.Module(body=node.body, type_ignores=[])
                return _lab_imports(block)
    return None


def code_closure(subcommand: str) -> list[str] | None:
    """Repo-relative paths of every lab module the subcommand can execute.

    ``None`` means the dispatch block could not be found; callers treat that
    as "compare the whole tree" rather than guessing a smaller set.
    """
    roots = _dispatch_roots(subcommand)
    if roots is None:
        return None
    seen: set[str] = set()
    todo = list(roots - PLUMBING)
    if not todo:
        return None  # a dispatch block that imports no science: compare everything
    while todo:
        mod = todo.pop()
        if mod in seen:
            continue
        seen.add(mod)
        tree = _parsed(mod)
        if tree is not None:
            todo.extend(_lab_imports(tree) - seen - PLUMBING)
    return sorted(f"src/lab/{m}.py" for m in seen)


# ── environment ──────────────────────────────────────────────────────────────

def current_environment() -> dict:
    """The same three provenance fields ``render._stamp_report_json`` writes."""
    from . import render
    return {
        "python": platform.python_version(),
        "platform": f"{platform.system().lower()}-{platform.machine().lower()}",
        "dependencies": render._dependency_versions(),
    }


# ── receipts ─────────────────────────────────────────────────────────────────

def newest_receipts(receipts_dir: Path) -> dict[tuple[str, str | None], tuple[str, dict]]:
    """``{(mid, input_or_None): (generated_at, receipt)}`` — newest per key.

    Keyed by input only for the milestones ``_multi_target_inputs`` names.
    """
    from . import publish as publish_mod
    multi = _multi_target_inputs()
    newest: dict[tuple[str, str | None], tuple[str, dict]] = {}
    date_glob = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
    for path in sorted(receipts_dir.glob(f"run-{date_glob}-*.json")):
        _date, _turn, slug = publish_mod._split_receipt_stem(path.stem[len("run-"):])
        if not slug:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        stamp = data.get("generated_at")
        if not isinstance(stamp, str) or not stamp:
            continue
        mid = slug.upper()
        key_input = None
        if mid in multi:
            key_input = data.get(multi[mid][0])
            if not isinstance(key_input, str):
                continue
        key = (mid, key_input)
        if key not in newest or stamp > newest[key][0]:
            newest[key] = (stamp, data)
    return newest


def _git(*args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-C", str(REPO_ROOT), *args],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None


def why_changed(receipt: dict, files: list[str] | None, env: Mapping) -> str | None:
    """The first thing that differs between this receipt's run and a run now,
    or ``None`` when nothing does. Unknown always counts as changed."""
    prov = receipt.get("provenance")
    if not isinstance(prov, dict):
        return "its newest receipt has no provenance"
    commit = prov.get("source_commit")
    if not isinstance(commit, str) or not commit:
        return "its newest receipt names no source commit"
    if prov.get("source_clean") is not True:
        return "its newest receipt ran on uncommitted source"
    for field in ("python", "platform", "dependencies"):
        if prov.get(field) != env.get(field):
            return f"{field} differs ({prov.get(field)} then, {env.get(field)} now)"
    paths = files if files is not None else ["src/lab"]
    diff = _git("diff", "--quiet", commit, "HEAD", "--", *paths)
    if diff is None or diff.returncode not in (0, 1):
        return f"git cannot compare against {commit[:8]}"
    if diff.returncode == 1:
        return f"its code changed since {commit[:8]}"
    dirty = _git("status", "--porcelain", "--", *paths)
    if dirty is None or dirty.returncode != 0:
        return "git cannot read the working tree"
    if dirty.stdout.strip():
        return "its code has uncommitted edits"
    return None


def unchanged_since_last_run(
    mids: Iterable[str],
    subcommands: Mapping[str, str],
    receipts_dir: Path,
    env: Mapping | None = None,
) -> dict[str, str]:
    """``{mid: reason}`` for every mid whose next scheduled run would repeat
    its newest receipt exactly. Mids not in the result are free to run."""
    env = dict(env) if env is not None else current_environment()
    newest = newest_receipts(receipts_dir)
    multi = _multi_target_inputs()
    closures: dict[str, list[str] | None] = {}
    out: dict[str, str] = {}
    for mid in mids:
        if mid in EXEMPT or mid not in subcommands:
            continue
        sub = subcommands[mid]
        if sub not in closures:
            closures[sub] = code_closure(sub)
        files = closures[sub]
        inputs = multi[mid][1] if mid in multi else (None,)
        stamps: list[str] = []
        for key_input in inputs:
            hit = newest.get((mid, key_input))
            if hit is None or why_changed(hit[1], files, env) is not None:
                break
            stamps.append(hit[0][:10])
        else:
            scope = (f"{len(files)} source files" if files is not None
                     else "the src/lab tree")
            what = (f"every registered target ({', '.join(inputs)}) already ran"
                    if mid in multi else f"its newest receipt ({max(stamps)})")
            out[mid] = (f"nothing changed since its last run: {what} on the same "
                        f"code ({scope}), Python and libraries, so a rerun would "
                        "only repeat it")
    return out


def next_input(mid: str, subcommand: str, receipts_dir: Path,
               env: Mapping | None = None) -> str | None:
    """For a multi-target milestone: the first registered input whose newest
    receipt is missing or would change. ``None`` when every input is done (or
    the milestone has a single input)."""
    multi = _multi_target_inputs()
    if mid not in multi:
        return None
    env = dict(env) if env is not None else current_environment()
    newest = newest_receipts(receipts_dir)
    files = code_closure(subcommand)
    for key_input in multi[mid][1]:
        hit = newest.get((mid, key_input))
        if hit is None or why_changed(hit[1], files, env) is not None:
            return key_input
    return None
