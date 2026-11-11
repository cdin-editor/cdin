"""Unit tests for the Registry toolchain bootstrap environment."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.build_stack import (
    stage_cmake_prefix,
    stage_kernel_sdk_prefix,
    verify_kernel_sdk_manifest_contract,
)
from scripts.configure import selected_package_version
from scripts.deps import (
    SDKBootstrapError,
    install_sdk_atomically,
    parse_kernel_abi,
)
from scripts.registry import (
    create_effective_product_definition,
    detect_target_tuple,
    registry_go_environment,
)


class RegistryGoEnvironmentTests(unittest.TestCase):
    def test_uses_canonical_proxy_and_auto_toolchain_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            environment = registry_go_environment()
        self.assertEqual(
            environment["GOPROXY"], "https://proxy.golang.org,direct"
        )
        self.assertEqual(environment["GOTOOLCHAIN"], "auto")

    def test_allows_explicit_proxy_override(self) -> None:
        with patch.dict(
            os.environ,
            {"CDIN_GOPROXY": "https://proxy.example.invalid"},
            clear=True,
        ):
            environment = registry_go_environment()
        self.assertEqual(environment["GOPROXY"], "https://proxy.example.invalid")

    def test_preserves_other_environment_variables(self) -> None:
        with patch.dict(
            os.environ,
            {"CI": "true", "CDIN_GOPROXY": "direct"},
            clear=True,
        ):
            environment = registry_go_environment()
        self.assertEqual(environment["CI"], "true")
        self.assertEqual(environment["GOPROXY"], "direct")


class ConfigureManifestTests(unittest.TestCase):
    def test_reads_the_exact_selected_component_variant(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        payload = {
            "components": [
                {"component_id": "frontend", "variant": "tui", "version": "1.0.2"},
                {"component_id": "frontend", "variant": "gui-sdl", "version": "1.0.2"},
                {"component_id": "backend", "variant": "default", "version": "1.2.0"},
            ]
        }
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "registry-manifest.json"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(
                selected_package_version(manifest, "frontend", "gui-sdl"),
                "1.0.2",
            )

    def test_rejects_missing_or_ambiguous_component_variants(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "registry-manifest.json"
            manifest.write_text(
                json.dumps({
                    "components": [
                        {"component_id": "backend", "variant": "default", "version": "1.2.0"},
                        {"component_id": "backend", "variant": "default", "version": "1.2.1"},
                    ]
                }),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                selected_package_version(manifest, "backend", "default")

    def test_rejects_a_missing_manifest(self) -> None:
        from pathlib import Path

        with self.assertRaises(FileNotFoundError):
            selected_package_version(
                Path("missing-registry-manifest.json"), "backend", "default"
            )


class RegistryMakeTargetTests(unittest.TestCase):
    def test_normal_stack_uses_pinned_registry_binary(self) -> None:
        makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text(encoding="utf-8")
        self.assertRegex(makefile, r"(?m)^stack: deps registry$")
        self.assertRegex(makefile, r"(?m)^stack-gui: deps registry-gui$")
        self.assertNotRegex(makefile, r"(?m)^stack:.*registry-dev")
        self.assertNotRegex(makefile, r"(?m)^stack-gui:.*registry-gui-dev")

    def test_source_build_is_explicit_for_developer_stack_targets(self) -> None:
        root = Path(__file__).resolve().parents[1]
        makefile = (root / "Makefile").read_text(encoding="utf-8")
        stack_script = (root / "scripts" / "build_stack.py").read_text(encoding="utf-8")
        pipeline = (root / "pipeline.toml").read_text(encoding="utf-8")

        self.assertRegex(makefile, r"(?m)^stack-dev: registry-dev$")
        self.assertRegex(makefile, r"(?m)^stack-gui-dev: registry-gui-dev$")
        self.assertIn("--registry-source-build", makefile)
        self.assertIn('parser.add_argument(\n        "--registry-source-build"', stack_script)
        self.assertIn('if args.registry_source_build:', stack_script)
        # CI is allowed to test the explicit source build; normal Make targets are not.
        self.assertIn('"scripts/build_stack.py", "--registry-source-build"', pipeline)



class RegistryPinSeparationTests(unittest.TestCase):
    def test_consumer_release_and_developer_source_pins_are_separate(self) -> None:
        from scripts.registry import registry_pin
        lock = Path(__file__).resolve().parents[1] / "deps.lock"
        import tomllib

        data = tomllib.loads(lock.read_text(encoding="utf-8"))
        consumer = data["tooling"]["registry"]
        development = consumer["development"]
        self.assertEqual(consumer["release_tag"], "v0.1.0-dev")
        self.assertNotIn("release_descriptor_sha256", consumer)
        self.assertNotIn("release_descriptor_size", consumer)
        self.assertEqual(
            registry_pin(),
            ("https://github.com/cdin-editor/registry.git", "cdcf86ed6a8788bf20fa0bcd821bb91242ba09a4"),
        )
        self.assertEqual(
            registry_pin(development=True),
            ("https://github.com/cdin-editor/registry.git", "ff317e458a57dd9d8b8a2be8f7439ba860c99f10"),
        )
        self.assertNotEqual(consumer["revision"], development["revision"])




class RegistryTargetDetectionTests(unittest.TestCase):
    def test_linux_target_uses_supported_glibc_baseline(self) -> None:
        self.assertEqual(
            detect_target_tuple(
                system="Linux", machine="x86_64", libc=("glibc", "2.39")
            ),
            {"os": "linux", "architecture": "x86_64", "abi": "gnu-glibc-2.39"},
        )
        self.assertEqual(
            detect_target_tuple(
                system="Linux", machine="aarch64", libc=("glibc", "2.40")
            ),
            {"os": "linux", "architecture": "arm64", "abi": "gnu-glibc-2.39"},
        )

    def test_rejects_old_or_non_gnu_linux_runtime(self) -> None:
        for libc in (("glibc", "2.38"), ("musl", "1.2.5"), ("", "")):
            with self.subTest(libc=libc):
                with self.assertRaises(RuntimeError):
                    detect_target_tuple(system="Linux", machine="x86_64", libc=libc)

    def test_macos_target_requires_version_fifteen_or_newer(self) -> None:
        self.assertEqual(
            detect_target_tuple(system="Darwin", machine="arm64", mac_version="15.7.1"),
            {"os": "darwin", "architecture": "arm64", "abi": "macos-15"},
        )
        with self.assertRaisesRegex(RuntimeError, "macOS 14"):
            detect_target_tuple(system="Darwin", machine="x86_64", mac_version="14.7")

    def test_windows_target_requires_ucrt64_and_x86_64(self) -> None:
        self.assertEqual(
            detect_target_tuple(
                system="Windows", machine="AMD64", msystem="UCRT64"
            ),
            {"os": "windows", "architecture": "x86_64", "abi": "windows-ucrt64"},
        )
        with self.assertRaisesRegex(RuntimeError, "UCRT64"):
            detect_target_tuple(system="Windows", machine="AMD64", msystem="MINGW64")
        with self.assertRaisesRegex(RuntimeError, "only Windows x86_64"):
            detect_target_tuple(system="Windows", machine="arm64", msystem="UCRT64")

    def test_unsupported_system_and_architecture_fail_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "operating system"):
            detect_target_tuple(system="FreeBSD", machine="x86_64")
        with self.assertRaisesRegex(RuntimeError, "architecture"):
            detect_target_tuple(system="Linux", machine="riscv64", libc=("glibc", "2.39"))


class EffectiveProductDefinitionTests(unittest.TestCase):
    def test_creates_host_specific_copy_without_mutating_checked_in_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "product-definition.tui.yaml"
            generated = root / "temporary" / "product-definition.yaml"
            source = (
                'schema_version: "1.0.0"\n'
                "product:\n"
                "  id: com.cdin.editor\n"
                "  name: CDIN\n"
                "components:\n"
                "  - component_id: backend\n"
                '    version_constraint: "1.2.1"\n'
            )
            original.write_text(source, encoding="utf-8")

            result = create_effective_product_definition(
                original,
                generated,
                {"os": "linux", "architecture": "arm64", "abi": "gnu-glibc-2.39"},
            )

            self.assertEqual(result, generated)
            self.assertEqual(original.read_text(encoding="utf-8"), source)
            generated_text = generated.read_text(encoding="utf-8")
            self.assertIn('schema_version: "1.1.0"', generated_text)
            self.assertIn("delivery_mode: artifact-or-source", generated_text)
            self.assertIn("os: linux", generated_text)
            self.assertIn("architecture: arm64", generated_text)
            self.assertIn("abi: gnu-glibc-2.39", generated_text)

    def test_rejects_existing_resolution_block_and_unknown_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "product.yaml"
            destination = root / "generated.yaml"
            source.write_text(
                'schema_version: "1.0.0"\ncomponents: []\nresolution:\n  delivery_mode: source\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "already declares resolution"):
                create_effective_product_definition(
                    source, destination,
                    {"os": "linux", "architecture": "x86_64", "abi": "gnu-glibc-2.39"},
                )
            source.write_text('schema_version: "2.0.0"\ncomponents: []\n', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "unsupported Product Definition schema"):
                create_effective_product_definition(
                    source, destination,
                    {"os": "linux", "architecture": "x86_64", "abi": "gnu-glibc-2.39"},
                )


class BackendArtifactStagingTests(unittest.TestCase):
    REQUIRED_FILES = {
        "include/cdin/backend.h": b"backend header",
        "lib/libcdin_backend.a": b"backend archive",
        "lib/libcdin_backend_services.a": b"backend services archive",
        "lib/libcdin_protocol.a": b"protocol archive",
        "lib/cmake/cdinBackend/cdinBackendConfig.cmake": b"cmake config",
        "lib/cmake/cdinBackend/cdinBackendTargets.cmake": b"cmake targets",
        "lib/pkgconfig/cdin-backend.pc": b"backend pkgconfig",
        "lib/pkgconfig/cdin-backend-services.pc": b"backend services pkgconfig",
        "lib/pkgconfig/cdin-protocol.pc": b"protocol pkgconfig",
    }

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.package = self.root / "registry-package"

        for relative, payload in self.REQUIRED_FILES.items():
            path = self.package / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)

        docs = self.package / "share" / "cdin-backend" / "BUILD-INFO.txt"
        docs.parent.mkdir(parents=True, exist_ok=True)
        docs.write_bytes(b"Backend 1.2.1 package provenance")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _prepare_existing_component_prefix(self) -> Path:
        prefix = self.root / "install-prefix"
        files = {
            "include/cdin/kernel.h": b"existing kernel header",
            "lib/libcdin_kernel.a": b"existing kernel library",
            "lib/pkgconfig/cdin-kernel.pc": b"kernel pkgconfig",
            "lib/pkgconfig/m-mdy-m-log.pc": b"logger pkgconfig",
        }
        for relative, payload in files.items():
            path = prefix / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        return prefix

    def test_merges_backend_package_without_overwriting_kernel_or_logger(self) -> None:
        prefix = self._prepare_existing_component_prefix()

        stage_cmake_prefix(self.package, prefix)

        for relative, payload in self.REQUIRED_FILES.items():
            self.assertEqual((prefix / relative).read_bytes(), payload)
        self.assertEqual(
            (prefix / "include/cdin/kernel.h").read_bytes(),
            b"existing kernel header",
        )
        self.assertEqual(
            (prefix / "lib/pkgconfig/cdin-kernel.pc").read_bytes(),
            b"kernel pkgconfig",
        )
        self.assertEqual(
            (prefix / "lib/pkgconfig/m-mdy-m-log.pc").read_bytes(),
            b"logger pkgconfig",
        )
        self.assertEqual(
            (prefix / "share/cdin-backend/BUILD-INFO.txt").read_bytes(),
            b"Backend 1.2.1 package provenance",
        )

    def test_collision_is_detected_before_any_package_file_is_copied(self) -> None:
        prefix = self.root / "install-prefix"
        collision = prefix / "lib" / "libcdin_backend.a"
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_bytes(b"pre-existing file")

        with self.assertRaisesRegex(RuntimeError, "overwrite an existing staged file"):
            stage_cmake_prefix(self.package, prefix)

        self.assertEqual(collision.read_bytes(), b"pre-existing file")
        self.assertFalse((prefix / "include/cdin/backend.h").exists())

    def test_missing_required_package_file_fails_closed(self) -> None:
        (self.package / "lib" / "libcdin_protocol.a").unlink()
        with self.assertRaisesRegex(RuntimeError, "missing a regular required file"):
            stage_cmake_prefix(self.package, self.root / "install-prefix")
        self.assertFalse((self.root / "install-prefix").exists())

    @unittest.skipIf(os.name == "nt", "POSIX symlink creation may require elevated Windows privileges")
    def test_symlink_in_registry_package_is_rejected(self) -> None:
        outside = self.root / "outside"
        outside.write_bytes(b"outside")
        link = self.package / "lib" / "escape"
        link.symlink_to(outside)

        with self.assertRaisesRegex(RuntimeError, "symlink/special file"):
            stage_cmake_prefix(self.package, self.root / "install-prefix")

        self.assertFalse((self.root / "install-prefix" / "include/cdin/backend.h").exists())





class KernelSDKCompositionTests(unittest.TestCase):
    def test_kernel_header_abi_parser_uses_public_three_part_constants(self) -> None:
        header = (
            "#define CDIN_KERNEL_ABI_MAJOR 1u\n"
            "#define CDIN_KERNEL_ABI_MINOR 1u\n"
            "#define CDIN_KERNEL_ABI_PATCH 0u\n"
        )
        self.assertEqual(parse_kernel_abi(header), "1.1.0")
        with self.assertRaisesRegex(SDKBootstrapError, "missing ABI PATCH"):
            parse_kernel_abi(
                "#define CDIN_KERNEL_ABI_MAJOR 1u\n"
                "#define CDIN_KERNEL_ABI_MINOR 1u\n"
            )


    def test_kernel_sdk_version_and_abi_must_match_registry_manifest(self) -> None:
        manifest = {
            "components": [
                {
                    "component_id": "kernel",
                    "variant": "default",
                    "version": "1.2.1",
                    "contracts": {
                        "provides": [
                            {"contract_id": "org.cdin.kernel-abi", "version": "1.1.0"}
                        ]
                    },
                }
            ]
        }
        pin = {"version": "1.2.1", "kernel_abi": "1.1.0"}
        verify_kernel_sdk_manifest_contract(manifest, pin)

        wrong_version = {"version": "1.2.0", "kernel_abi": "1.1.0"}
        with self.assertRaisesRegex(RuntimeError, "does not match Registry Kernel version"):
            verify_kernel_sdk_manifest_contract(manifest, wrong_version)

        wrong_abi = {"version": "1.2.1", "kernel_abi": "1.0.0"}
        with self.assertRaisesRegex(RuntimeError, "does not match Registry Kernel ABI"):
            verify_kernel_sdk_manifest_contract(manifest, wrong_abi)

    def test_kernel_sdk_manifest_requires_one_default_kernel(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "exactly one Kernel default component"):
            verify_kernel_sdk_manifest_contract(
                {"components": []},
                {"version": "1.2.1", "kernel_abi": "1.1.0"},
            )

    def test_kernel_logger_sdk_prefix_stages_all_cmake_and_pkgconfig_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sdk = root / "sdk"
            prefix = root / "install"
            files = {
                "include/cdin/kernel.h": b"kernel header",
                "include/m-mdy-m/log.h": b"logger header",
                "lib/libcdin_kernel.a": b"kernel static library",
                "lib/libm-mdy-m-log.a": b"logger static library",
                "lib/pkgconfig/cdin-kernel.pc": b"kernel pkgconfig",
                "lib/pkgconfig/m-mdy-m-log.pc": b"logger pkgconfig",
                "lib/cmake/m-mdy-m-log/m-mdy-m-log-config.cmake": b"logger cmake config",
                "lib/cmake/m-mdy-m-log/m-mdy-m-log-config-version.cmake": b"logger cmake version",
                "lib/cmake/m-mdy-m-log/m-mdy-m-log-targets.cmake": b"logger imported targets",
            }
            for relative, payload in files.items():
                path = sdk / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)

            stage_kernel_sdk_prefix(sdk, prefix)

            for relative, payload in files.items():
                self.assertEqual((prefix / relative).read_bytes(), payload)

    def test_kernel_sdk_and_backend_install_prefixes_compose_together(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sdk = root / "kernel-sdk"
            backend = root / "backend"
            prefix = root / "install"
            sdk_files = {
                "include/cdin/kernel.h": b"kernel header",
                "include/m-mdy-m/log.h": b"logger header",
                "lib/libcdin_kernel.a": b"kernel static library",
                "lib/libm-mdy-m-log.a": b"logger static library",
                "lib/pkgconfig/cdin-kernel.pc": b"kernel pkgconfig",
                "lib/pkgconfig/m-mdy-m-log.pc": b"logger pkgconfig",
                "lib/cmake/m-mdy-m-log/m-mdy-m-log-config.cmake": b"logger cmake config",
                "lib/cmake/m-mdy-m-log/m-mdy-m-log-config-version.cmake": b"logger cmake version",
                "lib/cmake/m-mdy-m-log/m-mdy-m-log-targets.cmake": b"logger targets",
            }
            for relative, payload in sdk_files.items():
                path = sdk / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            backend_files = {
                "include/cdin/backend.h": b"backend header",
                "lib/libcdin_backend.a": b"backend archive",
                "lib/libcdin_backend_services.a": b"backend services",
                "lib/libcdin_protocol.a": b"protocol archive",
                "lib/cmake/cdinBackend/cdinBackendConfig.cmake": b"backend config",
                "lib/pkgconfig/cdin-backend.pc": b"backend pkgconfig",
                "lib/pkgconfig/cdin-backend-services.pc": b"backend services pkgconfig",
                "lib/pkgconfig/cdin-protocol.pc": b"protocol pkgconfig",
            }
            for relative, payload in backend_files.items():
                path = backend / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)

            stage_kernel_sdk_prefix(sdk, prefix)
            stage_cmake_prefix(backend, prefix)

            for relative, payload in {**sdk_files, **backend_files}.items():
                self.assertEqual((prefix / relative).read_bytes(), payload)



class KernelSDKAtomicInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.package = self.root / "package"
        self.package.mkdir()
        self.destination = self.root / "sdk"
        self.destination.mkdir()
        (self.destination / "marker.txt").write_text("previous-sdk", encoding="utf-8")
        self.pin = {"version": "1.2.1", "kernel_abi": "1.1.0", "logger_version": "0.1.0"}

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_failed_installer_keeps_the_existing_sdk_prefix_unchanged(self) -> None:
        def fail_after_partial_install(package_root: Path, prefix: Path) -> None:
            prefix.mkdir(parents=True)
            (prefix / "marker.txt").write_text("partial-new-sdk", encoding="utf-8")
            raise SDKBootstrapError("simulated installer failure")

        with patch("scripts.deps.install_package", side_effect=fail_after_partial_install), \
             patch("scripts.deps.verify_installed") as verify:
            with self.assertRaisesRegex(SDKBootstrapError, "simulated installer failure"):
                install_sdk_atomically(self.package, self.pin, self.destination)

        self.assertEqual(
            (self.destination / "marker.txt").read_text(encoding="utf-8"),
            "previous-sdk",
        )
        self.assertFalse(self.destination.with_name("sdk.previous").exists())
        self.assertFalse(list(self.root.glob("sdk.staging-*")))
        verify.assert_not_called()

    def test_failed_staged_verification_keeps_the_existing_sdk_prefix_unchanged(self) -> None:
        def install_new(package_root: Path, prefix: Path) -> None:
            prefix.mkdir(parents=True)
            (prefix / "marker.txt").write_text("new-sdk", encoding="utf-8")

        def reject_staged(pin: dict, prefix: Path) -> None:
            self.assertNotEqual(prefix, self.destination)
            self.assertEqual((prefix / "marker.txt").read_text(encoding="utf-8"), "new-sdk")
            raise SDKBootstrapError("simulated verification failure")

        with patch("scripts.deps.install_package", side_effect=install_new), \
             patch("scripts.deps.verify_installed", side_effect=reject_staged):
            with self.assertRaisesRegex(SDKBootstrapError, "simulated verification failure"):
                install_sdk_atomically(self.package, self.pin, self.destination)

        self.assertEqual(
            (self.destination / "marker.txt").read_text(encoding="utf-8"),
            "previous-sdk",
        )
        self.assertFalse(self.destination.with_name("sdk.previous").exists())
        self.assertFalse(list(self.root.glob("sdk.staging-*")))

    def test_verified_sdk_replaces_old_prefix_and_removes_backup(self) -> None:
        def install_new(package_root: Path, prefix: Path) -> None:
            prefix.mkdir(parents=True)
            (prefix / "marker.txt").write_text("new-sdk", encoding="utf-8")

        def verify_new(pin: dict, prefix: Path) -> None:
            self.assertNotEqual(prefix, self.destination)
            self.assertEqual((prefix / "marker.txt").read_text(encoding="utf-8"), "new-sdk")

        with patch("scripts.deps.install_package", side_effect=install_new), \
             patch("scripts.deps.verify_installed", side_effect=verify_new):
            install_sdk_atomically(self.package, self.pin, self.destination)

        self.assertEqual(
            (self.destination / "marker.txt").read_text(encoding="utf-8"),
            "new-sdk",
        )
        self.assertFalse(self.destination.with_name("sdk.previous").exists())
        self.assertFalse(list(self.root.glob("sdk.staging-*")))



if __name__ == "__main__":
    unittest.main()
