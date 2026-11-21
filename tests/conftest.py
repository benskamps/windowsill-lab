"""Suite-wide isolation from the committed receipts ledger.

``cli._unchanged_runs`` (the planner-v3 rerun gate) reads the REAL committed
receipts. A test that stubs one runner and points ``lab next`` at it would see
that mid skipped as "unchanged since its last run" because of a receipt the
test never wrote, and the planner would then dispatch a different, UNSTUBBED
runner for real. That happened while the gate was being written (2026-11-04):
the lock test ran A07 and A02 for real and wrote into the live ``~/.lab``.

So the gate is pinned off for every test here, the same way ``_hunt_status``
is pinned per file. tests/test_rerun_gate.py calls ``lab.rerun_gate`` directly
and re-patches ``cli._unchanged_runs`` where it tests the CLI seam.

A private ``MonkeyPatch``, not the ``monkeypatch`` fixture: requesting the
shared fixture from a suite-wide autouse fixture sets it up FIRST, so it is
torn down LAST, after every file-level fixture. test_origin.py's cache-clearing
fixture then tore down while its test's ``origin.slug`` patch was still in
place and called ``cache_clear`` on the stub lambda.
"""
import pytest


@pytest.fixture(autouse=True)
def _rerun_gate_reads_no_real_receipts():
    import lab.cli as cli
    patch = pytest.MonkeyPatch()
    patch.setattr(cli, "_unchanged_runs", lambda: {})
    yield
    patch.undo()
