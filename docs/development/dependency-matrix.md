# Dependency and delivery matrix

Component versions/revisions remain selected by the Registry Catalog and the Product Definitions, then recorded in the generated `registry-manifest.json`. `deps.lock` holds the separate immutable Kernel/logger SDK asset pin, the Registry consumer/development pins and developer tooling; it is not a second component-version resolver.

This table describes the current **hybrid developer/CI inventory**. It is not the normal consumer delivery policy: normal Product Definitions are resolved with `delivery_mode: artifact` and reject source-only Runtime/Frontend entries. The developer/CI path opts into `artifact-or-source` explicitly.

| Component/tool | Current selected identity | Current delivery in the CDIN development stack | Notes |
| --- | --- | --- | --- |
| Kernel | `1.2.1`, source revision `f4875b6eb59bd76878e7ff486b6114abd9bb1329` | Existing immutable GitHub Release SDK package | Five target archive hashes/sizes are in `[dependencies.kernel_sdk]`. Provides Kernel ABI `1.1.0`. No new Kernel packaging work is part of CDIN #122. |
| m-mdy-m/log.c | `0.1.0`, source commit `c9b53e9901dc7103eb50be282ae055fe16e98f9a` | Bundled in the existing Kernel 1.2.1 SDK package | Static library, header, pkg-config and CMake package config/targets are installed together with Kernel. |
| Backend | `1.2.1`, source revision `b6a54e43313add7e73399b040569874d30d32611` | Registry native `cmake-prefix-v1` artifact | Five target packages are declared by the existing Backend 1.2.1 metadata and selected by exact target tuple. |
| Runtime | `1.0.0-rc.2`, source revision `49f3ab78fc115cd453294de561790ca9881c31a2` | Source unit | Current Catalog metadata is source-only. The next publisher identity/RC3 still needs its immutable module Release and matching Catalog metadata. |
| Frontend TUI | `1.0.2`, source revision `5bbeac3e3301d34fc7ad7041dc8b369992cc8462` | Source unit | Current Catalog metadata is source-only; a separate Core/TUI package Release is still required. |
| Frontend GUI-SDL | `1.0.2`, source revision `5bbeac3e3301d34fc7ad7041dc8b369992cc8462` | Source unit | Selected as a separate Registry variant; a separate GUI-SDL package Release is still required. |
| Registry consumer executable | `0.1.0-dev`, source pin `cdcf86ed6a8788bf20fa0bcd821bb91242ba09a4` | Not consumable | The existing tag has incorrect architecture-to-binary mappings. Descriptor digest/size are intentionally absent, so normal acquisition fails closed. |
| Registry development source | `0.2.0-dev.1`, commit `ff317e458a57dd9d8b8a2be8f7439ba860c99f10` | Explicit developer/CI source build only | Separate from the consumer pin; this exact source contains the current artifact delivery support. |
| SDL3 | `3.4.16`, archive SHA-256 `7322236cd12090c3eb40b9728be4d49c76f66ad17d04369584d4ecad5cf77c68` | Source build for GUI-SDL development only | The SDK publisher implementation is merged, but the actual five-target SDK Release and digests are still missing. TUI never installs SDL3. |
| Pipeline | `79169afc4f9f74ee46c52be2bf6974f8544c7db1` | Local/CI task runner | Developer tooling only. |
| PSX | `e4f12e85725e1ebd44c7f3a4e18fcbaa893b30df` | Repository structure validation | Developer tooling only. |
| Gix | `9f0867923177cef3cd36d980cc2b356a35bee507` | Git branch workflow | Developer tooling only. |

## Target package pins

The exact Kernel SDK release assets, SHA-256 digests and byte sizes are recorded under `dependencies.kernel_sdk.assets` in `deps.lock` for Linux x86_64/ARM64, macOS x86_64/ARM64 and Windows x86_64 UCRT64. The package also provides the independently versioned logger SDK.

Backend 1.2.1's five exact native artifact descriptors and their target tuples are resolved from Registry's static Catalog. CDIN does not reproduce Backend URLs or hashes in a second table or code path; the Resolved Manifest records the selected artifact identity and staged package path.

## Compatibility and build checks

- Registry resolves the Backend dependency closure and contract graph before artifact selection.
- CDIN checks the Kernel SDK pin against the Manifest's Kernel package version and `org.cdin.kernel-abi` provider.
- Backend's exact target tuple must match the host; its selected artifact must be `native-development-package` / `cmake-prefix-v1`.
- The private install prefix merges Kernel/logger and Backend files only after symlink/special-file checks and collision preflight. Existing differing files are never overwritten.
- Runtime and Frontend remain source-delivered until their immutable package releases and Catalog metadata are published.
- SDL3 remains GUI-SDL-only; its source archive is a development/CI workaround, not the final consumer SDK flow.

## Readiness boundary

The Registry executable Release is still blocked by Registry #58. A real corrected Registry descriptor/tag/asset pin must be published before the ordinary binary bootstrap can run. Even after that, the product migration is incomplete until Runtime, Frontend and GUI-SDL SDK assets are published, verified, and consumed from a clean prefix. CDIN #122 remains open.