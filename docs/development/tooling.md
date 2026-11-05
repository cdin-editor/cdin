# Development tooling

- deps.lock is the immutable source of truth for component and tool revisions.
- scripts/deps.py checks out exactly those SHAs; floating branch names are not valid pins.
- pipeline.toml defines the task graph and pipeline run check is the standard local/CI entry point.
- psx.yml declares the expected repository topology; validate it with psx check.
- .gix/config defines feature/bugfix branches from main; validate with gix doctor.
- scripts/build_stack.py builds and tests logger, Kernel, Backend, Frontend and CDIN in dependency order.
- scripts/check_boundaries.py guards against copying component implementation into the Composition Root.

Use Conventional Commits and keep each change focused. Update deps.lock only with reviewed immutable SHAs.
