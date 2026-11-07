# Dependency matrix

Component versions and source revisions are selected by the Registry Product Definition and recorded in the generated `registry-manifest.json`. `deps.lock` now pins only non-component dependencies and build tools; it is not a second component lockfile.

| Component/tool | Selected version | Source revision / pin | Role |
| --- | --- | --- | --- |
| Kernel | 1.2.1 | `f4875b6eb59bd76878e7ff486b6114abd9bb1329` | Backend-owned document engine; provides Kernel ABI 1.1.0. |
| Runtime | 1.0.0-rc.1 | `d2acb6f174edf127c3bf59e8e5d4aedcbef0d490` | Backend-hosted Lua policy; requires Runtime Host API 1.0.0. |
| Backend | 1.2.0 | `c0a88090460929796bd7cd731966f04115256910` | Depends on Kernel and Runtime; provides Runtime Host API 1.0.0 and Frontend Protocol 1.0.0. |
| Frontend TUI | 1.0.0 | `1373715c23eb965445caa926de3a99d9c0246f81` | Protocol 1.0.0 client and terminal adapter. |
| Frontend GUI-SDL | 1.0.0 | `1373715c23eb965445caa926de3a99d9c0246f81` | Protocol 1.0.0 client and SDL adapter; selected as a separate Registry variant. |
| Registry | 0.1.0-dev | `9704b962732109f61cf96632e2edcbb0ee4a68a4` | Build-time resolver, source collector, Manifest producer and versioned Catalog snapshot; never linked into CDIN. |
| m-mdy-m/log.c | 0.1.0 | `c9b53e9901dc7103eb50be282ae055fe16e98f9a` | CDIN-owned diagnostics dependency. |
| SDL3 | 3.4.16 | SHA-256 `7322236cd12090c3eb40b9728be4d49c76f66ad17d04369584d4ecad5cf77c68` | Checksum-pinned source archive for GUI-SDL. |
| Pipeline | — | `79169afc4f9f74ee46c52be2bf6974f8544c7db1` | Local and CI task execution. |
| PSX | — | `e4f12e85725e1ebd44c7f3a4e18fcbaa893b30df` | Project structure validation. |
| Gix | — | `9f0867923177cef3cd36d980cc2b356a35bee507` | Git branch workflow. |

The four component revisions above are discovered from component-owned immutable Release Metadata documents referenced by the Registry Catalog snapshot at `catalogs/cdin-components/catalog-index.json`. CDIN pins the Registry commit (and therefore this Catalog snapshot) in `deps.lock`. The generated Registry Manifest remains authoritative for an individual prepared build.

## Compatibility checks

- Registry validates the Product Definition, Catalog Index and every referenced Component Release Metadata document against the versioned Registry contracts.
- Backend's release declares its Kernel and Runtime dependencies; Registry resolves them transitively rather than CDIN independently selecting them.
- Kernel ABI 1.1.0, Runtime Host API 1.0.0 and Frontend Protocol 1.0.0 are represented as explicit provider/requirement contracts.
- CDIN checks the Backend runtime/header version and Backend/Frontend Protocol major/minor values at build or startup.
- The stack lifecycle smoke compares the Runtime-reported package version with the selected Runtime version in the Resolved Manifest.
- The GUI-SDL and TUI profiles select separate Frontend variants while keeping the same public Protocol contract.

## Transitional policy

The current Runtime release is `1.0.0-rc.1`. Both Product Definitions therefore set `allow_prerelease: true` so Registry can resolve the exact currently integrated candidate. This must be changed to `false` after a stable Runtime release and corresponding Catalog entry are available.

The Registry executable itself is currently `0.1.0-dev`; it is pinned to an immutable source commit and built as a host tool. It is not a production component package and does not enter the application runtime.

## Verification status

The branch now contains the component-owned metadata references in Registry's Catalog snapshot, TUI and GUI-SDL Product Definitions, pinned Registry CLI orchestration, Manifest replay verification and product-level workspace assertions. These are implementation changes, not yet a claim of green CI. The new workflow must pass the current Linux/macOS/Windows stack matrix and sanitizer job before the Registry handoff is marked verified.

See [Registry integration](registry.md) and [Integration status](integration-status.md) for the complete workflow and remaining product gates.
