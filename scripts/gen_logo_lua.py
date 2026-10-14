#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _cdin.gen_logo import cmd_gen_logo, DEFAULT_GRID
from _cdin._constants import ICON_SVG


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("svg", nargs="?", metavar="icon.svg",
                   help=f"Source SVG (default: {ICON_SVG})")
    p.add_argument("--grid", type=int, default=DEFAULT_GRID, metavar="N",
                   help=f"Rasterize at N×N pixels (default: {DEFAULT_GRID})")
    p.add_argument("--out", metavar="PATH",
                   help="Output path (default: data/core/rootview/logo.lua)")
    return p.parse_args()


if __name__ == "__main__":
    try:
        args = parse_args()
        if not args.svg:
            args.svg = str(ICON_SVG)
        cmd_gen_logo(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
        sys.exit(130)