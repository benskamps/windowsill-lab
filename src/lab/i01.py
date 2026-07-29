"""I01 — dark-frame calibration for a CMOS particle-detector workflow.

Real capped-sensor frames can be supplied as one ``.npy``/``.npz`` stack, a
directory of 2-D ``.npy`` frames, or acquired from a live camera with
``capture_dark_frames``.  Camera acquisition happens in a disposable child
process: a camera backend that wedges cannot wedge the lab process with it.

Persistent bright pixels are estimated from the temporal median and removed
before transient connected components are classified.  A long, multi-pixel
component is track-like; a pixel bright in the same location across frames is a
hot pixel.

No synthetic frames are used by the command.  If no real stack is configured,
the run returns an explicit hardware-unavailable null receipt so the instrument
plant never claims a measurement the machine did not make.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import multiprocessing
import os
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np


# These are deliberately conservative.  Analysis holds the input, a levelled
# float32 copy, and (briefly) an absolute-deviation workspace.
MAX_FRAME_COUNT = 2_048
MAX_FRAME_HEIGHT = 8_192
MAX_FRAME_WIDTH = 8_192
MAX_STACK_PIXELS = 67_108_864
MAX_ANALYSIS_WORK_BYTES = 1_100_000_000
MAX_INPUT_BYTES = 1_100_000_000
HASH_CHUNK_BYTES = 1024 * 1024
MAX_CANDIDATE_PIXELS_PER_FRAME = 100_000
MAX_CANDIDATE_FRACTION = 0.05
MAX_STORED_CANDIDATES = 256

ProgressCallback = Callable[[dict[str, Any]], None]
FileSignature = tuple[int, int, int, int, int]


class I01Error(Exception):
    """Base class for expected, user-actionable I01 failures."""

    code = "i01_error"


class DarkFrameInputError(I01Error, ValueError):
    code = "invalid_dark_frames"


class DarkFrameNotFoundError(I01Error, FileNotFoundError):
    code = "dark_frames_not_found"


class CaptureError(I01Error):
    code = "capture_failed"


class CaptureUnavailableError(CaptureError):
    code = "capture_unavailable"


class CameraUnavailableError(CaptureUnavailableError):
    code = "camera_unavailable"


class CameraReadError(CaptureError):
    code = "camera_read_failed"


class CaptureTimeoutError(CaptureError, TimeoutError):
    code = "capture_timeout"


class CaptureOutputError(CaptureError):
    code = "capture_output_error"


@dataclass(frozen=True)
class CaptureResult:
    """Saved products and provenance from one real camera acquisition."""

    stack_path: Path
    metadata_path: Path
    metadata: dict[str, Any]
    input_evidence: list[dict[str, Any]]


def _emit_progress(
    callback: ProgressCallback | None,
    stage: str,
    **details: Any,
) -> None:
    if callback is not None:
        callback({"stage": stage, **details})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash_file(path: Path) -> tuple[str, int]:
    """Hash a file incrementally so evidence does not duplicate it in memory."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _stat_signature(stat_result: os.stat_result) -> FileSignature:
    """Identity plus mutation-sensitive fields for one filesystem object."""
    return (
        int(stat_result.st_dev),
        int(stat_result.st_ino),
        int(stat_result.st_size),
        int(stat_result.st_mtime_ns),
        int(stat_result.st_ctime_ns),
    )


def _file_evidence(
    path: Path,
    *,
    expected_signature: FileSignature | None = None,
    **extra: Any,
) -> dict[str, Any]:
    try:
        before = path.stat()
        if (
            expected_signature is not None
            and _stat_signature(before) != expected_signature
        ):
            raise DarkFrameInputError(
                f"{path} changed between input preflight and evidence hashing; "
                "stop the writer and retry"
            )
        digest, size = _hash_file(path)
        after = path.stat()
    except DarkFrameInputError:
        raise
    except OSError as exc:
        raise DarkFrameInputError(
            f"cannot read {path} for input evidence: {exc}"
        ) from exc
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or size != after.st_size
    ):
        raise DarkFrameInputError(
            f"{path} changed while it was being read; stop the writer and retry"
        )
    return {
        "filename": path.name,
        "bytes": size,
        "sha256": digest,
        **extra,
    }


def _validate_numeric_dtype(dtype: np.dtype, *, context: str) -> None:
    dtype = np.dtype(dtype)
    if (
        not np.issubdtype(dtype, np.number)
        or np.issubdtype(dtype, np.complexfloating)
    ):
        raise DarkFrameInputError(
            f"{context} has unsupported dtype {dtype}; use real-valued grayscale pixels"
        )


def _validate_frame_shape(shape: tuple[int, ...], *, context: str) -> None:
    if len(shape) != 2:
        raise DarkFrameInputError(
            f"{context} is not a 2-D grayscale frame (found shape {shape})"
        )
    height, width = (int(x) for x in shape)
    if height <= 0 or width <= 0:
        raise DarkFrameInputError(f"{context} has an empty dimension: {shape}")
    if height > MAX_FRAME_HEIGHT or width > MAX_FRAME_WIDTH:
        raise DarkFrameInputError(
            f"{context} is {height}x{width}; the safety limit is "
            f"{MAX_FRAME_HEIGHT}x{MAX_FRAME_WIDTH}"
        )


def _validate_stack_shape(
    shape: tuple[int, ...],
    *,
    context: str,
    minimum_frames: int = 1,
    raw_input_bytes: int = 0,
) -> int:
    if len(shape) != 3:
        raise DarkFrameInputError(
            f"{context} must have shape (frames, height, width), found {shape}"
        )
    frame_count, height, width = (int(x) for x in shape)
    if frame_count < minimum_frames:
        raise DarkFrameInputError(
            f"{context} has {frame_count} frames; I01 needs at least "
            f"{minimum_frames}"
        )
    if frame_count > MAX_FRAME_COUNT:
        raise DarkFrameInputError(
            f"{context} has {frame_count} frames; the safety limit is "
            f"{MAX_FRAME_COUNT}. Split or down-sample the acquisition."
        )
    _validate_frame_shape((height, width), context=f"{context} frame")
    pixels = frame_count * height * width
    if pixels > MAX_STACK_PIXELS:
        raise DarkFrameInputError(
            f"{context} contains {pixels:,} pixels; the safety limit is "
            f"{MAX_STACK_PIXELS:,}. Capture fewer or smaller frames."
        )
    if raw_input_bytes < 0:
        raise DarkFrameInputError("raw input byte count cannot be negative")
    # Four float32-scale analysis buffers plus masks/medians and the caller's
    # still-live source array.  Counting the source separately is deliberately
    # conservative when a contiguous float32 input can be reused in place.
    estimated_work_bytes = (
        pixels * 16 + height * width * 16 + int(raw_input_bytes)
    )
    if estimated_work_bytes > MAX_ANALYSIS_WORK_BYTES:
        raise DarkFrameInputError(
            f"{context} would require about "
            f"{estimated_work_bytes / (1024 ** 2):.0f} MiB of analysis workspace; "
            f"the safety limit is {MAX_ANALYSIS_WORK_BYTES / (1024 ** 2):.0f} MiB"
        )
    return pixels


def _to_float32(
    array: np.ndarray,
    *,
    context: str,
    owned: bool = False,
) -> np.ndarray:
    _validate_numeric_dtype(array.dtype, context=context)
    with np.errstate(over="ignore", invalid="ignore"):
        converted = (
            np.array(array, dtype=np.float32, order="C", copy=True)
            if owned
            else np.ascontiguousarray(array, dtype=np.float32)
        )
    if not np.all(np.isfinite(converted)):
        raise DarkFrameInputError(
            f"{context} contains non-finite pixels or values outside float32 range"
        )
    return converted


def _inspect_npz_member(
    path: Path,
    member_key: str,
) -> tuple[tuple[int, ...], np.dtype]:
    """Read an NPZ member's NPY header before decompressing its pixel payload."""
    member_name = f"{member_key}.npy"
    try:
        with zipfile.ZipFile(path) as bundle:
            info = bundle.getinfo(member_name)
            if info.file_size > MAX_INPUT_BYTES:
                raise DarkFrameInputError(
                    f"{path.name}:{member_key} expands to {info.file_size:,} bytes; "
                    f"the safety limit is {MAX_INPUT_BYTES:,}"
                )
            with bundle.open(info) as member:
                version = np.lib.format.read_magic(member)
                if version == (1, 0):
                    header_reader = np.lib.format.read_array_header_1_0
                elif version == (2, 0):
                    header_reader = np.lib.format.read_array_header_2_0
                else:
                    raise DarkFrameInputError(
                        f"{path.name}:{member_key} uses unsupported NPY header "
                        f"version {version}"
                    )
                shape, _fortran_order, dtype = header_reader(member)
    except KeyError as exc:
        raise DarkFrameInputError(
            f"{path.name} has an invalid NPZ member for {member_key!r}"
        ) from exc
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise DarkFrameInputError(f"cannot read {path.name}: {exc}") from exc
    return tuple(int(x) for x in shape), np.dtype(dtype)


def _load_single_stack(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix == ".npy":
        try:
            raw = np.load(path, allow_pickle=False, mmap_mode="r")
        except (OSError, ValueError, EOFError) as exc:
            raise DarkFrameInputError(f"cannot read {path.name}: {exc}") from exc
        _validate_stack_shape(
            tuple(raw.shape),
            context=f"dark-frame stack {path.name}",
            raw_input_bytes=max(
                int(raw.nbytes),
                int(raw.size) * np.dtype(np.float32).itemsize,
            ),
        )
        # Do not return an ndarray backed by the source memmap.  Besides keeping
        # files locked on Windows, that would let later source mutations change
        # pixels after their evidence hash had been recorded.
        return _to_float32(raw, context=path.name, owned=True)

    if suffix != ".npz":
        raise DarkFrameInputError(
            f"{path.name} is not .npy or .npz; provide a real NumPy dark-frame stack"
        )

    try:
        with np.load(path, allow_pickle=False) as bundle:
            keys = list(bundle.files)
            if not keys:
                raise DarkFrameInputError("empty NPZ dark-frame bundle")
            if len(keys) != 1:
                raise DarkFrameInputError(
                    f"{path.name} contains {len(keys)} arrays ({', '.join(keys)}); "
                    "NPZ input must contain exactly one unambiguous dark-frame stack"
                )
            shape, dtype = _inspect_npz_member(path, keys[0])
            _validate_numeric_dtype(dtype, context=f"{path.name}:{keys[0]}")
            _validate_stack_shape(
                shape,
                context=f"dark-frame stack {path.name}:{keys[0]}",
                raw_input_bytes=(
                    int(shape[0])
                    * int(shape[1])
                    * int(shape[2])
                    * max(int(dtype.itemsize), np.dtype(np.float32).itemsize)
                ),
            )
            raw = bundle[keys[0]]
            # Confirm the archive header inspected above matches NumPy's decoded
            # array before committing analysis memory.
            if tuple(raw.shape) != shape or np.dtype(raw.dtype) != dtype:
                raise DarkFrameInputError(
                    f"{path.name}:{keys[0]} changed while it was being read"
                )
            return _to_float32(raw, context=f"{path.name}:{keys[0]}")
    except DarkFrameInputError:
        raise
    except (OSError, ValueError, EOFError, zipfile.BadZipFile) as exc:
        raise DarkFrameInputError(f"cannot read {path.name}: {exc}") from exc


def _load_frame_directory(
    path: Path,
    files: list[Path],
    progress: ProgressCallback | None,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    if len(files) > MAX_FRAME_COUNT:
        raise DarkFrameInputError(
            f"{path} contains {len(files)} .npy frames; the safety limit is "
            f"{MAX_FRAME_COUNT}"
        )

    expected_shape: tuple[int, int] | None = None
    dtypes: list[np.dtype] = []
    source_signatures: list[FileSignature] = []
    total_input_bytes = 0
    # Inspect every header before allocating the combined stack.  This catches a
    # late mismatched frame without first stacking all the earlier files.
    for file in files:
        try:
            source_stat = file.stat()
        except OSError as exc:
            raise DarkFrameInputError(
                f"cannot stat directory frame {file.name}: {exc}"
            ) from exc
        total_input_bytes += source_stat.st_size
        if total_input_bytes > MAX_INPUT_BYTES:
            raise DarkFrameInputError(
                f"{path} contains more than {MAX_INPUT_BYTES:,} input bytes; "
                "split or down-sample the acquisition"
            )
        try:
            frame = np.load(file, allow_pickle=False, mmap_mode="r")
        except (OSError, ValueError, EOFError) as exc:
            raise DarkFrameInputError(f"cannot read {file.name}: {exc}") from exc
        shape = tuple(int(x) for x in frame.shape)
        _validate_frame_shape(shape, context=file.name)
        _validate_numeric_dtype(frame.dtype, context=file.name)
        if expected_shape is None:
            expected_shape = shape
        elif shape != expected_shape:
            raise DarkFrameInputError(
                f"directory frames do not match: {file.name} is {shape}, "
                f"expected {expected_shape}"
            )
        dtypes.append(np.dtype(frame.dtype))
        source_signatures.append(_stat_signature(source_stat))

    assert expected_shape is not None
    stack_shape = (len(files), *expected_shape)
    stack_pixels = int(stack_shape[0] * stack_shape[1] * stack_shape[2])
    _validate_stack_shape(
        stack_shape,
        context=f"dark-frame directory {path}",
        raw_input_bytes=stack_pixels * np.dtype(np.float32).itemsize,
    )
    stack = np.empty(stack_shape, dtype=np.float32)
    evidence: list[dict[str, Any]] = []
    entries = zip(files, dtypes, source_signatures, strict=True)
    for index, (file, expected_dtype, source_signature) in enumerate(entries):
        try:
            frame = np.load(file, allow_pickle=False, mmap_mode="r")
        except (OSError, ValueError, EOFError) as exc:
            raise DarkFrameInputError(f"cannot read {file.name}: {exc}") from exc
        if (
            tuple(frame.shape) != expected_shape
            or np.dtype(frame.dtype) != expected_dtype
        ):
            raise DarkFrameInputError(
                f"{file.name} changed after preflight; stop the writer and retry"
            )
        converted = _to_float32(frame, context=file.name)
        stack[index] = converted
        evidence.append(
            _file_evidence(file, expected_signature=source_signature)
        )
        _emit_progress(
            progress,
            "load",
            current=index + 1,
            total=len(files),
            filename=file.name,
        )
    return stack, evidence


def load_dark_frames(
    path: Path,
    *,
    progress: ProgressCallback | None = None,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Load and authenticate a bounded real dark-frame stack.

    The returned analysis array is contiguous ``float32``.  File hashes are
    streamed, and directory members are shape-checked before the stack is
    allocated.
    """
    path = Path(path)
    _emit_progress(progress, "preflight", source=str(path))
    if path.is_file():
        try:
            source_stat = path.stat()
        except OSError as exc:
            raise DarkFrameInputError(f"cannot stat {path}: {exc}") from exc
        size = source_stat.st_size
        if size > MAX_INPUT_BYTES:
            raise DarkFrameInputError(
                f"{path.name} is {size:,} bytes; the input safety limit is "
                f"{MAX_INPUT_BYTES:,}"
            )
        stack = _load_single_stack(path)
        evidence = [
            _file_evidence(
                path,
                expected_signature=_stat_signature(source_stat),
            )
        ]
        _emit_progress(progress, "load", current=1, total=1, filename=path.name)
    elif path.is_dir():
        files = sorted(path.glob("*.npy"))
        if not files:
            raise DarkFrameInputError(
                f"{path} contains no .npy frames; export 2-D grayscale frames first"
            )
        stack, evidence = _load_frame_directory(path, files, progress)
    elif path.exists():
        raise DarkFrameInputError(f"{path} is not a regular file or directory")
    else:
        raise DarkFrameNotFoundError(
            f"dark-frame input does not exist: {path}. Check --frames or "
            "WINDOWSILL_I01_FRAMES."
        )
    return stack, evidence


def _cv2_available() -> bool:
    return importlib.util.find_spec("cv2") is not None


def _worker_send(connection: Any, event: dict[str, Any]) -> None:
    try:
        connection.send(event)
    except (BrokenPipeError, EOFError, OSError):
        # The bounded parent may have timed out and terminated its side.
        pass


def _capture_worker(connection: Any, request: dict[str, Any]) -> None:
    """Child-process entry point.  Never call a camera backend in the parent."""
    capture = None
    started = time.monotonic()
    started_at = _utc_now()
    try:
        try:
            import cv2  # type: ignore[import-not-found]
        except (ImportError, ModuleNotFoundError) as exc:
            _worker_send(
                connection,
                {
                    "type": "error",
                    "code": "missing_cv2",
                    "message": (
                        "OpenCV is not installed. Install the optional camera "
                        "extra (`pip install windowsill-lab[camera]`) and retry."
                    ),
                },
            )
            return

        camera_index = int(request["camera_index"])
        capture = cv2.VideoCapture(camera_index)
        if request.get("width") is not None:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, int(request["width"]))
        if request.get("height") is not None:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, int(request["height"]))
        if not capture.isOpened():
            _worker_send(
                connection,
                {
                    "type": "error",
                    "code": "camera_unavailable",
                    "message": (
                        f"camera {camera_index} could not be opened. Close other "
                        "camera apps, check OS camera permission, and retry."
                    ),
                },
            )
            return

        backend = None
        try:
            backend = capture.getBackendName()
        except (AttributeError, RuntimeError):
            pass

        frame_count = int(request["frame_count"])
        stack: np.ndarray | None = None
        frame_shape: tuple[int, int] | None = None
        for index in range(frame_count):
            ok, raw_frame = capture.read()
            if not ok or raw_frame is None:
                _worker_send(
                    connection,
                    {
                        "type": "error",
                        "code": "camera_read_failed",
                        "message": (
                            f"camera {camera_index} stopped at frame {index + 1}/"
                            f"{frame_count}. Check the device connection and retry."
                        ),
                    },
                )
                return
            raw_frame = np.asarray(raw_frame)
            if raw_frame.ndim == 2:
                gray = raw_frame
            elif raw_frame.ndim == 3 and raw_frame.shape[2] == 3:
                gray = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY)
            elif raw_frame.ndim == 3 and raw_frame.shape[2] == 4:
                gray = cv2.cvtColor(raw_frame, cv2.COLOR_BGRA2GRAY)
            else:
                _worker_send(
                    connection,
                    {
                        "type": "error",
                        "code": "unsupported_camera_frame",
                        "message": (
                            f"camera {camera_index} returned unsupported shape "
                            f"{tuple(raw_frame.shape)}; expected grayscale, BGR, or BGRA"
                        ),
                    },
                )
                return
            gray = np.ascontiguousarray(gray)
            if not np.issubdtype(gray.dtype, np.number) or np.issubdtype(
                gray.dtype, np.complexfloating
            ):
                _worker_send(
                    connection,
                    {
                        "type": "error",
                        "code": "unsupported_camera_dtype",
                        "message": f"camera returned unsupported dtype {gray.dtype}",
                    },
                )
                return
            if not np.all(np.isfinite(gray)):
                _worker_send(
                    connection,
                    {
                        "type": "error",
                        "code": "non_finite_camera_frame",
                        "message": f"camera frame {index + 1} contains non-finite pixels",
                    },
                )
                return

            current_shape = (int(gray.shape[0]), int(gray.shape[1]))
            if stack is None:
                try:
                    _validate_stack_shape(
                        (frame_count, *current_shape),
                        context="live camera acquisition",
                        raw_input_bytes=(
                            frame_count
                            * current_shape[0]
                            * current_shape[1]
                            * max(
                                int(gray.dtype.itemsize),
                                np.dtype(np.float32).itemsize,
                            )
                        ),
                    )
                except DarkFrameInputError as exc:
                    _worker_send(
                        connection,
                        {
                            "type": "error",
                            "code": "capture_size_limit",
                            "message": str(exc),
                        },
                    )
                    return
                frame_shape = current_shape
                stack = np.empty((frame_count, *current_shape), dtype=gray.dtype)
            elif current_shape != frame_shape or gray.dtype != stack.dtype:
                _worker_send(
                    connection,
                    {
                        "type": "error",
                        "code": "camera_format_changed",
                        "message": (
                            f"camera format changed at frame {index + 1}: "
                            f"{current_shape}/{gray.dtype}, expected "
                            f"{frame_shape}/{stack.dtype}"
                        ),
                    },
                )
                return
            stack[index] = gray
            _worker_send(
                connection,
                {
                    "type": "progress",
                    "current": index + 1,
                    "total": frame_count,
                },
            )

        assert stack is not None and frame_shape is not None
        staging_path = Path(request["staging_path"])
        np.save(staging_path, stack, allow_pickle=False)
        _worker_send(
            connection,
            {
                "type": "result",
                "metadata": {
                    "source": "camera",
                    "synthetic": False,
                    "camera_index": camera_index,
                    "frame_count": frame_count,
                    "width": frame_shape[1],
                    "height": frame_shape[0],
                    "dtype": str(stack.dtype),
                    "backend": backend,
                    "started_at_utc": started_at,
                    "completed_at_utc": _utc_now(),
                    "elapsed_seconds": time.monotonic() - started,
                    "dark_conditions_verified": False,
                },
            },
        )
    except Exception as exc:
        _worker_send(
            connection,
            {
                "type": "error",
                "code": "capture_worker_error",
                "message": (
                    f"camera acquisition failed with {type(exc).__name__}: {exc}. "
                    "Check camera permission, backend support, and output space."
                ),
            },
        )
    finally:
        if capture is not None:
            try:
                capture.release()
            except Exception:
                pass
        try:
            connection.close()
        except (AttributeError, OSError):
            pass


def _terminate_process(process: Any) -> None:
    if not process.is_alive():
        process.join(timeout=0.2)
        return
    process.terminate()
    process.join(timeout=0.5)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=0.5)


def _cleanup_private_paths(*paths: Path) -> None:
    """Best-effort cleanup for UUID-named staging files owned by this call."""
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _claim_staging_product(
    staging_path: Path,
    output_path: Path,
) -> FileSignature:
    """Atomically publish a staging file without replacing any destination."""
    try:
        os.link(staging_path, output_path)
    except FileExistsError as exc:
        raise CaptureOutputError(
            f"refusing to overwrite capture product created during acquisition: "
            f"{output_path}"
        ) from exc
    except OSError as exc:
        raise CaptureOutputError(
            f"could not atomically publish {output_path} without overwrite: {exc}. "
            "Choose a writable local filesystem that supports hard links."
        ) from exc
    _cleanup_private_paths(staging_path)
    try:
        return _stat_signature(output_path.stat())
    except OSError as exc:
        raise CaptureOutputError(
            f"published capture product disappeared before verification: "
            f"{output_path}: {exc}"
        ) from exc


def _unlink_if_owned(path: Path, signature: FileSignature | None) -> None:
    """Remove a published product only while it is still the file we created."""
    if signature is None:
        return
    try:
        if _stat_signature(path.stat()) == signature:
            path.unlink()
    except OSError:
        pass


def _capture_error(code: str, message: str) -> CaptureError:
    if code == "missing_cv2":
        error: CaptureError = CaptureUnavailableError(message)
    elif code == "camera_unavailable":
        error = CameraUnavailableError(message)
    elif code == "camera_read_failed":
        error = CameraReadError(message)
    elif code in {"capture_size_limit", "capture_output_error"}:
        error = CaptureOutputError(message)
    else:
        error = CaptureError(message)
    # Preserve the worker's actionable machine-readable reason even when its
    # broad exception class is shared with other camera failures.
    error.code = code
    return error


def capture_dark_frames(
    output_path: str | Path,
    *,
    camera_index: int = 0,
    frame_count: int = 24,
    timeout_seconds: float = 30.0,
    width: int | None = None,
    height: int | None = None,
    progress: ProgressCallback | None = None,
    _worker: Callable[[Any, dict[str, Any]], None] | None = None,
    _context: Any | None = None,
) -> CaptureResult:
    """Acquire and save a real grayscale ``.npy`` stack with bounded latency.

    OpenCV is an optional dependency and is imported only inside this API's
    child process.  ``timeout_seconds`` bounds camera/backend work in the parent;
    on expiry the disposable child is terminated.  Existing outputs are never
    overwritten.

    The private ``_worker``/``_context`` seams permit deterministic failure
    injection in tests without requiring a physical camera.
    """
    output_path = Path(output_path)
    if output_path.suffix.lower() != ".npy":
        raise CaptureOutputError(
            f"capture output must end in .npy, found {output_path.name!r}"
        )
    metadata_path = output_path.with_suffix(output_path.suffix + ".capture.json")
    if output_path.exists() or metadata_path.exists():
        raise CaptureOutputError(
            f"refusing to overwrite capture product: {output_path if output_path.exists() else metadata_path}"
        )
    if isinstance(camera_index, bool) or not isinstance(camera_index, int):
        raise CaptureError("camera_index must be an integer device index")
    if camera_index < 0:
        raise CaptureError("camera_index must be zero or greater")
    if isinstance(frame_count, bool) or not isinstance(frame_count, int):
        raise CaptureError("frame_count must be an integer")
    if frame_count <= 0 or frame_count > MAX_FRAME_COUNT:
        raise CaptureError(
            f"frame_count must be between 1 and {MAX_FRAME_COUNT}, found {frame_count}"
        )
    if (
        not np.isfinite(timeout_seconds)
        or timeout_seconds <= 0
        or timeout_seconds > 3_600
    ):
        raise CaptureError("timeout_seconds must be in (0, 3600]")
    for name, value, limit in (
        ("width", width, MAX_FRAME_WIDTH),
        ("height", height, MAX_FRAME_HEIGHT),
    ):
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            or value > limit
        ):
            raise CaptureError(f"{name} must be an integer in [1, {limit}]")
    if width is not None and height is not None:
        try:
            _validate_stack_shape(
                (frame_count, height, width),
                context="requested live camera acquisition",
            )
        except DarkFrameInputError as exc:
            raise CaptureError(str(exc)) from exc

    worker = _capture_worker if _worker is None else _worker
    if _worker is None and not _cv2_available():
        raise CaptureUnavailableError(
            "OpenCV is not installed. Install the optional camera extra "
            "(`pip install windowsill-lab[camera]`) and retry."
        )

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise CaptureOutputError(
            f"cannot create capture directory {output_path.parent}: {exc}"
        ) from exc
    staging_path = output_path.with_name(
        f".{output_path.stem}.{uuid.uuid4().hex}.capture.npy"
    )
    request = {
        "camera_index": camera_index,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "output_path": str(output_path),
        "staging_path": str(staging_path),
    }
    context = _context or multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=worker,
        args=(send_connection, request),
        name="windowsill-i01-camera",
        daemon=True,
    )
    _emit_progress(
        progress,
        "capture_start",
        camera_index=camera_index,
        total=frame_count,
        timeout_seconds=float(timeout_seconds),
    )
    try:
        process.start()
    except Exception as exc:
        receive_connection.close()
        send_connection.close()
        raise CaptureUnavailableError(
            f"could not start isolated camera process: {type(exc).__name__}: {exc}"
        ) from exc

    deadline = time.monotonic() + float(timeout_seconds)
    final_event: dict[str, Any] | None = None
    try:
        try:
            send_connection.close()
            while final_event is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    # One final non-blocking drain avoids racing a
                    # just-completed worker at the exact deadline.
                    if receive_connection.poll(0):
                        try:
                            event = receive_connection.recv()
                        except EOFError:
                            break
                    else:
                        raise CaptureTimeoutError(
                            f"camera {camera_index} did not deliver "
                            f"{frame_count} frames within {timeout_seconds:g}s; "
                            "the camera process was terminated. Try fewer frames, "
                            "a different camera index, or close other camera apps."
                        )
                else:
                    event = None
                    if receive_connection.poll(min(0.1, remaining)):
                        try:
                            event = receive_connection.recv()
                        except EOFError:
                            break
                    elif not process.is_alive():
                        break
                if event is None:
                    continue
                if event.get("type") == "progress":
                    _emit_progress(
                        progress,
                        "capture",
                        current=int(event["current"]),
                        total=int(event["total"]),
                        camera_index=camera_index,
                    )
                elif event.get("type") in {"result", "error"}:
                    final_event = event
        finally:
            receive_connection.close()
            try:
                send_connection.close()
            except OSError:
                pass
            if final_event is None:
                # This covers timeout, worker crash, Ctrl-C, recv failures, and
                # observer callback exceptions.  No escape path may strand a
                # camera backend after the public call has returned.
                _terminate_process(process)
            else:
                process.join(timeout=0.5)
                if process.is_alive():
                    _terminate_process(process)
    except BaseException:
        _cleanup_private_paths(staging_path)
        raise

    if final_event is None:
        exitcode = process.exitcode
        _cleanup_private_paths(staging_path)
        raise CaptureError(
            f"isolated camera process exited without a result (exit code {exitcode}); "
            "check camera drivers and OS camera permission"
        )
    if final_event["type"] == "error":
        _cleanup_private_paths(staging_path)
        raise _capture_error(
            str(final_event.get("code", "capture_failed")),
            str(final_event.get("message", "camera acquisition failed")),
        )
    if not staging_path.is_file():
        raise CaptureOutputError(
            "camera process reported success but did not save its private "
            f"staging product {staging_path.name}"
        )

    try:
        metadata = dict(final_event["metadata"])
    except (KeyError, TypeError, ValueError) as exc:
        _cleanup_private_paths(staging_path)
        error = CaptureError(
            f"camera process returned invalid capture metadata: {exc}"
        )
        error.code = "invalid_capture_metadata"
        raise error from exc
    output_signature: FileSignature | None = None
    metadata_signature: FileSignature | None = None
    temporary_metadata = metadata_path.with_name(
        f".{metadata_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        output_signature = _claim_staging_product(staging_path, output_path)
        evidence = _file_evidence(
            output_path,
            expected_signature=output_signature,
            source="camera",
            synthetic=False,
            camera_index=camera_index,
            frame_count=int(metadata["frame_count"]),
            width=int(metadata["width"]),
            height=int(metadata["height"]),
            dtype=str(metadata["dtype"]),
            elapsed_seconds=float(metadata["elapsed_seconds"]),
            output_path=str(output_path.resolve()),
        )
        metadata.update(
            {
                "output_path": str(output_path.resolve()),
                "metadata_path": str(metadata_path.resolve()),
                "bytes": evidence["bytes"],
                "sha256": evidence["sha256"],
            }
        )
        with temporary_metadata.open("x", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, sort_keys=True)
            handle.write("\n")
        metadata_signature = _claim_staging_product(
            temporary_metadata, metadata_path
        )
    except DarkFrameInputError as exc:
        _cleanup_private_paths(staging_path, temporary_metadata)
        _unlink_if_owned(metadata_path, metadata_signature)
        _unlink_if_owned(output_path, output_signature)
        raise CaptureOutputError(
            f"captured frames but could not record their evidence: {exc}"
        ) from exc
    except (OSError, TypeError, ValueError) as exc:
        _cleanup_private_paths(staging_path, temporary_metadata)
        _unlink_if_owned(metadata_path, metadata_signature)
        _unlink_if_owned(output_path, output_signature)
        raise CaptureOutputError(
            f"captured frames but could not save metadata {metadata_path}: {exc}"
        ) from exc
    except BaseException:
        _cleanup_private_paths(staging_path, temporary_metadata)
        _unlink_if_owned(metadata_path, metadata_signature)
        _unlink_if_owned(output_path, output_signature)
        raise
    _emit_progress(
        progress,
        "capture_complete",
        current=frame_count,
        total=frame_count,
        output_path=str(output_path),
        sha256=evidence["sha256"],
    )
    return CaptureResult(
        stack_path=output_path,
        metadata_path=metadata_path,
        metadata=metadata,
        input_evidence=[evidence],
    )


def _iter_components(mask: np.ndarray):
    """Yield 8-connected components as integer ``(row, col)`` arrays."""
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    for r, c in np.argwhere(mask):
        if seen[r, c]:
            continue
        pending = [(int(r), int(c))]
        seen[r, c] = True
        coords: list[tuple[int, int]] = []
        while pending:
            y, x = pending.pop()
            coords.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if not (dy or dx):
                        continue
                    yy, xx = y + dy, x + dx
                    if (
                        0 <= yy < height
                        and 0 <= xx < width
                        and mask[yy, xx]
                        and not seen[yy, xx]
                    ):
                        seen[yy, xx] = True
                        pending.append((yy, xx))
        yield np.asarray(coords, dtype=np.int32)


def _components(mask: np.ndarray) -> list[np.ndarray]:
    """Compatibility wrapper returning all 8-connected components."""
    return list(_iter_components(mask))


def _elongation(coords: np.ndarray) -> float:
    if len(coords) < 2:
        return 1.0
    centred = coords - np.mean(coords, axis=0)
    values = np.linalg.eigvalsh(centred.T @ centred / len(coords))
    return float(math_sqrt((values[-1] + 1e-9) / (values[0] + 1e-9)))


def math_sqrt(value: float) -> float:
    # Tiny wrapper keeps the hot loop's dependency surface NumPy-only.
    return float(value**0.5)


def _unique_frame_count(stack: np.ndarray) -> int:
    digests = {
        hashlib.sha256(frame.view(np.uint8).reshape(-1)).digest()
        for frame in stack
    }
    return len(digests)


def classify_dark_stack(
    stack: np.ndarray,
    sigma_threshold: float = 6.0,
    *,
    max_candidate_pixels_per_frame: int = MAX_CANDIDATE_PIXELS_PER_FRAME,
    max_candidate_fraction: float = MAX_CANDIDATE_FRACTION,
    max_stored_candidates: int = MAX_STORED_CANDIDATES,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Classify a bounded dark stack without inventing a numerical noise floor."""
    raw_stack = np.asarray(stack)
    _validate_stack_shape(
        tuple(raw_stack.shape),
        context="I01 dark-frame stack",
        minimum_frames=8,
        raw_input_bytes=int(raw_stack.nbytes),
    )
    if not np.isfinite(sigma_threshold) or sigma_threshold <= 0:
        raise DarkFrameInputError("sigma_threshold must be finite and greater than zero")
    if (
        isinstance(max_candidate_pixels_per_frame, bool)
        or not isinstance(max_candidate_pixels_per_frame, int)
        or max_candidate_pixels_per_frame <= 0
    ):
        raise DarkFrameInputError(
            "max_candidate_pixels_per_frame must be a positive integer"
        )
    if (
        not np.isfinite(max_candidate_fraction)
        or max_candidate_fraction <= 0
        or max_candidate_fraction > 1
    ):
        raise DarkFrameInputError("max_candidate_fraction must be in (0, 1]")
    if (
        isinstance(max_stored_candidates, bool)
        or not isinstance(max_stored_candidates, int)
        or max_stored_candidates < 0
    ):
        raise DarkFrameInputError("max_stored_candidates must be zero or greater")

    stack32 = _to_float32(raw_stack, context="I01 dark-frame stack")
    frame_count, height, width = stack32.shape
    unique_frames = _unique_frame_count(stack32)
    minimum_unique_frames = max(2, (frame_count + 1) // 2)
    duplicate_fraction = 1.0 - unique_frames / frame_count
    stack_constant = bool(float(np.min(stack32)) == float(np.max(stack32)))

    _emit_progress(progress, "analysis_baseline", total=frame_count)
    frame_baseline = np.median(stack32, axis=(1, 2), keepdims=True)
    residual = stack32.copy()
    residual -= frame_baseline
    persistent = np.median(residual, axis=0).astype(np.float32, copy=False)
    p_med = float(np.median(persistent))
    persistent_deviation = persistent.copy()
    persistent_deviation -= p_med
    np.abs(persistent_deviation, out=persistent_deviation)
    # Preserve the measured raw MAD sigma, including a physically meaningful 0.
    p_sigma = 1.4826 * float(
        np.median(persistent_deviation, overwrite_input=True)
    )
    if p_sigma > 0:
        hot = persistent > p_med + 8.0 * p_sigma
    else:
        # Sparse positive persistent defects can coexist with a zero spatial MAD.
        hot = persistent > p_med

    residual -= persistent
    noise_deviation = np.empty_like(residual)
    np.abs(residual, out=noise_deviation)
    noise_sigma = 1.4826 * float(
        np.median(noise_deviation, overwrite_input=True)
    )
    del noise_deviation

    quality_failures: list[str] = []
    if stack_constant:
        quality_failures.append("constant_stack")
    if unique_frames < minimum_unique_frames:
        quality_failures.append("insufficient_unique_frames")
    if noise_sigma <= 0:
        quality_failures.append("temporal_noise_unresolved")

    candidates: list[dict[str, Any]] = []
    candidate_total = 0
    candidate_component_total = 0
    threshold_pixel_total = 0
    per_frame: list[int] = []
    flood_frames: list[dict[str, int]] = []
    frame_pixel_limit = min(
        max_candidate_pixels_per_frame,
        max(1, int(np.ceil(height * width * max_candidate_fraction))),
    )
    for frame_i, frame in enumerate(residual):
        if noise_sigma > 0:
            above = (frame > sigma_threshold * noise_sigma) & ~hot
            threshold_pixels = int(np.count_nonzero(above))
        else:
            above = np.zeros((height, width), dtype=bool)
            threshold_pixels = 0
        threshold_pixel_total += threshold_pixels
        frame_candidate_count = 0
        if threshold_pixels > frame_pixel_limit:
            # Never hand a contaminated full-frame mask to Python flood-fill.
            flood_frames.append(
                {
                    "frame": frame_i,
                    "threshold_crossing_pixels": threshold_pixels,
                    "pixel_limit": frame_pixel_limit,
                }
            )
        else:
            for coords in _iter_components(above):
                candidate_component_total += 1
                area = int(len(coords))
                elongation = _elongation(coords)
                if area >= 3 and (elongation >= 2.0 or area >= 6):
                    frame_candidate_count += 1
                    candidate_total += 1
                    if len(candidates) < max_stored_candidates:
                        rows = coords[:, 0]
                        columns = coords[:, 1]
                        candidates.append(
                            {
                                "frame": frame_i,
                                "area_pixels": area,
                                "elongation": elongation,
                                "peak_sigma": float(
                                    np.max(frame[rows, columns]) / noise_sigma
                                ),
                                "centroid": [
                                    float(x) for x in np.mean(coords, axis=0)
                                ],
                            }
                        )
        per_frame.append(frame_candidate_count)
        _emit_progress(
            progress,
            "analysis_frame",
            current=frame_i + 1,
            total=frame_count,
            threshold_crossing_pixels=threshold_pixels,
            candidate_flood=threshold_pixels > frame_pixel_limit,
        )

    if flood_frames:
        quality_failures.append("candidate_flood_frames")
    return {
        "shape": list(stack32.shape),
        "analysis_dtype": str(stack32.dtype),
        "median_dark_level": float(np.median(stack32)),
        "temporal_noise_sigma": noise_sigma,
        "persistent_spatial_sigma": p_sigma,
        "hot_pixel_count": int(hot.sum()),
        "hot_pixel_fraction": float(hot.mean()),
        "unique_frame_count": unique_frames,
        "duplicate_frame_fraction": duplicate_fraction,
        "stack_constant": stack_constant,
        "stack_quality_passed": not quality_failures,
        "quality_failures": quality_failures,
        "track_candidate_count": candidate_total,
        "stored_track_candidate_count": len(candidates),
        "track_candidate_details_truncated": candidate_total - len(candidates),
        "candidate_component_count": candidate_component_total,
        "candidate_rate_per_frame": candidate_total / frame_count,
        "candidates_per_frame": per_frame,
        "track_candidates": candidates,
        "threshold_crossing_pixel_count": threshold_pixel_total,
        "candidate_pixel_limit_per_frame": frame_pixel_limit,
        "candidate_flood_frame_count": len(flood_frames),
        "candidate_flood_frames": flood_frames,
        "sigma_threshold": float(sigma_threshold),
    }


@dataclass
class I01Result:
    hardware_available: bool
    calibration_passed: bool
    reason: str
    analysis: dict[str, Any] | None
    input_evidence: list[dict[str, Any]]
    wall_seconds: float
    error_code: str | None = None
    capture_metadata: dict[str, Any] | None = field(default=None)


def _failed_result(
    started: float,
    *,
    reason: str,
    error_code: str | None,
    hardware_available: bool = False,
    analysis: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    capture_metadata: dict[str, Any] | None = None,
) -> I01Result:
    return I01Result(
        hardware_available=hardware_available,
        calibration_passed=False,
        reason=reason,
        analysis=analysis,
        input_evidence=evidence or [],
        wall_seconds=time.time() - started,
        error_code=error_code,
        capture_metadata=capture_metadata,
    )


def run_i01(
    frames_path: str | Path | None = None,
    *,
    capture_camera: int | None = None,
    capture_output: str | Path | None = None,
    capture_frames: int = 24,
    capture_timeout_seconds: float = 30.0,
    capture_width: int | None = None,
    capture_height: int | None = None,
    progress: ProgressCallback | None = None,
) -> I01Result:
    """Run I01 from an existing stack or an optionally captured real stack.

    Expected input/acquisition failures are caught and returned as actionable
    receipts.  Direct callers that need exceptions can use ``load_dark_frames``
    or ``capture_dark_frames`` and catch the typed ``I01Error`` subclasses.
    """
    started = time.time()
    capture_result: CaptureResult | None = None
    if frames_path is not None and capture_camera is not None:
        return _failed_result(
            started,
            reason=(
                "Choose one real input source: pass frames_path/--frames or "
                "capture_camera, not both."
            ),
            error_code="conflicting_input_sources",
        )
    if capture_output is not None and capture_camera is None:
        return _failed_result(
            started,
            reason="capture_output requires capture_camera.",
            error_code="capture_camera_required",
        )

    configured = (
        frames_path
        if frames_path is not None
        else (
            None
            if capture_camera is not None
            else os.environ.get("WINDOWSILL_I01_FRAMES")
        )
    )
    if configured is None and capture_camera is None:
        return _failed_result(
            started,
            reason=(
                "No real capped-sensor dark-frame stack was configured. Set "
                "WINDOWSILL_I01_FRAMES or pass --frames; synthetic data is not "
                "accepted as an instrument measurement."
            ),
            error_code="no_real_frames",
        )

    try:
        if capture_camera is not None:
            if capture_output is None:
                raise CaptureOutputError(
                    "live capture needs capture_output so the real .npy stack "
                    "and its evidence remain inspectable"
                )
            capture_result = capture_dark_frames(
                capture_output,
                camera_index=capture_camera,
                frame_count=capture_frames,
                timeout_seconds=capture_timeout_seconds,
                width=capture_width,
                height=capture_height,
                progress=progress,
            )
            configured = capture_result.stack_path

        assert configured is not None
        configured_path = Path(configured)
        hardware_available = configured_path.exists()
        stack, loaded_evidence = load_dark_frames(
            configured_path, progress=progress
        )
        if capture_result is not None:
            if (
                len(capture_result.input_evidence) != 1
                or len(loaded_evidence) != 1
            ):
                raise DarkFrameInputError(
                    "captured stack did not retain exactly one source-evidence record"
                )
            captured_item = capture_result.input_evidence[0]
            loaded_item = loaded_evidence[0]
            if any(
                captured_item.get(field) != loaded_item.get(field)
                for field in ("bytes", "sha256")
            ):
                raise DarkFrameInputError(
                    "captured stack changed between acquisition evidence and "
                    "analysis; the product was not graded"
                )
            try:
                expected_shape = (
                    int(capture_result.metadata.get("frame_count", -1)),
                    int(capture_result.metadata.get("height", -1)),
                    int(capture_result.metadata.get("width", -1)),
                )
            except (TypeError, ValueError) as exc:
                raise DarkFrameInputError(
                    f"capture metadata has invalid frame dimensions: {exc}"
                ) from exc
            if tuple(stack.shape) != expected_shape:
                raise DarkFrameInputError(
                    f"captured stack shape {tuple(stack.shape)} does not match "
                    f"capture metadata {expected_shape}"
                )
            evidence = capture_result.input_evidence
        else:
            evidence = loaded_evidence
        analysis = classify_dark_stack(stack, progress=progress)
    except CaptureError as exc:
        return _failed_result(
            started,
            reason=f"Camera acquisition did not produce a measurement: {exc}",
            error_code=exc.code,
            capture_metadata=(
                capture_result.metadata if capture_result is not None else None
            ),
        )
    except DarkFrameNotFoundError as exc:
        return _failed_result(
            started,
            reason=str(exc),
            error_code=exc.code,
        )
    except DarkFrameInputError as exc:
        return _failed_result(
            started,
            reason=f"Real dark-frame input was rejected: {exc}",
            error_code=exc.code,
            hardware_available=locals().get("hardware_available", False),
            evidence=(
                capture_result.input_evidence
                if capture_result is not None
                else []
            ),
            capture_metadata=(
                capture_result.metadata if capture_result is not None else None
            ),
        )

    enough_frames = stack.shape[0] >= 16
    noise_resolved = analysis["temporal_noise_sigma"] > 0
    quality_passed = bool(analysis["stack_quality_passed"])
    passed = bool(enough_frames and noise_resolved and quality_passed)
    if passed:
        reason = (
            "Dark noise, persistent hot pixels, and transient track-like "
            "components were measured from the real stack."
        )
    else:
        failures = list(analysis["quality_failures"])
        if not enough_frames:
            failures.insert(0, "fewer_than_16_frames")
        reason = (
            "The real stack was measured but failed calibration quality gates: "
            + ", ".join(failures)
            + ". Capture at least 16 distinct, uncropped dark frames with the "
            "sensor stable and retry."
        )
    _emit_progress(
        progress,
        "complete",
        calibration_passed=passed,
        frame_count=int(stack.shape[0]),
    )
    return I01Result(
        hardware_available=True,
        calibration_passed=passed,
        reason=reason,
        analysis=analysis,
        input_evidence=evidence,
        wall_seconds=time.time() - started,
        capture_metadata=(
            capture_result.metadata if capture_result is not None else None
        ),
    )


def to_report(result: I01Result) -> dict[str, Any]:
    headline = (
        f"CMOS dark calibration: {result.analysis['shape'][0]} frames, "
        f"{result.analysis['hot_pixel_count']} hot pixels, "
        f"{result.analysis['track_candidate_count']} track-like candidates"
        if result.analysis
        else "CMOS calibration not run: no usable real dark-frame stack available"
    )
    status = (
        "pass"
        if result.calibration_passed
        else ("fail" if result.hardware_available else "null")
    )
    return {
        "experiment": "I01-cmos-particle-detector-calibration",
        "headline": headline,
        "status": status,
        "hardware_available": result.hardware_available,
        "calibration_passed": result.calibration_passed,
        "reason": result.reason,
        "error_code": result.error_code,
        "analysis": result.analysis,
        "input_evidence": result.input_evidence,
        "capture_metadata": result.capture_metadata,
        "wall_seconds": result.wall_seconds,
        "claim_boundary": (
            "A pass calibrates dark noise and event separation only. Candidate "
            "components are not identified as cosmic rays without exposure "
            "metadata, controls, and a sustained rate/geometry study. Camera "
            "capture metadata records the device output but cannot verify that "
            "the lens was capped. A hardware-null is evidence of no measurement, "
            "not a failure of the classifier."
        ),
    }
