"""Is the bundled editor actually redrawing continuously?

The user reports the window refreshing constantly in the `make build` tree. Two
different faults look identical on screen and have opposite causes:

  a redraw loop   the frame loop decides something is damaged every frame and
                  redraws all of it — CPU cost, cache invalidated each frame
  a window resize the window itself keeps being resized, and the compositor
                  shows that as flicker — CPU may be low

So this measures both, and compares the bundled tree against the bare one, which
is the only tree whose behaviour depends on nothing outside this repository. A
difference between them is cdin-x's, not cdin's.
"""
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\CODE\cdin")

TREES = {
    "bare     (core + fonts + themes)": ROOT / "build" / "bare",
    "bundled  (core + cdin-x plugins)": ROOT / "build" / "windows-release",
}

SAMPLE_SECONDS = 12.0
POLL = 0.25

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.GetProcessTimes.restype = wintypes.BOOL
kernel32.GetProcessTimes.argtypes = (
    wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME))
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

QPI = 0x1000


def cpu_seconds(pid):
    h = kernel32.OpenProcess(QPI, False, pid)
    if not h:
        return None
    try:
        c, e, k, u = (wintypes.FILETIME(),) * 4
        ok = kernel32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e),
                                      ctypes.byref(k), ctypes.byref(u))
    finally:
        kernel32.CloseHandle(h)
    if not ok:
        return None
    val = lambda f: (f.dwHighDateTime << 32) | f.dwLowDateTime
    return (val(u) + val(k)) / 1e7


def measure(label, tree):
    exe = tree / "cdin.exe"
    log = tree / "cdin-log.txt"
    if not exe.exists():
        print(f"{label}\n   NOT MEASURED - {exe} does not exist (run `make bare` / `make build`)")
        return
    if log.exists():
        log.unlink()

    # DEBUG level, so cache invalidation is visible: the full-invalidation line
    # is DEBUG, and at INFO a redraw loop is invisible.
    proc = subprocess.Popen([str(exe)], cwd=str(tree),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env={**os.environ, "CDIN_LOG_LEVEL": "debug",
                                 "CDIN_LOG_FILE": str(log)})
    time.sleep(4.0)          # let boot finish before counting
    alive = proc.poll() is None

    log_lines0 = len(log.read_text(encoding="utf-8", errors="replace").splitlines()) \
        if log.exists() else 0

    cpu0 = cpu_seconds(proc.pid)
    t0 = time.perf_counter()
    time.sleep(SAMPLE_SECONDS)
    cpu1 = cpu_seconds(proc.pid)
    wall = time.perf_counter() - t0

    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    log_lines1 = len(text.splitlines())

    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

    invalidations = text.count("full invalidation")
    presented = text.count("first frame presented")
    resized = text.count("window resized from")

    print(f"{label}")
    print(f"   stayed alive          {alive}")
    if cpu0 is None or cpu1 is None:
        print("   idle CPU              NOT MEASURED - process CPU time unreadable")
        idle = None
    else:
        idle = 100.0 * (cpu1 - cpu0) / wall
        print(f"   idle CPU over {SAMPLE_SECONDS:.0f}s     {idle:6.2f} %   "
              f"({cpu1 - cpu0:.3f} s cpu in {wall:.1f} s wall)")
    print(f"   log lines while idle  {log_lines1 - log_lines0}   "
          f"(rate {1000 * (log_lines1 - log_lines0) / (SAMPLE_SECONDS * POLL):.0f}/s)")
    print(f"   cache invalidations   {invalidations} total")
    print(f"   window resize events  {resized} total")
    print(f"   frames presented      {presented}")
    print()
    return {"idle": idle, "log_rate": (log_lines1 - log_lines0) / SAMPLE_SECONDS,
            "invalidations": invalidations, "resizes": resized}


print(f"-- is the bundled editor redrawing continuously? ({SAMPLE_SECONDS:.0f}s idle sample each) --")
print("   A redraw loop shows up as idle CPU well above zero AND log lines per second.\n")

results = {}
for label, tree in TREES.items():
    results[label] = measure(label, tree)

b = results.get("bare     (core + fonts + themes)")
u = results.get("bundled  (core + cdin-x plugins)")
if b and u:
    print("-- comparison --")
    if b["idle"] is not None and u["idle"] is not None:
        ratio = u["idle"] / b["idle"] if b["idle"] > 0.001 else float("inf")
        print(f"   idle CPU ratio bundled/bare: {ratio:.1f}x")
    print(f"   log rate  bare {b['log_rate']:.1f}/s   bundled {u['log_rate']:.1f}/s")
    print(f"   invalidations  bare {b['invalidations']}   bundled {u['invalidations']}")
    print(f"   resizes        bare {b['resizes']}   bundled {u['resizes']}")
