# Contributing

Changes in this repository must stay within the Composition Root boundary: dependency pins, build orchestration, packaging, process lifecycle, launch configuration and release tooling. Editor behavior belongs in Kernel, Runtime, Backend or Frontend.

Before changing an interface, read [AGENTS.md](AGENTS.md), inspect the relevant component's public API and check the latest accepted Spec requirements. Record ownership or contract conflicts in the [architecture audit](docs/architecture/audit.md).

## Verify

Install the native build prerequisites from the [Developer guide](docs/development.md), then run:

```sh
psx check
gix doctor
pipeline validate
pipeline run check
```

For a direct full-stack build without Pipeline:

```sh
make stack
```

Submit executable-level or cross-component E2E for observable behavior. Do not add isolated Composition Root tests as a substitute for real product workflows. For changes involving memory, queues, concurrency or transport, run the supported sanitizer jobs.

Do not claim that interactive editing, memory benchmarks or platform support is complete unless the corresponding real workflow was executed. Record unavailable checks as NOT RUN, with the reason.

Use focused commits, Conventional Commit subjects and immutable dependency revisions. Do not change the website here; it is maintained in https://github.com/cdin-editor/cdin-editor.github.io.
