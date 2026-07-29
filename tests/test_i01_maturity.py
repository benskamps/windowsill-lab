"""Maturity regressions for the bounded I01 camera and dark-stack pipeline."""
from __future__ import annotations

import hashlib
import multiprocessing
import time
from pathlib import Path

import numpy as np
import pytest

from lab import checks, cli, i01


def _hanging_capture_worker(connection, request):
    """Pickleable spawn target that models a camera backend stuck in read()."""
    del connection, request
    time.sleep(10)


def _successful_capture_worker(connection, request):
    """Pickleable camera stand-in used only to exercise product/evidence wiring."""
    stack = np.arange(16 * 6 * 8, dtype=np.uint8).reshape(16, 6, 8)
    np.save(request["staging_path"], stack, allow_pickle=False)
    connection.send(
        {
            "type": "result",
            "metadata": {
                "source": "camera",
                "synthetic": False,
                "camera_index": int(request["camera_index"]),
                "frame_count": 16,
                "width": 8,
                "height": 6,
                "dtype": "uint8",
                "backend": "test-double",
                "started_at_utc": "2026-01-01T00:00:00Z",
                "completed_at_utc": "2026-01-01T00:00:01Z",
                "elapsed_seconds": 1.0,
                "dark_conditions_verified": False,
            },
        }
    )
    connection.close()


def _progress_then_hanging_worker(connection, request):
    """Emit one observable event, then model a backend wedged in read()."""
    del request
    connection.send({"type": "progress", "current": 1, "total": 16})
    time.sleep(10)


def _racing_output_worker(connection, request):
    """Create a competing destination after preflight but before publication."""
    captured = np.arange(16 * 6 * 8, dtype=np.uint8).reshape(16, 6, 8)
    competitor = np.full((16, 6, 8), 211, dtype=np.uint8)
    np.save(request["staging_path"], captured, allow_pickle=False)
    np.save(request["output_path"], competitor, allow_pickle=False)
    connection.send(
        {
            "type": "result",
            "metadata": {
                "source": "camera",
                "synthetic": False,
                "camera_index": int(request["camera_index"]),
                "frame_count": 16,
                "width": 8,
                "height": 6,
                "dtype": "uint8",
                "backend": "race-test-double",
                "started_at_utc": "2026-01-01T00:00:00Z",
                "completed_at_utc": "2026-01-01T00:00:01Z",
                "elapsed_seconds": 1.0,
                "dark_conditions_verified": False,
            },
        }
    )
    connection.close()


def _racing_metadata_worker(connection, request):
    """Race only the sidecar; the owned frame product must be cleaned safely."""
    captured = np.arange(16 * 6 * 8, dtype=np.uint8).reshape(16, 6, 8)
    np.save(request["staging_path"], captured, allow_pickle=False)
    output = Path(request["output_path"])
    output.with_suffix(".npy.capture.json").write_text(
        "competitor metadata\n", encoding="utf-8"
    )
    connection.send(
        {
            "type": "result",
            "metadata": {
                "source": "camera",
                "synthetic": False,
                "camera_index": int(request["camera_index"]),
                "frame_count": 16,
                "width": 8,
                "height": 6,
                "dtype": "uint8",
                "backend": "metadata-race-test-double",
                "started_at_utc": "2026-01-01T00:00:00Z",
                "completed_at_utc": "2026-01-01T00:00:01Z",
                "elapsed_seconds": 1.0,
                "dark_conditions_verified": False,
            },
        }
    )
    connection.close()


def _typed_failure_worker(connection, request):
    del request
    connection.send(
        {
            "type": "error",
            "code": "camera_format_changed",
            "message": "camera format changed during capture",
        }
    )
    connection.close()


def _noisy_stack(seed: int = 7, shape=(16, 32, 32)) -> np.ndarray:
    return np.random.default_rng(seed).normal(100, 1, size=shape).astype(np.float32)


def _valid_checker_report() -> dict:
    return {
        "experiment": "I01-cmos-particle-detector-calibration",
        "hardware_available": True,
        "analysis": {
            "shape": [16, 24, 24],
            "temporal_noise_sigma": 1.25,
            "unique_frame_count": 16,
            "candidate_flood_frame_count": 0,
            "hot_pixel_count": 2,
            "track_candidate_count": 1,
            "stack_quality_passed": True,
            "stack_constant": False,
            "quality_failures": [],
        },
        "input_evidence": [{"sha256": "a" * 64, "synthetic": False}],
    }


def test_zero_stack_preserves_raw_noise_and_fails_calibration(tmp_path):
    path = tmp_path / "zero-dark.npy"
    np.save(path, np.zeros((16, 12, 12), dtype=np.uint16))

    result = i01.run_i01(path)

    assert result.hardware_available
    assert not result.calibration_passed
    assert result.analysis is not None
    assert result.analysis["temporal_noise_sigma"] == 0
    assert "constant_stack" in result.analysis["quality_failures"]
    assert "temporal_noise_unresolved" in result.analysis["quality_failures"]
    assert i01.to_report(result)["status"] == "fail"
    ok, detail = checks.check_i01(i01.to_report(result))
    assert ok is False
    assert "constant_stack" in detail


def test_repeated_nonconstant_frame_fails_unique_frame_gate(tmp_path):
    rng = np.random.default_rng(3)
    one_frame = rng.integers(0, 256, size=(10, 10), dtype=np.uint8)
    path = tmp_path / "repeated.npy"
    np.save(path, np.repeat(one_frame[None, :, :], 16, axis=0))

    result = i01.run_i01(path)

    assert not result.calibration_passed
    assert result.analysis["unique_frame_count"] == 1
    assert result.analysis["duplicate_frame_fraction"] == pytest.approx(15 / 16)
    assert "insufficient_unique_frames" in result.analysis["quality_failures"]
    assert result.analysis["temporal_noise_sigma"] == 0


def test_contaminated_frame_skips_python_components_and_details_stay_bounded(
    monkeypatch,
):
    stack = _noisy_stack(shape=(16, 40, 40))
    # A localized exposure cannot be removed by the per-frame scalar baseline.
    stack[4, 5:25, 5:25] += 100
    original_iter = i01._iter_components

    def guarded_components(mask):
        # If the flood gate regresses this assertion fires before flood-fill.
        assert np.count_nonzero(mask) <= 30
        yield from original_iter(mask)

    monkeypatch.setattr(i01, "_iter_components", guarded_components)
    analysis = i01.classify_dark_stack(
        stack,
        max_candidate_pixels_per_frame=30,
        max_candidate_fraction=1.0,
        max_stored_candidates=2,
    )

    assert analysis["candidate_flood_frame_count"] == 1
    assert analysis["candidate_flood_frames"][0]["frame"] == 4
    assert analysis["threshold_crossing_pixel_count"] >= 400
    assert len(analysis["track_candidates"]) <= 2
    assert "candidate_flood_frames" in analysis["quality_failures"]


def test_candidate_detail_cap_retains_total_count():
    stack = _noisy_stack(seed=11, shape=(16, 64, 64))
    # Ten separated, three-pixel line components in a single exposure.
    for index in range(10):
        row = 3 + index * 5
        stack[7, row, 5:8] += 40

    analysis = i01.classify_dark_stack(
        stack,
        max_candidate_pixels_per_frame=1_000,
        max_candidate_fraction=1.0,
        max_stored_candidates=2,
    )

    assert analysis["track_candidate_count"] >= 10
    assert analysis["stored_track_candidate_count"] == 2
    assert analysis["track_candidate_details_truncated"] == (
        analysis["track_candidate_count"] - 2
    )


def test_npz_with_multiple_arrays_is_rejected_as_ambiguous(tmp_path):
    path = tmp_path / "ambiguous.npz"
    np.savez(path, first=_noisy_stack(), second=_noisy_stack(seed=9))

    with pytest.raises(i01.DarkFrameInputError, match="exactly one"):
        i01.load_dark_frames(path)


def test_single_array_npz_is_preflighted_and_loaded_as_float32(tmp_path):
    path = tmp_path / "single.npz"
    source = _noisy_stack().astype(np.float64)
    np.savez_compressed(path, dark=source)

    loaded, evidence = i01.load_dark_frames(path)

    assert loaded.shape == source.shape
    assert loaded.dtype == np.float32
    assert np.allclose(loaded, source)
    assert len(evidence[0]["sha256"]) == 64


def test_directory_rejects_mismatched_frames_before_stack(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    np.save(frames / "001.npy", np.zeros((8, 8), dtype=np.uint8))
    np.save(frames / "002.npy", np.zeros((9, 8), dtype=np.uint8))

    with pytest.raises(i01.DarkFrameInputError, match="do not match"):
        i01.load_dark_frames(frames)


def test_hashing_streams_instead_of_using_path_read_bytes(tmp_path, monkeypatch):
    path = tmp_path / "streamed.npy"
    np.save(path, _noisy_stack())

    def forbid_read_bytes(self):
        raise AssertionError(f"read_bytes loaded the whole file: {self}")

    monkeypatch.setattr(Path, "read_bytes", forbid_read_bytes)
    _stack, evidence = i01.load_dark_frames(path)

    expected = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(257):
            expected.update(chunk)
    assert evidence[0]["sha256"] == expected.hexdigest()
    assert evidence[0]["bytes"] == path.stat().st_size


def test_float32_npy_load_is_an_owned_snapshot_not_a_live_memmap(tmp_path):
    path = tmp_path / "snapshot.npy"
    np.save(path, np.ones((8, 4, 4), dtype=np.float32))

    loaded, evidence = i01.load_dark_frames(path)
    writer = np.load(path, allow_pickle=False, mmap_mode="r+")
    writer[:] = 7
    writer.flush()
    del writer

    assert loaded.flags.owndata
    assert float(loaded.mean()) == 1.0
    assert evidence[0]["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest()
    # In particular, keeping the analyzed pixels alive no longer locks the
    # source against replacement on Windows.
    np.save(path, np.full((8, 4, 4), 9, dtype=np.float32))
    assert float(loaded.mean()) == 1.0


def test_file_change_between_load_and_hash_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "changing.npy"
    np.save(path, np.ones((8, 4, 4), dtype=np.uint8))
    original_evidence = i01._file_evidence

    def replace_before_hash(evidence_path, **kwargs):
        np.save(evidence_path, np.full((8, 4, 4), 9, dtype=np.float32))
        return original_evidence(evidence_path, **kwargs)

    monkeypatch.setattr(i01, "_file_evidence", replace_before_hash)
    with pytest.raises(i01.DarkFrameInputError, match="changed between"):
        i01.load_dark_frames(path)


def test_work_size_gate_runs_before_float32_conversion(monkeypatch):
    stack = np.broadcast_to(np.uint8(1), (8, 4, 4))
    monkeypatch.setattr(i01, "MAX_STACK_PIXELS", 100)

    with pytest.raises(i01.DarkFrameInputError, match="safety limit"):
        i01.classify_dark_stack(stack)


def test_work_size_gate_counts_retained_float64_input(monkeypatch):
    stack = np.ones((8, 4, 4), dtype=np.float64)
    pixels = int(stack.size)
    baseline_estimate = pixels * 16 + 4 * 4 * 16
    monkeypatch.setattr(
        i01,
        "MAX_ANALYSIS_WORK_BYTES",
        baseline_estimate + stack.nbytes - 1,
    )

    with pytest.raises(i01.DarkFrameInputError, match="analysis workspace"):
        i01.classify_dark_stack(stack)


def test_capture_timeout_terminates_stuck_backend_and_leaves_no_product(tmp_path):
    output = tmp_path / "camera.npy"
    started = time.monotonic()

    with pytest.raises(i01.CaptureTimeoutError, match="terminated"):
        i01.capture_dark_frames(
            output,
            frame_count=16,
            timeout_seconds=0.15,
            _worker=_hanging_capture_worker,
        )

    assert time.monotonic() - started < 3
    assert not output.exists()
    assert not output.with_suffix(".npy.capture.json").exists()


def test_progress_callback_failure_cannot_strand_camera_child(tmp_path):
    output = tmp_path / "callback.npy"
    started = time.monotonic()

    def broken_observer(event):
        if event["stage"] == "capture":
            raise RuntimeError("observer disconnected")

    with pytest.raises(RuntimeError, match="observer disconnected"):
        i01.capture_dark_frames(
            output,
            frame_count=16,
            timeout_seconds=5,
            progress=broken_observer,
            _worker=_progress_then_hanging_worker,
        )

    assert time.monotonic() - started < 3
    assert not output.exists()
    assert not output.with_suffix(".npy.capture.json").exists()
    assert not list(tmp_path.glob(".*.capture.npy"))
    assert not any(
        child.name == "windowsill-i01-camera"
        for child in multiprocessing.active_children()
    )


def test_capture_reports_actionable_missing_optional_cv2(tmp_path, monkeypatch):
    monkeypatch.setattr(i01, "_cv2_available", lambda: False)

    with pytest.raises(i01.CaptureUnavailableError, match=r"\[camera\]"):
        i01.capture_dark_frames(tmp_path / "camera.npy")


def test_capture_saves_grayscale_stack_metadata_hash_and_progress(tmp_path):
    output = tmp_path / "camera.npy"
    events = []

    result = i01.capture_dark_frames(
        output,
        frame_count=16,
        timeout_seconds=5,
        progress=events.append,
        _worker=_successful_capture_worker,
    )

    saved = np.load(output, allow_pickle=False)
    assert saved.shape == (16, 6, 8)
    assert saved.ndim == 3
    assert result.metadata["source"] == "camera"
    assert result.metadata["synthetic"] is False
    assert result.metadata["camera_index"] == 0
    assert result.metadata["frame_count"] == 16
    assert result.metadata["width"] == 8
    assert result.metadata["height"] == 6
    assert result.metadata["dtype"] == "uint8"
    assert result.metadata["output_path"] == str(output.resolve())
    assert len(result.metadata["sha256"]) == 64
    assert result.metadata_path.is_file()
    assert result.input_evidence[0]["sha256"] == result.metadata["sha256"]
    assert [event["stage"] for event in events] == [
        "capture_start",
        "capture_complete",
    ]


def test_capture_never_overwrites_or_deletes_racing_output(tmp_path):
    output = tmp_path / "racing.npy"

    with pytest.raises(i01.CaptureOutputError, match="refusing to overwrite"):
        i01.capture_dark_frames(
            output,
            frame_count=16,
            timeout_seconds=5,
            _worker=_racing_output_worker,
        )

    assert np.all(np.load(output, allow_pickle=False) == 211)
    assert not output.with_suffix(".npy.capture.json").exists()
    assert not list(tmp_path.glob(".*.capture.npy"))


def test_capture_never_overwrites_racing_metadata_and_removes_only_owned_output(
    tmp_path,
):
    output = tmp_path / "metadata-race.npy"
    metadata = output.with_suffix(".npy.capture.json")

    with pytest.raises(i01.CaptureOutputError, match="refusing to overwrite"):
        i01.capture_dark_frames(
            output,
            frame_count=16,
            timeout_seconds=5,
            _worker=_racing_metadata_worker,
        )

    assert not output.exists()
    assert metadata.read_text(encoding="utf-8") == "competitor metadata\n"


def test_worker_error_preserves_specific_machine_readable_code(tmp_path):
    with pytest.raises(i01.CaptureError) as captured:
        i01.capture_dark_frames(
            tmp_path / "failure.npy",
            frame_count=16,
            timeout_seconds=5,
            _worker=_typed_failure_worker,
        )

    assert captured.value.code == "camera_format_changed"


def test_run_rejects_capture_changed_after_its_evidence_hash(tmp_path, monkeypatch):
    output = tmp_path / "changed-after-capture.npy"

    def changed_capture(output_path, **_kwargs):
        product = Path(output_path)
        original = _noisy_stack()
        np.save(product, original)
        evidence = i01._file_evidence(
            product,
            source="camera",
            synthetic=False,
        )
        metadata = {
            "source": "camera",
            "synthetic": False,
            "camera_index": 0,
            "frame_count": 16,
            "width": 32,
            "height": 32,
            "dtype": "float32",
            "elapsed_seconds": 1.0,
            "dark_conditions_verified": False,
        }
        result = i01.CaptureResult(
            stack_path=product,
            metadata_path=product.with_suffix(".npy.capture.json"),
            metadata=metadata,
            input_evidence=[evidence],
        )
        np.save(product, original + 5)
        return result

    monkeypatch.setattr(i01, "capture_dark_frames", changed_capture)
    result = i01.run_i01(
        capture_camera=0,
        capture_output=output,
    )

    assert result.hardware_available
    assert not result.calibration_passed
    assert result.error_code == "invalid_dark_frames"
    assert "changed between acquisition evidence and analysis" in result.reason


def test_run_accepts_capture_when_reloaded_hash_and_metadata_match(
    tmp_path,
    monkeypatch,
):
    output = tmp_path / "stable-capture.npy"

    def stable_capture(output_path, **_kwargs):
        product = Path(output_path)
        np.save(product, _noisy_stack())
        evidence = i01._file_evidence(
            product,
            source="camera",
            synthetic=False,
        )
        metadata = {
            "source": "camera",
            "synthetic": False,
            "camera_index": 0,
            "frame_count": 16,
            "width": 32,
            "height": 32,
            "dtype": "float32",
            "elapsed_seconds": 1.0,
            "dark_conditions_verified": False,
        }
        return i01.CaptureResult(
            stack_path=product,
            metadata_path=product.with_suffix(".npy.capture.json"),
            metadata=metadata,
            input_evidence=[evidence],
        )

    monkeypatch.setattr(i01, "capture_dark_frames", stable_capture)
    result = i01.run_i01(
        capture_camera=0,
        capture_output=output,
    )

    assert result.hardware_available
    assert result.calibration_passed
    assert result.input_evidence[0]["sha256"] == hashlib.sha256(
        output.read_bytes()
    ).hexdigest()


def test_load_and_analysis_expose_progress_seams(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    stack = _noisy_stack(shape=(8, 12, 12))
    for index, frame in enumerate(stack):
        np.save(frames / f"{index:03d}.npy", frame)
    events = []

    loaded, _evidence = i01.load_dark_frames(frames, progress=events.append)
    i01.classify_dark_stack(loaded, progress=events.append)

    stages = [event["stage"] for event in events]
    assert stages.count("load") == 8
    assert stages.count("analysis_frame") == 8
    assert "preflight" in stages
    assert "analysis_baseline" in stages


def test_i01_cli_parses_bounded_camera_controls():
    ns = cli._parse_i01([
        "--camera", "2",
        "--capture-frames", "32",
        "--capture-timeout", "4.5",
        "--capture-width", "640",
        "--capture-height", "480",
    ])
    assert ns.camera == 2
    assert ns.capture_frames == 32
    assert ns.capture_timeout == 4.5
    assert ns.capture_width == 640
    assert ns.capture_height == 480


def test_runner_and_checker_share_the_positive_quality_gate(tmp_path):
    path = tmp_path / "real-noisy-stack.npy"
    np.save(path, _noisy_stack(shape=(16, 24, 24)))
    report = i01.to_report(i01.run_i01(path))
    ok, detail = checks.check_i01(report)
    assert report["calibration_passed"] is True
    assert ok is True
    assert "operational" in detail


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("shape", ["sixteen", 24, 24]),
        ("temporal_noise_sigma", "not-a-number"),
        ("unique_frame_count", []),
        ("candidate_flood_frame_count", "none"),
        ("hot_pixel_count", float("inf")),
        ("track_candidate_count", 1.5),
    ],
)
def test_checker_fails_closed_on_malformed_numeric_receipt_fields(field, value):
    report = _valid_checker_report()
    report["analysis"][field] = value

    ok, detail = checks.check_i01(report)

    assert ok is False
    assert "malformed numeric receipt" in detail
