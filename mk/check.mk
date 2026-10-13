# `make check`, `make bench` and the memory harness. Split from mk/test.mk
# because these are about the state of the tree rather than about running a
# suite, and because they are the targets whose output goes into a phase report.
#
# Both are honest about what they could not do. A check that cannot run prints
# SKIPPED with the reason; a bench with no baseline says it has no baseline.
# Neither exits 0 in a way that reads as a pass when it did not pass.

.PHONY: check check-baseline bench bench-save bench-baseline mem runtime

# ── static checks ─────────────────────────────────────────────────────────

check:
	@command -v $(PYTHON) >/dev/null 2>&1 || { \
		echo '✗ $(PYTHON) not found (needed for scripts/check.py)'; exit 1; }
	@$(PYTHON) scripts/check.py


# Regenerates tests/check_baseline.json. Run this when a check's result is
# expected to change, and commit the result with the change that caused it — the
# diff of that file is the diff of the warning profile.
check-baseline:
	@$(PYTHON) tests/record_baseline.py


# ── benchmarks ────────────────────────────────────────────────────────────

# The memory harness: synthetic files of 4/16/64/256 MiB, opened through the
# real Doc path, with the Lua heap and RSS read before load, after load, after
# highlighting, and after close.
bench:
	@$(PYTHON) scripts/bench.py

# The full sweep includes 256 MiB, which takes minutes. `make bench` runs the
# same thing; this is the same target with the size list made explicit for a
# reader who wants to know what it is about to spend.
bench-save:
	@$(PYTHON) scripts/bench.py --save

bench-baseline:
	@$(PYTHON) tests/record_bench_baseline.py


# ── startup and idle CPU ──────────────────────────────────────────────────
#
# Runs the bare tree (core + fonts + themes, no plugins), because a plugin can
# change what startup means and the question here is what the runtime costs
# before anything is added to it. Needs `make bare` first; says so and exits
# non-zero if the tree is missing, rather than reporting NOT MEASURED and looking
# like a result.
runtime: bare
	@$(PYTHON) scripts/measure_runtime.py


# ── memory harness, on its own ────────────────────────────────────────────

# Just the load-and-release part, on a small file, as a quick answer to "is a
# document released when it is closed?" That question has a yes/no answer and
# the harness asserts it rather than leaving it to be read off a ratio.
mem:
	@$(PYTHON) scripts/bench.py --sizes 4
