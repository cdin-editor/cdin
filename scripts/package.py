#!/usr/bin/env python3
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
dist = root / "dist"
dist.mkdir(exist_ok=True)
out = dist / "cdin-composition-root-source.zip"
excluded = {".git", ".deps", "build", "build-ci", "build-tests", "dist", "__pycache__"}
with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in root.rglob("*"):
        if not path.is_file() or any(part in excluded for part in path.relative_to(root).parts):
            continue
        archive.write(path, Path("cdin") / path.relative_to(root))
print(out)
