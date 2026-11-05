# Contributing

Changes in this repository must stay within the Composition Root boundary:
dependency pins, build orchestration, packaging, process lifecycle, launch
configuration and release tooling. Editor behavior belongs in Kernel, Runtime,
Backend or Frontend.

## Verify

```sh
python3 scripts/deps.py
python3 scripts/check_boundaries.py
python3 scripts/build_stack.py
pipeline run check
psx check
gix doctor
```

Submit process-level or cross-component E2E for observable behavior. Do not add
unit-only tests as a substitute. For changes involving concurrent queues or
transport, run sanitizer-enabled jobs. Do not claim product memory benchmarks
until the real Kernel-backed edit/save workload is exercised.

Use Conventional Commits, focused diffs and immutable dependency revisions.
