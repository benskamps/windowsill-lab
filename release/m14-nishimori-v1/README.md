# M14 Nishimori-line verification release

This is a narrow, offline receipt for one result already committed by
Windowsill Lab. It regrades the eight persisted aggregate energy measurements
at `L=24` in `evidence/2026-07-05-m14.json` against

```text
E/N = -2 tanh(1/T)
```

All eight saved points lie on the declared Nishimori line and fall inside the
checker-owned absolute tolerance of `0.05`. The largest recomputed absolute
deviation is `0.015110101699829181`.

From this directory, verify the extracted bundle with Python 3.11 or newer. No
network access or third-party packages are used:

```sh
python verify_release.py receipt.json --strict
```

To confirm that the checked-in manifest and deterministic ZIP still match the
loose files:

```sh
python build_archive.py --check
```

## Boundary of the receipt

This release verifies agreement of saved aggregate measurements with a known
identity at eight sampled points and one declared numerical gate. It does not:

- prove the Nishimori identity or test every point on the line;
- precisely locate the multicritical Nishimori point;
- claim novelty, peer review, or a formal proof;
- rerun the Monte Carlo simulation;
- provide per-realization samples, trajectories, bonds, spins, or RNG states;
- attest the run-start commit, clean-tree state, machine, package versions, or
  run timestamp, because the committed report did not record them.

The full provenance boundary and the distinction between the exact theoretical
target and the statistical measurement are machine-readable in `receipt.json`.
The commit named there is the first commit containing the report, not an
assertion about which checkout produced the run.
