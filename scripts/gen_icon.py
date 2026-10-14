#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _cdin.gen_icon import cmd_gen_icon
from _cdin._constants import ICON_SVG


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("svg", nargs="?", metavar="icon.svg",
                   help=f"Source SVG (default: {ICON_SVG})")
    p.add_argument("--out-dir", metavar="DIR",
                   help="Directory for output files (default: same dir as SVG)")
    p.add_argument("--out-ico", metavar="PATH",
                   help="Override output path for the .ico file")
    p.add_argument("--out-inl", metavar="PATH",
                   help="Write a C inline array to PATH (e.g. src/icon.inl)")
    return p.parse_args()


if __name__ == "__main__":
    try:
        args = parse_args()
        if not args.svg:
            args.svg = str(ICON_SVG)
        cmd_gen_icon(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
        sys.exit(130)