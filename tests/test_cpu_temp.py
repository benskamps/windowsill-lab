"""The season sensor tells the truth or says nothing.

Born from the 2026-08-12 two-producer investigation, axis two: loam's only
``/sys/class/thermal`` zone is the Intel WiFi adapter (``iwlwifi_1``), its
real CPU sensor (``k10temp``, Tctl) lives under ``/sys/class/hwmon`` which
the old reader never opened — so the public feed carried a WiFi reading
labelled "CPU heat". These pin the fix: hwmon is read, and an unnamed zone
is never a fallback.
"""

from pathlib import Path

from lab.publish import _cpu_temp_linux


def _thermal_zone(base: Path, n: int, kind: str, milli: int) -> None:
    zone = base / f"thermal_zone{n}"
    zone.mkdir(parents=True)
    (zone / "type").write_text(kind, encoding="utf-8")
    (zone / "temp").write_text(str(milli), encoding="utf-8")


def _hwmon_chip(base: Path, n: int, name: str, milli: int) -> None:
    chip = base / f"hwmon{n}"
    chip.mkdir(parents=True)
    (chip / "name").write_text(name, encoding="utf-8")
    (chip / "temp1_input").write_text(str(milli), encoding="utf-8")


def test_loam_shape_reads_k10temp_from_hwmon_not_the_wifi_zone(tmp_path):
    """The exact loam layout: iwlwifi is the only thermal zone, k10temp is
    an hwmon chip. The reading must be Tctl, never the WiFi adapter."""
    thermal, hwmon = tmp_path / "thermal", tmp_path / "hwmon"
    _thermal_zone(thermal, 0, "iwlwifi_1", 46000)
    _hwmon_chip(hwmon, 0, "k10temp", 47500)
    assert _cpu_temp_linux(thermal, hwmon) == 47.5


def test_no_cpu_named_sensor_fails_closed(tmp_path):
    """Negative control: a WiFi zone alone yields None — the old
    first-readable-zone fallback published it as CPU heat."""
    thermal, hwmon = tmp_path / "thermal", tmp_path / "hwmon"
    _thermal_zone(thermal, 0, "iwlwifi_1", 46000)
    _hwmon_chip(hwmon, 0, "nvme", 38000)   # named, but not a CPU either
    assert _cpu_temp_linux(thermal, hwmon) is None


def test_cpu_named_thermal_zone_still_wins(tmp_path):
    """The pre-fix happy path is unchanged: an x86_pkg zone is preferred
    and hwmon is not consulted."""
    thermal, hwmon = tmp_path / "thermal", tmp_path / "hwmon"
    _thermal_zone(thermal, 0, "iwlwifi_1", 46000)
    _thermal_zone(thermal, 1, "x86_pkg_temp", 51300)
    _hwmon_chip(hwmon, 0, "k10temp", 47500)
    assert _cpu_temp_linux(thermal, hwmon) == 51.3


def test_missing_roots_yield_none(tmp_path):
    assert _cpu_temp_linux(tmp_path / "no-thermal", tmp_path / "no-hwmon") is None
