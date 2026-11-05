#!/usr/bin/env python3
"""Measure the real CDIN headless integration path and emit a reproducible JSON report.

This is a macro benchmark for `cdin --check`. It measures end-to-end process
latency and sampled peak RSS; it does not claim per-operation latency or a soak
test. Sampling may miss very short RSS peaks, which is recorded in the report.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def percentile(values: list[float], quantile: float) -> float:
    """Linearly interpolated percentile in the closed interval [0, 1]."""
    if not values:
        raise ValueError("percentile requires at least one sample")
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between 0 and 1")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_output(command: list[str], cwd: Path = ROOT) -> str | None:
    try:
        result = subprocess.run(
            command, cwd=cwd, text=True, capture_output=True, check=False, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def repository_revision() -> str | None:
    return command_output(["git", "rev-parse", "HEAD"])


def parse_linux_rss(status: str) -> int | None:
    """Parse VmRSS from procfs status text and return bytes."""
    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                unit = parts[2].lower() if len(parts) >= 3 else "kb"
                multiplier = {"kb": 1024, "b": 1}.get(unit)
                if multiplier is not None:
                    return int(parts[1]) * multiplier
    return None


class RssSampler:
    """Read one process' resident set size using native OS facilities."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.kind = "unavailable"
        self.handle: Any = None
        self.kernel32: Any = None
        self.psapi: Any = None
        self.counters_type: Any = None
        if sys.platform.startswith("linux") and Path(f"/proc/{pid}/status").is_file():
            self.kind = "procfs"
        elif os.name == "nt":
            self._open_windows_process()
        elif sys.platform == "darwin":
            self.kind = "ps"

    def _open_windows_process(self) -> None:
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        try:
            self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self.psapi = ctypes.WinDLL("psapi", use_last_error=True)
            self.kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
            self.kernel32.OpenProcess.restype = ctypes.c_void_p
            self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            self.kernel32.CloseHandle.restype = ctypes.c_int
            self.psapi.GetProcessMemoryInfo.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(ProcessMemoryCounters), ctypes.c_ulong
            ]
            self.psapi.GetProcessMemoryInfo.restype = ctypes.c_int
            # PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
            self.handle = self.kernel32.OpenProcess(0x0400 | 0x0010, 0, self.pid)
            if self.handle:
                self.kind = "GetProcessMemoryInfo"
                self.counters_type = ProcessMemoryCounters
        except (AttributeError, OSError):
            self.close()

    def read_bytes(self) -> int | None:
        if self.kind == "procfs":
            try:
                return parse_linux_rss(Path(f"/proc/{self.pid}/status").read_text(encoding="ascii"))
            except (OSError, UnicodeError):
                return None
        if self.kind == "GetProcessMemoryInfo" and self.handle and self.counters_type:
            counters = self.counters_type()
            counters.cb = ctypes.sizeof(counters)
            if self.psapi.GetProcessMemoryInfo(
                self.handle, ctypes.byref(counters), counters.cb
            ):
                return int(counters.WorkingSetSize)
            return None
        if self.kind == "ps":
            # macOS does not expose procfs. ps reports RSS in KiB.
            result = command_output(["ps", "-o", "rss=", "-p", str(self.pid)])
            if result:
                try:
                    return int(result.splitlines()[0]) * 1024
                except (ValueError, IndexError):
                    return None
        return None

    def close(self) -> None:
        if self.handle and self.kernel32 is not None:
            self.kernel32.CloseHandle(self.handle)
        self.handle = None


def run_check(
    executable: Path,
    *,
    environment: dict[str, str],
    timeout_seconds: float,
    sample_interval_ms: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    samples: list[int] = []
    with tempfile.TemporaryFile(mode="w+b") as log:
        process = subprocess.Popen(
            [str(executable), "--check"],
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        sampler = RssSampler(process.pid)
        deadline = started + timeout_seconds
        try:
            rss = sampler.read_bytes()
            if rss is not None:
                samples.append(rss)
            while process.poll() is None:
                if time.perf_counter() >= deadline:
                    process.kill()
                    process.wait(timeout=5)
                    raise TimeoutError(
                        f"cdin --check exceeded {timeout_seconds:g}s"
                    )
                time.sleep(sample_interval_ms / 1000.0)
                rss = sampler.read_bytes()
                if rss is not None:
                    samples.append(rss)
            return_code = process.returncode
        finally:
            sampler.close()
        elapsed = time.perf_counter() - started
        log.seek(0)
        output = log.read().decode("utf-8", errors="replace")
    if return_code != 0:
        raise RuntimeError(
            f"cdin --check exited with status {return_code}; output tail:\\n{output[-4000:]}"
        )
    return {
        "elapsed_seconds": elapsed,
        "exit_code": return_code,
        "sampled_peak_rss_bytes": max(samples) if samples else None,
        "rss_sample_count": len(samples),
        "rss_sampler": sampler.kind,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    default_executable = ROOT / ".deps" / "install" / "bin" / (
        "cdin.exe" if os.name == "nt" else "cdin"
    )
    parser.add_argument("--executable", type=Path, default=default_executable)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--sample-interval-ms", type=float, default=10.0)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dist" / "cdin-headless-benchmark.json"
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.warmup < 0 or args.iterations < 3:
        print("warmup must be >= 0 and iterations must be >= 3", file=sys.stderr)
        return 2
    if not 1.0 <= args.sample_interval_ms <= 1000.0:
        print("sample interval must be between 1 and 1000 ms", file=sys.stderr)
        return 2
    if args.timeout_seconds <= 0.0:
        print("timeout must be positive", file=sys.stderr)
        return 2
    executable = args.executable.resolve()
    if not executable.is_file():
        print(f"CDIN executable not found: {executable}", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    runtime_root = args.runtime_root
    if runtime_root is None and not environment.get("CDIN_RUNTIME_ROOT"):
        candidate = executable.parent.parent / "share" / "cdin" / "lua"
        if candidate.is_dir():
            runtime_root = candidate
    if runtime_root is not None:
        if not runtime_root.is_dir():
            print(f"Runtime root does not exist: {runtime_root}", file=sys.stderr)
            return 2
        environment["CDIN_RUNTIME_ROOT"] = str(runtime_root.resolve())

    try:
        warmups = [
            run_check(
                executable,
                environment=environment,
                timeout_seconds=args.timeout_seconds,
                sample_interval_ms=args.sample_interval_ms,
            )
            for _ in range(args.warmup)
        ]
        measurements = []
        for index in range(args.iterations):
            measurement = run_check(
                executable,
                environment=environment,
                timeout_seconds=args.timeout_seconds,
                sample_interval_ms=args.sample_interval_ms,
            )
            measurements.append(measurement)
            print(
                f"benchmark {index + 1}/{args.iterations}: "
                f"{measurement['elapsed_seconds']:.4f}s, "
                f"sampled peak RSS={measurement['sampled_peak_rss_bytes']}",
                flush=True,
            )
    except (OSError, RuntimeError, TimeoutError) as error:
        print(f"benchmark failed: {error}", file=sys.stderr)
        return 1

    latencies = [item["elapsed_seconds"] for item in measurements]
    rss_values = [
        item["sampled_peak_rss_bytes"]
        for item in measurements
        if item["sampled_peak_rss_bytes"] is not None
    ]
    report = {
        "schema_version": 1,
        "status": "pass",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "git_revision": repository_revision(),
            "deps_lock_sha256": sha256_file(ROOT / "deps.lock"),
            "executable_sha256": sha256_file(executable),
        },
        "environment": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "compiler": os.environ.get("CC", "not-recorded"),
            "build_type": os.environ.get("CMAKE_BUILD_TYPE", "Release (stack default)"),
        },
        "workload": {
            "name": "headless-composition-root-check",
            "command": [str(executable), "--check"],
            "warmup_iterations": args.warmup,
            "measured_iterations": args.iterations,
            "sample_interval_ms": args.sample_interval_ms,
            "timeout_seconds": args.timeout_seconds,
            "latency_definition": (
                "wall time from process creation until cdin --check exits successfully; "
                "this is an end-to-end macro measurement, not per-operation latency"
            ),
            "rss_definition": (
                "maximum resident set size observed by periodic OS process sampling; "
                "very short peaks between samples may be missed"
            ),
        },
        "latency_seconds": {
            "sample_count": len(latencies),
            "min": min(latencies),
            "mean": sum(latencies) / len(latencies),
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": max(latencies),
        },
        "sampled_peak_rss_bytes": {
            "sample_count": len(rss_values),
            "median": percentile([float(value) for value in rss_values], 0.50) if rss_values else None,
            "max": max(rss_values) if rss_values else None,
            "samplers": sorted({item["rss_sampler"] for item in measurements}),
            "total_rss_samples": sum(item["rss_sample_count"] for item in measurements),
        },
        "warmup_results": warmups,
        "measurements": measurements,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
    temporary.replace(args.output)
    print(f"Benchmark report: {args.output}")
    print(
        f"Latency p50/p95/p99: {report['latency_seconds']['p50']:.4f}/"
        f"{report['latency_seconds']['p95']:.4f}/"
        f"{report['latency_seconds']['p99']:.4f} seconds"
    )
    if rss_values:
        print(f"Sampled peak RSS max: {max(rss_values)} bytes")
    else:
        print("Sampled peak RSS: unavailable on this platform")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
