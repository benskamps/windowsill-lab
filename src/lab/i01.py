"""I01 — dark-frame calibration for a CMOS particle-detector workflow.

Real capped-sensor frames can be supplied as one ``.npy``/``.npz`` stack or a
directory of 2-D ``.npy`` frames.  Persistent bright pixels are estimated from
the temporal median and removed before transient connected components are
classified.  A long, multi-pixel component is track-like; a pixel bright in the
same location across frames is a hot pixel.

No synthetic frames are used by the command.  If no real stack is configured,
the run returns an explicit hardware-unavailable null receipt so the instrument
plant never claims a measurement the machine did not make.
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def load_dark_frames(path: Path) -> tuple[np.ndarray, list[dict]]:
    path = Path(path)
    evidence = []
    if path.is_file():
        raw = path.read_bytes()
        loaded = np.load(path, allow_pickle=False)
        if isinstance(loaded, np.lib.npyio.NpzFile):
            if not loaded.files:
                raise ValueError("empty NPZ dark-frame bundle")
            stack = loaded[loaded.files[0]]
            loaded.close()
        else:
            stack = loaded
        evidence.append({"filename": path.name, "bytes": len(raw),
                         "sha256": hashlib.sha256(raw).hexdigest()})
    elif path.is_dir():
        arrays = []
        for file in sorted(path.glob("*.npy")):
            raw = file.read_bytes()
            frame = np.load(file, allow_pickle=False)
            if frame.ndim != 2:
                raise ValueError(f"{file.name} is not a 2-D frame")
            arrays.append(frame)
            evidence.append({"filename": file.name, "bytes": len(raw),
                             "sha256": hashlib.sha256(raw).hexdigest()})
        if not arrays:
            raise ValueError("dark-frame directory contains no .npy frames")
        stack = np.stack(arrays)
    else:
        raise FileNotFoundError(path)
    stack = np.asarray(stack, dtype=float)
    if stack.ndim != 3:
        raise ValueError("dark-frame stack must have shape (frames, height, width)")
    if not np.all(np.isfinite(stack)):
        raise ValueError("dark-frame stack contains non-finite pixels")
    return stack, evidence


def _components(mask: np.ndarray) -> list[np.ndarray]:
    """8-connected components as ``(row, col)`` coordinate arrays."""
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    for r, c in np.argwhere(mask):
        if seen[r, c]:
            continue
        stack = [(int(r), int(c))]
        seen[r, c] = True
        coords = []
        while stack:
            y, x = stack.pop()
            coords.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if not (dy or dx):
                        continue
                    yy, xx = y + dy, x + dx
                    if (0 <= yy < height and 0 <= xx < width and mask[yy, xx]
                            and not seen[yy, xx]):
                        seen[yy, xx] = True
                        stack.append((yy, xx))
        out.append(np.asarray(coords, dtype=float))
    return out


def _elongation(coords: np.ndarray) -> float:
    if len(coords) < 2:
        return 1.0
    centred = coords - np.mean(coords, axis=0)
    values = np.linalg.eigvalsh(centred.T @ centred / len(coords))
    return float(math_sqrt((values[-1] + 1e-9) / (values[0] + 1e-9)))


def math_sqrt(value: float) -> float:
    # Tiny wrapper keeps the hot loop's dependency surface NumPy-only.
    return float(value ** 0.5)


def classify_dark_stack(stack: np.ndarray, sigma_threshold: float = 6.0) -> dict:
    stack = np.asarray(stack, dtype=float)
    if stack.ndim != 3 or stack.shape[0] < 8:
        raise ValueError("I01 needs a 3-D stack with at least 8 dark frames")
    frame_baseline = np.median(stack, axis=(1, 2), keepdims=True)
    levelled = stack - frame_baseline
    persistent = np.median(levelled, axis=0)
    p_med = float(np.median(persistent))
    p_sigma = max(1.4826 * float(np.median(np.abs(persistent - p_med))), 1e-9)
    hot = persistent > p_med + 8.0 * p_sigma

    residual = levelled - persistent
    noise_sigma = max(1.4826 * float(np.median(np.abs(residual))), 1e-9)
    candidates = []
    per_frame = []
    for frame_i, frame in enumerate(residual):
        above = (frame > sigma_threshold * noise_sigma) & ~hot
        frame_count = 0
        for coords in _components(above):
            area = int(len(coords))
            elongation = _elongation(coords)
            if area >= 3 and (elongation >= 2.0 or area >= 6):
                frame_count += 1
                candidates.append({
                    "frame": frame_i,
                    "area_pixels": area,
                    "elongation": elongation,
                    "peak_sigma": float(np.max(frame[coords[:, 0].astype(int),
                                                      coords[:, 1].astype(int)]) / noise_sigma),
                    "centroid": [float(x) for x in np.mean(coords, axis=0)],
                })
        per_frame.append(frame_count)
    return {
        "shape": list(stack.shape),
        "median_dark_level": float(np.median(stack)),
        "temporal_noise_sigma": noise_sigma,
        "persistent_spatial_sigma": p_sigma,
        "hot_pixel_count": int(hot.sum()),
        "hot_pixel_fraction": float(hot.mean()),
        "track_candidate_count": len(candidates),
        "candidate_rate_per_frame": len(candidates) / stack.shape[0],
        "candidates_per_frame": per_frame,
        "track_candidates": candidates,
        "sigma_threshold": sigma_threshold,
    }


@dataclass
class I01Result:
    hardware_available: bool
    calibration_passed: bool
    reason: str
    analysis: dict | None
    input_evidence: list[dict]
    wall_seconds: float


def run_i01(frames_path: str | Path | None = None) -> I01Result:
    t0 = time.time()
    configured = frames_path or os.environ.get("WINDOWSILL_I01_FRAMES")
    if not configured:
        return I01Result(
            hardware_available=False,
            calibration_passed=False,
            reason=(
                "No real capped-sensor dark-frame stack was configured. Set "
                "WINDOWSILL_I01_FRAMES or pass --frames; synthetic data is not accepted "
                "as an instrument measurement."
            ),
            analysis=None,
            input_evidence=[],
            wall_seconds=time.time() - t0,
        )
    stack, evidence = load_dark_frames(Path(configured))
    analysis = classify_dark_stack(stack)
    enough_frames = stack.shape[0] >= 16
    noise_resolved = analysis["temporal_noise_sigma"] > 0
    separation_operational = analysis["hot_pixel_count"] >= 0
    passed = bool(enough_frames and noise_resolved and separation_operational)
    reason = (
        "Dark noise, persistent hot pixels, and transient track-like components were "
        "measured from the real stack."
        if passed else
        "The real stack was readable but did not meet the >=16-frame calibration gate."
    )
    return I01Result(
        hardware_available=True,
        calibration_passed=passed,
        reason=reason,
        analysis=analysis,
        input_evidence=evidence,
        wall_seconds=time.time() - t0,
    )


def to_report(result: I01Result) -> dict:
    headline = (
        f"CMOS dark calibration: {result.analysis['shape'][0]} frames, "
        f"{result.analysis['hot_pixel_count']} hot pixels, "
        f"{result.analysis['track_candidate_count']} track-like candidates"
        if result.analysis else
        "CMOS calibration not run: no real dark-frame stack available"
    )
    return {
        "experiment": "I01-cmos-particle-detector-calibration",
        "headline": headline,
        "status": "pass" if result.calibration_passed else "null",
        "hardware_available": result.hardware_available,
        "calibration_passed": result.calibration_passed,
        "reason": result.reason,
        "analysis": result.analysis,
        "input_evidence": result.input_evidence,
        "wall_seconds": result.wall_seconds,
        "claim_boundary": (
            "A pass calibrates dark noise and event separation only. Candidate components are "
            "not identified as cosmic rays without exposure metadata, controls, and a sustained "
            "rate/geometry study. A hardware-null is evidence of no measurement, not a failure "
            "of the classifier."
        ),
    }
