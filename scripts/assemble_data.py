#!/usr/bin/env python3
"""Assemble the build output's data/ directory.

The editor resolves its Lua layers from EXEDIR/data, so that directory has
to exist next to the binary and it has to be complete: the runtime's own
core/, plus the mandatory set that only cdin-x has — the vim plugin, the
default theme and the fonts. This script produces exactly that.

Two roots, and they are assembled differently on purpose:

  data/core   a symlink to the source tree, falling back to a copy. The core
              is edited constantly and never needs to be staged, so a link
              is the right shape — but a *stale copy* is the worst possible
              outcome here, because the editor would silently run yesterday's
              core. So the link is recreated on every run rather than
              created-if-missing.

  everything  else is produced by cdin-x's scripts/bundle.py, which copies
              the essential plugins, the essential theme, the fonts and
              writes a BUNDLE.lua index. It is a real copy, not a link, so
              the build output is self-contained and reproducible.

Stdlib only, Python 3.8+, no network. Deliberately does not know what is in
the bundle: naming vim or fonts here would put cdin-x's contents into cdin's
source.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

MISSING_CDIN_X = (
    "cdin needs cdin-x to produce a runnable editor — it provides the mandatory\n"
    "  set: the vim plugin, the extension manager, the default theme and the fonts.\n"
    "\n"
    "  Looked for {path}/scripts/bundle.py and it is not there.\n"
    "\n"
    "  CDINX_DIR is currently {cdinx}, which defaults to a sibling of this\n"
    "  checkout. cdin-x has to sit next to cdin, not inside it: `cdin/cdin-x`\n"
    "  is one directory too deep for `../cdin-x` to find.\n"
    "\n"
    "  Fix it with `make CDINX_DIR=/path/to/cdin-x`, or move the checkout.\n"
    "  `make bin` compiles the binary only and needs no cdin-x."
)


def die(message: str) -> "NoReturn":  # type: ignore[valid-type]
    print("✗ " + message, file=sys.stderr)
    sys.exit(1)


def is_link(path: Path) -> bool:
    """True for a symlink, a junction, or any other reparse point.

    os.path.islink is false for a Windows junction, and a junction is just
    as dangerous: it redirects writes to another tree. Any reparse point is
    treated as a link — unlinked, never traversed.
    """
    if os.path.islink(path):
        return True
    if sys.platform == "win32":
        try:
            st = os.lstat(path)
        except OSError:
            return False
        return bool(getattr(st, "st_file_attributes", 0) & 0x400)
    return False


def remove_tree(path: Path) -> None:
    """Remove a path, whatever it is.

    The link case is the one that matters. os.rmtree on a symlink raises on
    most platforms, and shutil.rmtree("link") on an old Python follows the
    link and deletes the *target's* contents. A build script that destroys
    the source tree because the output directory used to be a link is not a
    thing anyone should have to debug, so the link is unlinked and never
    traversed.
    """
    if not os.path.lexists(path):
        return
    if is_link(path):
        os.unlink(path)
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()


def mirror_core(src_core: Path, dst_core: Path) -> None:
    """Point dst_core at src_core, recreating it every time.

    A link when the platform gives us one, a copy when it does not. The
    important part is that whatever is there now is replaced, not reused: a
    previous build that degraded a link into a copy must not pin the core
    at whatever it contained then.
    """
    remove_tree(dst_core)
    dst_core.parent.mkdir(parents=True, exist_ok=True)

    try:
        os.symlink(src_core, dst_core, target_is_directory=True)
        return
    except (OSError, NotImplementedError, AttributeError):
        # Windows without developer mode, or a filesystem with no symlinks.
        # Correctness over speed: a copy that is refreshed every build is
        # merely slower than a link, and a stale copy is a broken editor.
        pass

    shutil.copytree(src_core, dst_core, symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__"))


def run_bundler(cdinx: Path, out_data: Path) -> None:
    bundler = cdinx / "scripts" / "bundle.py"
    if not bundler.is_file():
        # Name the directory that was actually probed. "cdin needs cdin-x" on
        # its own is a shrug: the usual cause is a cdin-x that is present but
        # one level too deep, and only the resolved path tells you that.
        die(MISSING_CDIN_X.format(path=cdinx, cdinx=cdinx))

    # The same interpreter, so a venv or a py launcher cannot end up bundling
    # with a different Python than the one running this script.
    cmd = [sys.executable, str(bundler), "--out", str(out_data)]
    print("── " + " ".join(cmd))
    try:
        result = subprocess.run(cmd)
    except OSError as exc:
        die("failed to run {}: {}".format(bundler, exc))
    if result.returncode != 0:
        die("cdin-x bundler failed (exit {}); see its output above".format(result.returncode))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assemble the build output's data/ directory.")
    parser.add_argument("--src", default="data", type=Path,
                        help="source data/ directory (default: data)")
    parser.add_argument("--out", required=True, type=Path,
                        help="build output data/ directory to assemble")
    parser.add_argument("--cdinx", required=True, type=Path,
                        help="path to a cdin-x checkout")
    args = parser.parse_args()

    src_core = args.src / "core"
    if not src_core.is_dir():
        die("no core/ under {} — is --src pointing at the source data/ ?".format(args.src))

    out_data = args.out
    # From an older layout this may still be a symlink or junction to the
    # source tree. Unlink it: the output has to be a real directory that the
    # bundler can add to, and following the link would write the bundle into
    # the source checkout.
    if is_link(out_data):
        os.unlink(out_data)
    out_data.mkdir(parents=True, exist_ok=True)

    mirror_core(src_core.resolve(), out_data / "core")
    run_bundler(args.cdinx, out_data)

    print("✓ data/ assembled: core/ + bundle from {}".format(args.cdinx))
    return 0


def _force_utf8_stdio() -> None:
    """Let the status lines print on a Windows console.

    Python defaults stdout to the ANSI code page, which is cp1252 on most
    Western installs and cannot encode the tick below. A build step that
    dies on its own success message is worse than one that prints a box.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


if __name__ == "__main__":
    _force_utf8_stdio()
    sys.exit(main())
