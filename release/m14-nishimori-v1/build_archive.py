"""Build the M14 release manifest and deterministic portable ZIP.

The archive uses stored entries, sorted POSIX names, a fixed DOS epoch, empty
metadata fields, and explicit Unix 0644 modes. Those choices make the bytes
stable across operating systems and independent of zlib versions.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path


RELEASE_ID = "m14-nishimori-v1"
ROOT = Path(__file__).resolve().parent
MANIFEST_NAME = "manifest.json"
ARCHIVE_NAME = f"{RELEASE_ID}.zip"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
VERIFY_COMMAND = "python verify_release.py receipt.json --strict"


def _runtime_noise(relative: Path) -> bool:
    return "__pycache__" in relative.parts or relative.suffix in {".pyc", ".pyo"}


def payload_paths(root: Path = ROOT) -> list[Path]:
    """Return the sorted, manifest-covered loose payload."""
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.as_posix() in {MANIFEST_NAME, ARCHIVE_NAME} or _runtime_noise(relative):
            continue
        paths.append(relative)
    return sorted(paths, key=lambda item: item.as_posix())


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_document(root: Path = ROOT) -> dict:
    files = []
    for relative in payload_paths(root):
        data = (root / relative).read_bytes()
        files.append({
            "path": relative.as_posix(),
            "bytes": len(data),
            "sha256": _sha256(data),
        })
    return {
        "schema_version": "windowsill.release-manifest.v1",
        "release_id": RELEASE_ID,
        "files": files,
        "excluded_from_file_table": {
            MANIFEST_NAME: "Self-hashing would be circular.",
            ARCHIVE_NAME: "The archive cannot contain or hash itself; verify its extracted payload with this manifest.",
        },
        "verify_command": VERIFY_COMMAND,
        "archive": {
            "path": ARCHIVE_NAME,
            "root_directory": RELEASE_ID,
            "entry_order": "lexicographic_posix_path",
            "entry_timestamp": "1980-01-01T00:00:00",
            "entry_mode": "0644",
            "compression": "stored"
        }
    }


def manifest_bytes(root: Path = ROOT) -> bytes:
    rendered = json.dumps(manifest_document(root), ensure_ascii=False, indent=2)
    return (rendered + "\n").encode("utf-8")


def archive_bytes(root: Path = ROOT, rendered_manifest: bytes | None = None) -> bytes:
    if rendered_manifest is None:
        rendered_manifest = manifest_bytes(root)
    entries = [(relative.as_posix(), (root / relative).read_bytes()) for relative in payload_paths(root)]
    entries.append((MANIFEST_NAME, rendered_manifest))
    entries.sort(key=lambda item: item[0])

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for relative_name, data in entries:
            info = zipfile.ZipInfo(f"{RELEASE_ID}/{relative_name}", FIXED_ZIP_TIME)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.extra = b""
            info.comment = b""
            archive.writestr(info, data)
        archive.comment = b""
    return buffer.getvalue()


def write_release(root: Path = ROOT) -> tuple[Path, Path]:
    rendered_manifest = manifest_bytes(root)
    manifest_path = root / MANIFEST_NAME
    archive_path = root / ARCHIVE_NAME
    manifest_path.write_bytes(rendered_manifest)
    archive_path.write_bytes(archive_bytes(root, rendered_manifest))
    return manifest_path, archive_path


def check_release(root: Path = ROOT) -> None:
    expected_manifest = manifest_bytes(root)
    manifest_path = root / MANIFEST_NAME
    archive_path = root / ARCHIVE_NAME
    if not manifest_path.is_file() or manifest_path.read_bytes() != expected_manifest:
        raise ValueError("manifest.json is missing or stale; run python build_archive.py")
    expected_archive = archive_bytes(root, expected_manifest)
    if not archive_path.is_file() or archive_path.read_bytes() != expected_archive:
        raise ValueError(f"{ARCHIVE_NAME} is missing or not the deterministic rebuild")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the deterministic M14 verification archive")
    parser.add_argument("--check", action="store_true", help="fail unless checked-in outputs are current")
    args = parser.parse_args()
    try:
        if args.check:
            check_release()
            archive_path = ROOT / ARCHIVE_NAME
            print(f"PASS - deterministic release matches ({_sha256(archive_path.read_bytes())})")
        else:
            manifest_path, archive_path = write_release()
            print(f"wrote {manifest_path.name}")
            print(f"wrote {archive_path.name} ({len(archive_path.read_bytes())} bytes, sha256={_sha256(archive_path.read_bytes())})")
    except Exception as exc:
        print(f"FAIL - {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
