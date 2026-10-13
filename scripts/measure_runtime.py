# Startup and idle-CPU measurement for the bare runtime.
#
# Two numbers the phase report needs and that neither the log nor the benchmark
# harness produces:
#
#   startup   process launch -> first frame drawn. Taken from the log's own
#             timestamps, because the process clock includes SDL and font
#             loading that a stopwatch around Start-Process also includes, but
#             only the log distinguishes them.
#   idle CPU  sampled CPU time over a window in which nothing is happening. The
#             loop is supposed to sleep until an event when idle; if it spins,
#             this is where it shows.
#
# Run with the bare runtime (data/core + fonts, no plugins), because a plugin
# doing work would be measured instead of the frame loop.

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
BARE = ROOT / "build" / "bare"
LOG = BARE / "cdin-log.txt"

IDLE_SECONDS = 12.0
SAMPLE = 0.25


def process_cpu_seconds(pid):
    """CPU seconds a process has used, or None if it cannot be read.

    Windows: GetProcessTimes. Elsewhere: /proc/<pid>/stat. No psutil, because a
    measurement that needs a package the reviewer may not have is a measurement
    that will not be run.

    The argtypes and restype are declared explicitly and this is not ceremony.
    ctypes defaults every restype to c_int, so without them OpenProcess's
    64-bit HANDLE comes back truncated — GetProcessTimes then either fails or
    reads a handle that belongs to something else, and the symptom is a delta of
    exactly zero for a process that is obviously burning CPU. That is what this
    function returned before the calibration step existed, and it is why the
    idle-CPU figure recorded in Phase 0 (0.26–0.39 %) cannot be trusted: it may
    have been a truncated handle rather than the frame loop.
    """
    import os
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD,   # dwDesiredAccess
                                         wintypes.BOOL,    # bInheritHandle
                                         wintypes.DWORD)   # dwProcessId

        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),   # creation
            ctypes.POINTER(wintypes.FILETIME),   # exit
            ctypes.POINTER(wintypes.FILETIME),   # kernel
            ctypes.POINTER(wintypes.FILETIME))   # user

        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        def ft_to_int(f):
            return (f.dwHighDateTime << 32) | f.dwLowDateTime

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,
                                      False, pid)
        if not handle:
            return None
        try:
            creation, exit_t, kernel, user = (wintypes.FILETIME(),
                                              wintypes.FILETIME(),
                                              wintypes.FILETIME(),
                                              wintypes.FILETIME())
            ok = kernel32.GetProcessTimes(handle,
                                          ctypes.byref(creation),
                                          ctypes.byref(exit_t),
                                          ctypes.byref(kernel),
                                          ctypes.byref(user))
        finally:
            kernel32.CloseHandle(handle)
        if not ok:
            return None
        # FILETIME counts 100 ns intervals.
        return (ft_to_int(user) + ft_to_int(kernel)) / 1e7

    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            fields = f.read().split()
        # utime and stime are fields 14 and 15 (1-based), after the comm field
        # which may itself contain spaces — so parse from the closing paren.
        tail = fields[fields.index(b")") + 2:]
        ticks = os.sysconf("SC_CLK_TCK")
        return (int(tail[11]) + int(tail[12])) / ticks
    except (OSError, ValueError, IndexError):
        return None


def startup_ms():
    """Launch the editor, watch the log grow, and time the phases.

    Times each milestone as it appears in the log rather than only the first and
    last, because "184 ms" does not say whether the cost is SDL, the fonts or the
    Lua boot, and those have completely different fixes. The log's own timestamps
    are one-second resolution, which cannot answer that at all, so the arrival
    time of each line is recorded here instead — an external observer, polling at
    SAMPLE. Resolution is the poll interval, not the clock.

    Two consequences worth stating: the first milestone's time includes process
    creation and dynamic linking, which is real and part of what a user waits
    for; and every milestone time is an upper bound, since a line is seen at the
    next poll rather than when it was written.
    """
    if LOG.exists():
        LOG.unlink()

    t0 = time.perf_counter()
    proc = subprocess.Popen([str(BARE / "cdin.exe"), "--no-plugins"],
                            cwd=str(ROOT),
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            env={**dict(__import__("os").environ),
                                 "CDIN_LOG_LEVEL": "info",
                                 "CDIN_LOG_FILE": str(LOG)})

    # (label, substring) in the order they are expected. First match wins, so a
    # marker repeated later (the fonts are loaded one per line) reports when it
    # first happened rather than when it was last seen.
    #
    # Every needle here is a literal the code actually emits. Two were stale and
    # silently matched nothing: the native-library needle looked for "native Lua
    # libraries registered" while api.c prints "3 eager + 2 lazy native libraries
    # registered", and the font milestone demanded 7 fonts when the bare runtime
    # loads 6. A marker that never matches is the worst kind of instrumentation —
    # it looks like a phase you chose not to measure.
    markers = [
        ("cdin starting",       "cdin starting"),
        # SDL_Init split out because it can dominate on a machine that has to
        # initialise a display driver, and because conflating it with the window
        # made the phase table useless for deciding what to fix.
        ("SDL_Init begin",      "SDL_Init begin"),
        ("SDL_Init done",       "SDL_Init done"),
        ("window created",      "window created"),
        ("native libraries",    "lazy native libraries registered"),
        ("lua_state created",   "lua_state created"),
        ("globals ready",       "globals ready"),
        ("job loop ready",      "job_loop: initialised"),
        # Everything from here to the last font is core.init(), which is Lua and
        # C mixed together; there is no marker inside it finer than the fonts
        # themselves, which is why they are tracked individually below.
        ("core.init begin",     "booting core.init()"),
        ("cwd changed",         "working directory changed"),
        # A PRESENTED frame, not a cache-setup message. This used to watch for
        # "window resized from", which is emitted by rencache_resize while the
        # damage cache is still being configured and long before any pixel reaches
        # the screen — so the metric was timing cache setup and calling it a frame.
        # "first frame presented" comes from rencache_end_frame, the one place
        # where pixels are handed to the display.
        ("first frame",         "first frame presented"),
    ]

    seen_at = {}
    font_count = 0
    first_frame_at = None
    last_size = 0

    deadline = time.perf_counter() + 20.0
    while time.perf_counter() < deadline:
        if LOG.exists():
            try:
                text = LOG.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            now = time.perf_counter()
            for label, needle in markers:
                if label in seen_at:
                    continue
                if needle in text:
                    seen_at[label] = (now - t0) * 1000.0
            # Each font gets its own milestone, counted as they appear rather than
            # compared against a hardcoded total. The total was hardcoded, and it
            # was wrong (it expected 7; the bare runtime loads 6), so the "all
            # fonts loaded" milestone never appeared and font loading — one of the
            # two things the startup budget investigation has to account for — had
            # no time attached to it at all. Counting what actually happened cannot
            # be wrong about how many there are.
            n = text.count('loaded "')
            while font_count < n:
                font_count += 1
                seen_at[f"font {font_count}"] = (now - t0) * 1000.0
            # A PRESENTED frame. This line used to break on "window resized from",
            # which is emitted by rencache_resize while the damage cache is still
            # being configured — long before any pixel reaches the screen. The
            # metric therefore reported cache setup and called it a frame, which
            # understates the real cost by however long the first draw takes.
            if first_frame_at is None and "first frame presented" in text:
                first_frame_at = now
                break
        time.sleep(0.005)   # 5 ms, so the phases are not quantised to 20 ms

    # Let it settle, then sample CPU while nothing happens.
    time.sleep(1.5)
    cpu0 = process_cpu_seconds(proc.pid)
    t_start = time.perf_counter()
    time.sleep(IDLE_SECONDS)
    cpu1 = process_cpu_seconds(proc.pid)
    wall = time.perf_counter() - t_start

    if cpu0 is None or cpu1 is None:
        idle_pct = None
        cpu = None
    else:
        cpu = cpu1 - cpu0
        idle_pct = 100.0 * cpu / wall if wall > 0 else 0.0

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

    return {
        "launch_to_first_frame_ms": (first_frame_at - t0) * 1000.0
            if first_frame_at else None,
        "milestones": seen_at,
        "font_count": font_count,
        "idle_seconds": IDLE_SECONDS,
        "idle_cpu_percent": idle_pct,
        "idle_cpu_seconds": cpu,
    }


def _child_burns_cpu(seconds):
    """A child that certainly uses CPU, as a calibration target.

    Spawned through this same interpreter rather than a system command, so the
    only thing being calibrated is the reading, not the tool's availability."""
    import os
    code = (
        "import time\n"
        "t = time.perf_counter()\n"
        "x = 0\n"
        "while time.perf_counter() - t < %r:\n"
        "    x = (x * 1103515245 + 12345) & 0xFFFFFFFF\n"
        "print(x)\n" % float(seconds)
    )
    return subprocess.Popen([sys.executable, "-c", code],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def calibrate():
    """Check that this script can read CPU time at all, by measuring a process
    that is definitely using it.

    Returns (ok, observed_percent).

    Without this, a reader cannot tell "the editor used no CPU while idle" from
    "the harness could not read CPU and silently reported zero" — and those have
    opposite meanings. Phase 0's version had exactly that hole: it reported
    0.00 % idle, and the only way to know whether that was true or broken was to
    read the source and guess. A measurement that cannot be falsified is not a
    measurement, so this spends one second proving the instrument works before
    trusting it.

    Deliberately not asserted against a threshold. The point is only "non-zero",
    because the exact figure depends on core count and how busy the box is.
    """
    child = _child_burns_cpu(1.2)
    try:
        time.sleep(0.2)
        cpu0 = process_cpu_seconds(child.pid)
        t0 = time.perf_counter()
        time.sleep(1.0)
        cpu1 = process_cpu_seconds(child.pid)
        wall = time.perf_counter() - t0
    finally:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()

    if cpu0 is None or cpu1 is None:
        return False, None
    observed = 100.0 * (cpu1 - cpu0) / wall if wall > 0 else 0.0
    return observed > 0.0, observed


# Five samples, not three.
#
# Three is enough to see that a number moves, and not enough to describe a
# distribution: with three samples the median is the middle value and the
# min/max say almost nothing about the shape. Five is the smallest count where
# the median is a real central estimate rather than an artefact of which samples
# happened to land where, and it costs two extra editor launches, which is
# seconds.
REPEATS = 5


def sample_once():
    return startup_ms()


def summarise(samples):
    """Median-of-N, with every sample and the spread printed.

    MEDIAN, not best-of and not mean. The thing being measured is the runtime's
    own cost, but the box is also being measured: another process, Windows
    Defender scanning a freshly linked binary, or a WSL VM all push samples up and
    none of them is the editor's fault. Taking the minimum answers a question
    nobody asked — "how fast was this once, on the quietest run" — and it is the
    number most flattering to a failing result, because a single lucky sample
    makes a 400 ms startup look like 130 ms. The owner settled on median for
    exactly this reason.

    Mean is wrong for the opposite reason: one 3x outlier drags it far enough to
    report a number the user will essentially never experience.

    Both the median and the full list are returned. The list is what stops a
    property of this machine being reported as a property of the editor: five runs
    of an unchanged binary on this box gave startup of 244, 180, 184, 176, 168 ms
    in one session and 233, 193, 509, 512, 532 ms in the next, which is a 2.8x
    spread between sessions on identical code. A reader who sees only the median
    cannot tell that; a reader who sees the spread can.

    An earlier version reported "idle CPU 0.13%, PASS" from one sample and the next
    two runs said 0.91% and 3.25%. One sample is not a measurement of either
    figure, and the reason it looked convincing is that both passed.
    """
    def median(key):
        vals = sorted(s[key] for s in samples if s.get(key) is not None)
        if not vals:
            return None
        mid = len(vals) // 2
        if len(vals) % 2:
            return vals[mid]
        return (vals[mid - 1] + vals[mid]) / 2.0

    def spread(key):
        vals = [s[key] for s in samples if s.get(key) is not None]
        if len(vals) < 2 or min(vals) <= 0:
            return None
        return max(vals) / min(vals)

    return {
        "startup": median("launch_to_first_frame_ms"),
        "startup_spread": spread("launch_to_first_frame_ms"),
        "idle": median("idle_cpu_percent"),
        "idle_spread": spread("idle_cpu_percent"),
        "startup_all": [s["launch_to_first_frame_ms"] for s in samples],
        "idle_all": [s["idle_cpu_percent"] for s in samples],
        "samples": samples,
    }


def main():
    """Startup and idle CPU on the bare runtime.

    PRIMARY metric: process launch -> first PRESENTED frame. That is the point a
    user can see the editor, and it includes everything: process creation,
    dynamic linking, SDL, fonts, and the Lua boot. Nothing is excluded.

    SECONDARY diagnostic: process launch -> the first line of our own logging.
    The gap between the two is the time before main() gets to log anything, which
    is the loader and the CRT rather than cdin's code. It is reported separately
    and deliberately NOT subtracted from the primary figure: a user launching the
    editor waits for the loader too, so folding it into an "application startup"
    number would flatter the result by measuring less than the user experiences.
    """
    if not (BARE / "cdin.exe").exists():
        print(f"!! {BARE / 'cdin.exe'} is not prepared")
        print(f"   It needs cdin.exe plus data/core and data/fonts and nothing")
        print(f"   else - the runtime with no plugins in it, because a plugin")
        print(f"   doing work would be measured instead of the frame loop.")
        print(f"   Build the bare tree with `make bare`.")
        return 1

    print(f"-- startup and idle CPU ({BARE.name} runtime, no plugins) --")
    print("   primary metric   process launch -> first PRESENTED frame")
    print("                    (the \"first frame presented\" log line: the point")
    print("                     pixels reach the surface, not a cache-setup message)")
    print("   secondary        process launch -> first log line, for reference only.")
    print("                    The gap is pre-main loader time and is NOT subtracted")
    print("                    from the primary figure: a user waits for it too.")

    # Prove the instrument before reporting anything with it.
    cal_ok, cal_pct = calibrate()
    if cal_pct is None:
        print("   calibration    NOT MEASURED - CPU time could not be read for a "
              "known-busy process")
        print("                   idle CPU below is NOT a measurement.")
    else:
        print(f"   calibration    a known-busy process reads "
              f"{cal_pct:6.1f} % CPU - "
              + ("the instrument works" if cal_ok
                 else "!! WHICH MEANS a 0.00 % reading below is broken, not true"))

    samples = []
    for i in range(REPEATS):
        s = sample_once()
        samples.append(s)
        got_start = s["launch_to_first_frame_ms"]
        got_idle = s["idle_cpu_percent"]
        print(f"   sample {i + 1}/{REPEATS}: startup "
              f"{'--' if got_start is None else format(got_start, '.0f') + ' ms'}"
              f",  idle "
              f"{'--' if got_idle is None else format(got_idle, '.2f') + ' %'}")

    r = summarise(samples)
    startup = r["startup"]
    idle = r["idle"]

    print("")
    if startup is None:
        print(f"   startup, median of {REPEATS}   NOT MEASURED")
    else:
        # Median is the figure the budget is judged against, because a startup
        # budget describes a typical launch rather than the luckiest one. Best and
        # worst are printed alongside it so the reader can see the shape, but
        # neither is the verdict: the minimum is the number that most flatters a
        # failing result, and one fast sample among five is how a machine looks
        # like a runtime that meets its target.
        allv = sorted(v for v in r["startup_all"] if v is not None)
        print(f"   startup, median of {REPEATS}  {startup:8.1f} ms   "
              f"<-- the figure the budget is judged against")
        print(f"   startup, best of {REPEATS}     {allv[0]:8.1f} ms")
        print(f"   startup, worst of {REPEATS}   {allv[-1]:8.1f} ms")
        print("     every sample: "
              + ", ".join("%.0f" % v for v in r["startup_all"] if v is not None)
              + " ms"
              + (f"   ({r['startup_spread']:.1f}x spread - machine load, not the editor)"
                 if r["startup_spread"] else ""))

        # Two distinct spans, previously conflated under one wrong label.
        #
        #   loader   launch -> first log line. Everything before main() can say
        #            anything: process creation, the Windows loader mapping and
        #            relocating SDL3/Lua/libuv, CRT startup. Not cdin's code, and
        #            not changed by anything cdin does — but it IS part of what a
        #            user waits for, so it is reported, never subtracted.
        #
        #   ours     first log line -> first presented frame. Everything main()
        #            does: SDL, window, Lua boot, fonts, chdir, first draw. This
        #            is cdin's own cost and it is the only part cdin can change.
        #
        # These were the same number under one label reading "pre-main loader
        # time ... not cdin code", which excused exactly the span that is cdin's
        # and made the loader look like the bulk of a startup it cannot affect.
        loader = []
        ours = []
        for s in samples:
            first = (s.get("milestones") or {}).get("cdin starting")
            ff = s.get("launch_to_first_frame_ms")
            if first is None or ff is None:
                continue
            loader.append(first)
            ours.append(ff - first)

        def _median(v):
            v = sorted(v)
            n = len(v)
            if not n:
                return None
            return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0

        if loader:
            print(f"   of which pre-main loader (launch -> first log line): "
                  f"median {_median(loader):.0f} ms   "
                  f"(samples: " + ", ".join("%.0f" % v for v in loader) + " ms)")
            print("     -> Windows loader + CRT + mapping SDL3/Lua/libuv.")
            print("        Not cdin code and not changeable by cdin, but part of the wait.")
        if ours:
            print(f"   of which cdin's own work (first log line -> first frame): "
                  f"median {_median(ours):.0f} ms   "
                  f"(samples: " + ", ".join("%.0f" % v for v in ours) + " ms)")
            print("     -> SDL, window, Lua boot, fonts, chdir, first draw.")
            print("        This is the only part a change to cdin can affect.")
    if idle is None:
        print("   idle CPU: NOT MEASURED - CPU time could not be read")
    else:
        print(f"   idle CPU, median of {REPEATS}  {idle:7.2f} %   "
              f"<-- the figure the budget is judged against")
        print("     samples: "
              + ", ".join("%.2f" % v for v in r["idle_all"]) + " %"
              + (f"   ({r['idle_spread']:.1f}x spread - a shared machine, not the loop)"
                 if r["idle_spread"] else ""))

    # The phase breakdown, taken from the run whose total is closest to the
    # MEDIAN. Using the fastest run would flatter every phase equally and is the
    # run least like the one the budget is judged against; using the slowest
    # attributes contention to whichever phase happened to be running. The
    # median run is the one that represents a typical launch.
    finite = [i for i, s in enumerate(samples)
              if s["launch_to_first_frame_ms"] is not None]
    if finite:
        totals = sorted((samples[i]["launch_to_first_frame_ms"], i) for i in finite)
        mid_i = totals[len(totals) // 2][1]
        med_total = (totals[len(totals) // 2 - 1][0] + totals[len(totals) // 2][0]) / 2.0 \
            if len(totals) % 2 == 0 else totals[len(totals) // 2][0]
        miles = samples[mid_i].get("milestones") or {}
        if miles:
            print("")
            print(f"   startup phases, from the median run (total "
                  f"{samples[mid_i]['launch_to_first_frame_ms']:.0f} ms; 5 ms poll,")
            print("   so each figure is an upper bound and phases shorter than the")
            print("   poll interval collapse onto one another):")
            # The font count must come from the same run as the milestones, not
            # from whichever sample happened to be last.
            run_fonts = samples[mid_i].get("font_count") or 0
            order = ["cdin starting", "SDL_Init begin", "SDL_Init done",
                     "window created", "native libraries", "lua_state created",
                     "globals ready", "job loop ready", "core.init begin"]
            order += [f"font {i}" for i in range(1, run_fonts + 1)]
            order += ["cwd changed", "first frame"]
            prev = 0.0
            for label in order:
                if label not in miles:
                    continue
                t = miles[label]
                name = label
                if label == "first frame":
                    name = "first frame PRESENTED"
                elif label.startswith("font "):
                    name = f"font {label.split()[1]} loaded"
                print(f"     {name:<28} {t:7.0f} ms   (+{t - prev:5.0f})")
                prev = t
            # The trailing gap is this run's own total, not the median of all runs:
            # subtracting a median from a per-run milestone would print a phase
            # duration that belongs to no run at all.
            run_total = samples[mid_i]["launch_to_first_frame_ms"]
            if run_total is not None and run_total > prev:
                print(f"     {'(after the last marker)':<28} {run_total:7.0f} ms   "
                      f"(+{run_total - prev:5.0f})")

    print("")
    # Budgets. Compared against None explicitly, never with `x or default`: in
    # Python 0.0 is falsy, so `startup or 1e9` reports a genuine 0 ms or 0.00 %
    # as a failure. This is the same mistake as the Lua `-1 is truthy` one, and
    # it was in this file.
    def budget(label, value, limit, unit, which="median of"):
        if value is None:
            print(f"   {'-':>4}   {label}: not measured, so not judged")
            return False
        passed = value < limit
        print(f"   {'PASS' if passed else 'FAIL':>4}   {label}: "
              f"{value:.2f}{unit} against a {limit:g}{unit} budget "
              f"({which} {REPEATS})")
        return passed

    # Judged on the MEDIAN, and the best is printed alongside so the difference
    # between them stays visible.
    #
    # A startup budget describes what a user waits for on a typical launch, and the
    # median is the typical launch. Gating on the minimum means the verdict is
    # decided by the single luckiest sample of five, which is a property of the
    # machine's mood rather than of the runtime — and it flatters: an earlier
    # 3-sample run gave 1172, 144 and 136 ms, and quoting the 136 turned a
    # FAIL-shaped distribution into a pass.
    # A sample that never saw its marker is None, not 0. Sorting a mixed list
    # raises in Python 3, which is how a run where the editor never started —
    # the most important thing this harness can report — used to end in a
    # TypeError traceback instead of a sentence saying so.
    startup_all = sorted(v for v in r["startup_all"] if v is not None)
    median_startup = (startup_all[len(startup_all) // 2] if len(startup_all) % 2
                      else (startup_all[len(startup_all) // 2 - 1]
                            + startup_all[len(startup_all) // 2]) / 2.0) \
        if startup_all else None

    missing = [v for v in r["startup_all"] if v is None]
    if missing:
        print(f"   {len(missing)}/{REPEATS} samples saw NO \"first frame presented\""
              f" line at all — the editor did not reach a presented frame.")
        print("   The startup figure above covers only the samples that did, so it")
        print("   is not a trustworthy launch time. Treat startup as NOT MEASURED.")
        return 1

    budget("startup, launch to first PRESENTED frame",
           median_startup, 100.0, " ms", which="median of")
    budget("idle CPU", idle if (idle is not None and cal_ok) else None, 1.0, " %")
    return 0


if __name__ == "__main__":
    sys.exit(main())
