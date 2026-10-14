#!/usr/bin/env python3
"""
Usage (flags):
    python3 scripts/cdin.py build [--debug] [--jobs N] [--prefix DIR]
    python3 scripts/cdin.py install [--prefix DIR] [--binary PATH] [--shortcut] [--register-filetypes]
    python3 scripts/cdin.py build-install [--debug] [--prefix DIR] [--shortcut]
    python3 scripts/cdin.py update [--check] [--force] [--version X.Y.Z]
    python3 scripts/cdin.py uninstall [--prefix DIR]
    python3 scripts/cdin.py gen-icon [<icon.svg>] [--out-dir DIR] [--out-ico PATH] [--out-inl PATH]
    python3 scripts/cdin.py gen-logo [<icon.svg>] [--grid N] [--out PATH]
    python3 scripts/cdin.py --help
"""

from __future__ import annotations

import argparse
import sys
import textwrap

from _cdin.build         import cmd_build
from _cdin.build_install import cmd_build_install
from _cdin.gen_icon      import cmd_gen_icon
from _cdin.gen_logo      import cmd_gen_logo
from _cdin.install       import cmd_install
from _cdin.interactive   import interactive
from _cdin.platform      import default_prefix
from _cdin.uninstall     import cmd_uninstall
from _cdin.update        import cmd_update


DISPATCH = {
    "build":         cmd_build,
    "install":       cmd_install,
    "build-install": cmd_build_install,
    "update":        cmd_update,
    "uninstall":     cmd_uninstall,
    "gen-icon":      cmd_gen_icon,
    "gen-logo":      cmd_gen_logo,
}


# ─────────────────────────── CLI parser ───────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cdin.py",
        description="cdin build / install / update / asset tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python3 scripts/cdin.py                          # interactive mode
              python3 scripts/cdin.py build                    # release build
              python3 scripts/cdin.py build --debug --jobs 8
              python3 scripts/cdin.py install --shortcut
              python3 scripts/cdin.py build-install            # build + install
              python3 scripts/cdin.py update                   # update to latest
              python3 scripts/cdin.py update --check           # check only
              python3 scripts/cdin.py update --version 0.2.0
              python3 scripts/cdin.py uninstall
              python3 scripts/cdin.py gen-icon                 # regenerate icons from scripts/icon.svg
              python3 scripts/cdin.py gen-icon path/to/icon.svg --out-dir build/icons
              python3 scripts/cdin.py gen-logo                 # regenerate data/core/rootview/logo.lua
              python3 scripts/cdin.py gen-logo --grid 128 --out /tmp/logo.lua
        """),
    )
    sub = p.add_subparsers(dest="command")

    # build
    b = sub.add_parser("build", help="Build cdin from source")
    b.add_argument("--debug",   action="store_true", help="Debug build (default: release)")
    b.add_argument("--release", action="store_true", help="Release build (default)")
    b.add_argument("--jobs", "-j", type=int, metavar="N", help="Parallel jobs (default: CPU count)")
    b.add_argument("--prefix", metavar="DIR", help="Installation prefix for Makefile variables")

    # install
    i = sub.add_parser("install", help="Install an already-built binary")
    i.add_argument("--prefix",   metavar="DIR", help=f"Install prefix (default: {default_prefix()})")
    i.add_argument("--binary",   metavar="PATH", help="Path to cdin binary (auto-detected if omitted)")
    i.add_argument("--shortcut", action="store_true",
                   help="Create desktop shortcut / .app / .desktop entry")
    i.add_argument("--register-filetypes", action="store_true",
                   help="(Windows) Register file-type associations")

    # build-install
    bi = sub.add_parser("build-install", help="Build from source, then install")
    bi.add_argument("--debug",   action="store_true")
    bi.add_argument("--release", action="store_true")
    bi.add_argument("--jobs", "-j", type=int, metavar="N")
    bi.add_argument("--prefix",  metavar="DIR")
    bi.add_argument("--shortcut", action="store_true")
    bi.add_argument("--register-filetypes", action="store_true")

    # update
    u = sub.add_parser("update", help="Update cdin to the latest release from GitHub")
    u.add_argument("--check",  action="store_true", help="Only check — do not install")
    u.add_argument("--force", "-f", action="store_true", help="Skip confirmation prompt")
    u.add_argument("--version", metavar="X.Y.Z", help="Install a specific version")

    # uninstall
    un = sub.add_parser("uninstall", help="Remove a cdin installation")
    un.add_argument("--prefix", metavar="DIR")

    # gen-icon
    gi = sub.add_parser("gen-icon", help="Generate .ico / .icns / .png icons from an SVG")
    gi.add_argument("svg", nargs="?", metavar="icon.svg",
                    help="Source SVG (default: scripts/icon.svg)")
    gi.add_argument("--out-dir", metavar="DIR",
                    help="Directory for output files (default: same dir as SVG)")
    gi.add_argument("--out-ico", metavar="PATH",
                    help="Path for the .ico file (overrides --out-dir for .ico)")
    gi.add_argument("--out-inl", metavar="PATH",
                    help="Write a C inline array to PATH (e.g. src/icon.inl)")

    # gen-logo
    gl = sub.add_parser("gen-logo", help="Rasterize SVG into logo.lua span data")
    gl.add_argument("svg", nargs="?", metavar="icon.svg",
                    help="Source SVG (default: scripts/icon.svg)")
    gl.add_argument("--grid", type=int, default=64, metavar="N",
                    help="Rasterize at N×N pixels (default: 64)")
    gl.add_argument("--out", metavar="PATH",
                    help="Output path (default: data/core/rootview/logo.lua)")

    return p


# ─────────────────────────── entry point ──────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    if args.command is None:
        interactive()
        return

    DISPATCH[args.command](args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
        sys.exit(130)