"""Create a byte-for-byte reproducible source snapshot for review and CI.

The archive is a source snapshot, not an application installer or release binary.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
OUTPUT = DIST / "cdin-composition-root-source.zip"
EXCLUDED_PARTS = {
    ".git",
    ".deps",
    "build",
    "build-ci",
    "build-tests",
    "dist",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".pytest_cache",
}


def build_archive(root: Path) -> bytes:
    """Build a stable ZIP: sorted names, fixed timestamps/modes and no symlinks."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        files = sorted(
            root.rglob("*"),
            key=lambda item: item.relative_to(root).as_posix(),
        )
        for path in files:
            relative = path.relative_to(root)
            if any(part in EXCLUDED_PARTS for part in relative.parts):
                continue

            try:
                mode = path.lstat().st_mode
            except OSError as exc:
                raise RuntimeError(f"cannot inspect source path {relative}: {exc}") from exc

            # Do not follow symlinks: a source snapshot must never pull bytes
            # from outside the repository tree.
            if not stat.S_ISREG(mode):
                continue

            name = (PurePosixPath("cdin") / PurePosixPath(relative.as_posix())).as_posix()
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_STORED
            info.extra = b""
            info.comment = b""
            archive.writestr(info, path.read_bytes())

    return buffer.getvalue()


def verify_archive(payload: bytes) -> None:
    """Validate CRCs, unique paths and safe archive member names."""
    with zipfile.ZipFile(BytesIO(payload), "r") as archive:
        names = archive.namelist()
        if not names:
            raise RuntimeError("source snapshot is empty")
        if len(names) != len(set(names)):
            raise RuntimeError("source snapshot contains duplicate paths")
        for name in names:
            member = PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts or not member.parts or member.parts[0] != "cdin":
                raise RuntimeError(f"unsafe source snapshot path: {name!r}")
        corrupt = archive.testzip()
        if corrupt is not None:
            raise RuntimeError(f"source snapshot CRC check failed for {corrupt}")


def main() -> int:
    DIST.mkdir(parents=True, exist_ok=True)

    first = build_archive(ROOT)
    second = build_archive(ROOT)
    if first != second:
        raise RuntimeError("source snapshot is not reproducible: repeated builds differ")
    verify_archive(first)

    temporary = OUTPUT.with_name(OUTPUT.name + ".tmp")
    temporary.write_bytes(first)
    temporary.replace(OUTPUT)

    digest = sha256(first).hexdigest()
    checksum_path = OUTPUT.with_suffix(OUTPUT.suffix + ".sha256")
    checksum_path.write_bytes(f"{digest}  {OUTPUT.name}\n".encode("ascii"))

    print(f"Created: {OUTPUT}")
    print(f"SHA-256: {digest}")
    print("Reproducibility: verified (two independent archive builds match)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
