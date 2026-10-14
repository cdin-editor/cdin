#!/usr/bin/env python3
"""Static checks: compiler warnings, cppcheck, luacheck.

Phase 0 makes this real. It existed as a target calling a file that was not
there, so `make check` failed with "can't open file" and nothing was ever
checked.

Design notes, because a check tool that lies is worse than none:

  * Every check that cannot run here prints SKIPPED with the reason and exits
    0 for that check. A report must be able to say "NOT RUN, because X" without
    a missing tool looking identical to a clean pass.
  * Warning counts are compared against a checked-in baseline, not against
    zero. `-Wconversion` is in the project's required warning set but the
    existing sources are far from clean under it, so failing the build on it
    would mean rewriting the runtime inside a phase whose job is a safety net.
    The baseline records what exists; the gate is "no new warnings".
  * A finding at ERROR severity fails. A finding at warning severity is counted
    and reported; the gate for those is also the baseline.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = ROOT / "tests" / "check_baseline.json"

# Warnings the project requires for new code (AGENTS.md §6). `-Wconversion` is
# excluded from the product build here and explained in the module docstring.
PRODUCT_WARNINGS = [
    "-Wall",
    "-Wextra",
    "-Wshadow",
    "-Wstrict-prototypes",
    "-Wformat=2",
]
EXTRA_SNIPPET_WARNINGS = ["-Wshadow", "-Wstrict-prototypes", "-Wformat=2"]

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
    GREEN = RED = YELLOW = DIM = RESET = ""

# The console on Windows is cp1252 by default and cannot encode the box-drawing
# and arrow characters the other tools in this repo print. Reconfigure stdout
# rather than transliterate: the output is read by people, and an ASCII fallback
# that only appears on one platform is worse than UTF-8 everywhere.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def head(text):
    print(f"\n{DIM}── {text} ──{RESET}")


def ok(text):
    print(f"   {GREEN}ok{RESET}    {text}")


def bad(text):
    print(f"   {RED}FAIL{RESET}  {text}")


def warn(text):
    print(f"   {YELLOW}warn{RESET}  {text}")


def skip(text):
    print(f"   {DIM}skip{RESET}  {text}")


def load_baseline():
    if not BASELINE_PATH.exists():
        return {}
    try:
        with open(BASELINE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        print(f"{DIM}(baseline unreadable: {exc}){RESET}")
        return {}


def c_sources():
    return sorted(
        str(p.relative_to(ROOT)).replace("\\", "/")
        for p in (ROOT / "src").rglob("*.c")
    )


def compiler_available(cc):
    return shutil.which(cc) is not None


def cc_name():
    """The compiler make would use. make/cc.mk resolves it; here the same
    order, so the warnings counted here are the warnings the build produces."""
    if os.environ.get("CC"):
        return os.environ["CC"]
    return "cc"


def include_flags():
    """Include paths the sources need. pkg-config when it can answer, the
    plain system include path otherwise — enough for a syntax-only pass."""
    flags = ["-Isrc"]
    if shutil.which("pkg-config"):
        for pkg in ("sdl3", "sdl2", "lua", "lua5.4"):
            probe = subprocess.run(
                ["pkg-config", "--exists", pkg],
                capture_output=True,
            )
            if probe.returncode == 0:
                out = subprocess.run(
                    ["pkg-config", "--cflags", pkg],
                    capture_output=True, text=True,
                )
                flags.extend(out.stdout.split())
                break
    return flags


def check_compiler(cc):
    head(f"compiler warnings ({cc})")
    if not compiler_available(cc):
        skip(f"{cc} not found — nothing to compile with")
        return True

    sources = c_sources()
    if not sources:
        bad("no sources under src/ — the file list is wrong")
        return False

    base = [
        "-std=gnu11", "-fsyntax-only",
        "-Wno-unused-parameter",
        "-Wno-conversion",
    ] + PRODUCT_WARNINGS + include_flags()

    cmd = [cc] + base + sources
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)

    # Group gcc/clang diagnostics by file:warning-class.
    diag_re = re.compile(r"^(.+?):(\d+):(\d+):\s+(warning|error):\s+(.*)$")
    counts = {}
    total = 0
    for line in proc.stderr.splitlines():
        m = diag_re.match(line.strip())
        if not m:
            continue
        path, _ln, _col, kind, text = m.groups()
        # The warning class is the bracketed tag gcc appends, e.g. [-Wshadow].
        tag = re.search(r"\[(-W[a-z0-9-]+)\]", text)
        key = "%s|%s" % (path.replace("\\", "/"), tag.group(1) if tag else kind)
        counts[key] = counts.get(key, 0) + 1
        total += 1

    baseline = load_baseline().get("compiler", {})
    regressions = []
    for key, count in sorted(counts.items()):
        path, wclass = key.split("|", 1)
        was = baseline.get(key, 0)
        if count > was:
            regressions.append((path, wclass, was, count))
        mark = f"{path} [{wclass}]"
        if count > was:
            bad(f"{mark}: {count} (baseline {was}) — {count - was} new")
        else:
            ok(f"{mark}: {count} (baseline {was})")

    if not counts:
        ok("no warnings")

    # `error:` means the sources do not compile at all, which is not a warning
    # count question.
    errors = sum(v for k, v in counts.items() if k.endswith("|error"))
    if errors:
        bad(f"{errors} compile errors — the baseline is meaningless")
        return False

    if regressions:
        bad(f"{len(regressions)} warning group(s) above baseline — "
            f"new warnings are not allowed (AGENTS.md §6)")
        return False

    ok(f"{total} diagnostic(s), none above baseline")
    return True


def check_cppcheck():
    head("cppcheck")
    cppcheck = shutil.which("cppcheck")
    if not cppcheck:
        skip("cppcheck not found (apt: sudo apt install cppcheck)")
        return True

    proc = subprocess.run(
        [cppcheck, "--enable=warning,performance,portability",
         "--std=c11", "--quiet",
         "--error-exitcode=0",   # findings are compared to the baseline below
         "-Isrc", "src"],
        capture_output=True, text=True, cwd=ROOT,
    )
    text = proc.stdout + proc.stderr
    findings = [
        line.strip() for line in text.splitlines()
        if ": (error" in line or ": (warning" in line or ": (style" in line
    ]

    baseline = load_baseline().get("cppcheck", {})
    by_file = {}
    for f in findings:
        path = f.split(":", 1)[0].replace("\\", "/")
        by_file[path] = by_file.get(path, 0) + 1

    regressed = False
    for path, count in sorted(by_file.items()):
        was = baseline.get(path, 0)
        if count > was:
            bad(f"{path}: {count} findings (baseline {was})")
            regressed = True
        else:
            ok(f"{path}: {count} findings (baseline {was})")
    if not by_file:
        ok("no findings")
    return not regressed


def check_luacheck():
    head("luacheck")
    luacheck = shutil.which("luacheck")
    if not luacheck:
        skip("luacheck not found "
             "(luarocks install luacheck) — Lua is unchecked on this machine")
        return True

    rc_path = ROOT / ".luacheckrc"
    if not rc_path.exists():
        bad(".luacheckrc is missing — the host globals are undeclared, so "
            "every legitimate global would read as a typo")
        return False

    targets = [str(p.relative_to(ROOT)).replace("\\", "/")
               for p in (ROOT / "data").rglob("*.lua")]
    if not targets:
        skip("no Lua under data/")
        return True

    proc = subprocess.run(
        [luacheck, "--codes", *targets],
        capture_output=True, text=True, cwd=ROOT,
    )
    baseline = load_baseline().get("luacheck", {})
    total = baseline.get("total", 0)

    m = re.search(r"total:\s*(\d+)\s+warning", proc.stdout)
    found = int(m.group(1)) if m else 0

    if found > total:
        bad(f"{found} warnings (baseline {total})")
        return False
    if found:
        warn(f"{found} warnings (baseline {total}) — pre-existing, see baseline")
    else:
        ok("no warnings")
    return True


def strip_c_noise(text):
    """Blank out C comments, string literals and char literals, preserving offsets.

    The banned-construct scan used to run over the raw text, which meant a
    comment explaining why `calloc(count, size)` is a classic overflow matched as
    if the file called calloc. Two of the "new" calloc findings in Phase 1 were a
    comment and a log message; a gate that counts prose is a gate that gets
    ignored.

    Offsets are preserved (each removed span becomes the same number of spaces,
    minus its newlines so line numbers stay right), so a finding can still be
    reported at the line it is really on.

    Deliberately a small scanner rather than a C parser: it handles the three
    things that can hide a banned call — comments, strings, chars — and does not
    try to understand the language.
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(_blank(text[i:j]))
            i = j
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(_blank(text[i:j]))
            i = j
        elif c in "\"'":
            quote = c
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == quote:
                    j += 1
                    break
                if text[j] == "\n":       # unterminated: stop at the line end
                    break
                j += 1
            out.append(_blank(text[i:j]))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _blank(span):
    """Same length, same newlines, no content."""
    return "".join("\n" if ch == "\n" else " " for ch in span)


# Files allowed to call the system allocator, per banned pattern.
#
# src/base/alloc.c is the allocator: it is the layer that wraps malloc, so the
# rule "use cdin_alloc instead of malloc" cannot apply to it — it is the thing
# cdin_alloc is. Exempting it by name, with this comment, is better than leaving
# the finding to be explained in a report every phase: the exemption is the
# reason, not a suppression.
BANNED_EXEMPT = {
    "bare malloc": {"src/base/alloc.c"},
    "calloc":      {"src/base/alloc.c"},
    "realloc":     {"src/base/alloc.c"},
}

# Module level, not inside check_banned, because tests/record_baseline.py
# imports it to record the baseline. Two copies of a scan is two numbers.
BANNED_PATTERNS = {
    "strcpy":        re.compile(r"\bstrcpy\s*\("),
    "strcat":        re.compile(r"\bstrcat\s*\("),
    "sprintf":       re.compile(r"\bsprintf\s*\("),
    "gets":          re.compile(r"\bgets\s*\("),
    "atoi":          re.compile(r"\batoi\s*\("),
    "alloca":        re.compile(r"\balloca\s*\("),
    "bare malloc":   re.compile(r"(?<![_a-zA-Z])malloc\s*\("),
    "calloc":        re.compile(r"(?<![_a-zA-Z])calloc\s*\("),
    "realloc":       re.compile(r"(?<![_a-zA-Z])realloc\s*\("),
}


def check_banned():
    head("banned constructs (AGENTS.md §6)")
    # Banned in new code. Reported, not failed: the existing sources predate the
    # rule and Phase 1 replaces them wholesale. The count is the number to watch
    # go down, not a gate.
    patterns = BANNED_PATTERNS
    baseline = load_baseline().get("banned", {})
    counts = {}
    exempt_hits = []
    for path in c_sources():
        try:
            text = strip_c_noise((ROOT / path).read_text(encoding="utf-8",
                                                         errors="replace"))
        except OSError:
            continue
        for name, pat in patterns.items():
            # Counted line by line rather than over the whole text, so a file can
            # be exempted by path — and so a finding can be reported at the line
            # it is really on.
            n = sum(1 for line in text.splitlines() if pat.search(line))
            if not n:
                continue
            if path in BANNED_EXEMPT.get(name, set()):
                exempt_hits.append((name, path, n))
            else:
                counts[name] = counts.get(name, 0) + n

    for name, path, n in sorted(exempt_hits):
        ok(f"{name}: {n} in {path} — exempt (that is the allocator)")

    regressed = False
    for name, n in sorted(counts.items()):
        was = baseline.get(name, 0)
        if n > was:
            bad(f"{name}: {n} (baseline {was}) — {n - was} new")
            regressed = True
        else:
            ok(f"{name}: {n} (baseline {was})")
    if not counts:
        ok("none outside the exempt files")
    else:
        warn("these are pre-existing; Phase 1 replaces them with cdin_alloc")
    return not regressed


def check_platform_branches():
    """Compile-check the non-Windows branches of src/platform/.

    A MinGW build never selects them, so a typo or a wrong signature in the Linux
    or macOS path is invisible until someone builds on those systems — the worst
    place to find it, because the person who finds it is not the person who wrote
    it. So the check is attempted here and reports SKIPPED, with the reason, when
    the toolchain cannot do it: the MinGW headers refuse to compile at all
    without _WIN32, so no flag makes them accept otherwise.

    Its own check rather than part of the compiler check, because "the compiler
    was clean" and "the branches nobody compiled were checked" are different
    facts, and merging them is how the second one stops being asked.
    """
    head("platform branches (src/platform)")

    src = ROOT / "src" / "platform" / "platform.c"
    if not src.is_file():
        bad(f"{src.relative_to(ROOT)} does not exist — nothing to check")
        return False

    cc = os.environ.get("CC") or "cc"
    if not shutil.which(cc):
        warn(f"{cc} not found — SKIPPED, not a pass")
        return True

    sdl_cflags = []
    if shutil.which("pkg-config"):
        for pkg in ("sdl3", "sdl2"):
            if subprocess.run(["pkg-config", "--exists", pkg],
                              capture_output=True).returncode == 0:
                out = subprocess.run(["pkg-config", "--cflags", pkg],
                                     capture_output=True, text=True)
                sdl_cflags = out.stdout.split()
                break

    all_ok = True
    diag_re = re.compile(r"^(.+?):(\d+):(\d+):\s+(error|fatal error):\s+(.*)$")

    for macro, label in (("__linux__", "linux"), ("__APPLE__", "macos")):
        cmd = [cc, "-std=gnu11", "-fsyntax-only",
               "-U_WIN32", "-U_WIN64", "-D%s=1" % macro,
               "-Wall", "-Wextra", "-Wno-unused-parameter", "-Isrc",
               *sdl_cflags, str(src)]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
        output = proc.stdout + proc.stderr

        if proc.returncode == 0:
            ok(f"{label} branch compiles")
            continue

        # The discriminator: did the compiler reach OUR code?
        #
        # MinGW's headers refuse to build at all without _WIN32 ("#error Only
        # Win32 target is supported!"), and SDL's headers include
        # AvailabilityMacros.h — a macOS SDK header — as soon as __APPLE__ is
        # defined. Both are the toolchain declining to express the target, not
        # our code being wrong, and both must be a SKIP.
        #
        # Only an error whose file is under src/ is ours to answer for. Anything
        # else is the toolchain, and reporting it as a failure would mean this
        # check fails on every MinGW machine forever, which is how a check gets
        # deleted.
        # Only an error in one of OUR files is ours to answer for. Compiler and
        # SDK diagnostics come with their own paths (mingw64/include/..., /usr/...),
        # so "does this path contain a src/ component" separates them. Crude, and
        # a toolchain whose own headers lived under a src/ directory would make
        # this check fail with a confusing message — which is the correct outcome
        # anyway, because somebody then has to look at it.
        ours, theirs = [], []
        for line in output.splitlines():
            m = diag_re.match(line.strip())
            if not m:
                continue
            path = "/" + m.group(1).replace("\\", "/").lstrip("/")
            (ours if "/src/" in path else theirs).append(line.strip())

        if not ours:
            reason = theirs[0] if theirs else (output.splitlines() or [""])[0]
            warn(f"SKIPPED {label}: the toolchain cannot express this target, so "
                 f"the branch was never compiled — {reason[:150]}")
            continue

        bad(f"{label} branch does not compile:")
        for line in ours[:12]:
            bad(f"    {line}")
        all_ok = False
    return all_ok


def check_baseline_is_current():
    head("baseline freshness")
    baseline = load_baseline()
    if not baseline:
        bad("tests/check_baseline.json is empty or unreadable — no check has "
            "a number to compare against, so no check can gate anything")
        return False

    listed = set(baseline.get("sources", []))
    actual = set(c_sources())
    if listed != actual:
        missing = sorted(actual - listed)
        extra = sorted(listed - actual)
        for p in missing:
            bad(f"new source not in the baseline: {p} "
                f"(add it, then re-run and record its warnings)")
        for p in extra:
            bad(f"baseline lists a source that does not exist: {p}")
        return False
    ok(f"{len(actual)} sources tracked")
    return True


def main():
    cc = cc_name()
    results = []

    results.append(("baseline", check_baseline_is_current()))
    results.append(("compiler", check_compiler(cc)))
    results.append(("banned", check_banned()))
    results.append(("platform", check_platform_branches()))
    results.append(("cppcheck", check_cppcheck()))
    results.append(("luacheck", check_luacheck()))

    print(f"\n{DIM}{'─' * 44}{RESET}")
    failed = [name for name, ok_ in results if not ok_]
    for name, ok_ in results:
        mark = f"{GREEN}ok{RESET}" if ok_ else f"{RED}FAIL{RESET}"
        print(f"   {mark}  {name}")

    if failed:
        print(f"\n{RED}check FAILED{RESET}: {', '.join(failed)}")
        return 1
    print(f"\n{GREEN}check OK{RESET}")
    print(f"{DIM}   SKIPPED checks are listed above with their reason; a skipped")
    print(f"   check is not a passing check.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
