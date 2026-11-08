# CDIN documentation

CDIN is the composition root for the editor components. These guides describe the responsibilities and behavior implemented in this repository. Cross-component contracts remain defined by the [CDIN Specification](https://github.com/cdin-editor/spec).

## Start here

| If you want to... | Read |
| --- | --- |
| Understand what CDIN does today and run its CLI | [User guide](user-guide.md) |
| Build and install a local development stack | [Installation](installation.md) |
| Understand component ownership and startup/shutdown | [Architecture](architecture.md) |
| Change the Composition Root or run CI checks | [Developer guide](development.md) |

## Architecture and requirements

| Document | Contents |
| --- | --- |
| [Architecture audit](architecture/audit.md) | Current inventory, ownership findings and implementation status. |
| [Composition model](architecture/composition.md) | The executable's current composition path and boundaries. |
| [Rewrite decision](architecture/rewrite-decision.md) | Owner-approved replacement of the legacy monolith. |
| [Spec traceability](architecture/traceability.md) | Requirement IDs, source links and verification state. |

## Development and release

| Document | Contents |
| --- | --- |
| [Dependency matrix](development/dependency-matrix.md) | Immutable revisions and declared package contracts. |
| [Registry integration](development/registry.md) | Product Definitions, Catalog Index, immutable component metadata and workspace handoff. |
| [Integration status](development/integration-status.md) | Implemented behavior and outstanding release gates. |
| [Tooling](development/tooling.md) | Pipeline, PSX, Gix and dependency checkout. |
| [E2E plan](../tests/e2e/README.md) | Executable-level coverage and missing product workflows. |
| [Resource benchmarks](../tests/bench/README.md) | Measurement plan; no product benchmark is claimed yet. |

## Documentation rules

The code and public component contracts are authoritative. A feature described in a plan or test guide is not evidence that it is implemented. Each status must distinguish IMPLEMENTED, PARTIAL, NOT IMPLEMENTED, NOT VERIFIED and NOT RUN.
