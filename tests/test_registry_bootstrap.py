"""Unit tests for the Registry toolchain bootstrap environment."""
from __future__ import annotations

import hashlib
import json
import os
import runpy
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from scripts.build_stack import (
    runtime_module_package_root,
    runtime_root_for_stack,
    stage_cmake_prefix,
    stage_frontend_variant_prefix,
    stage_kernel_sdk_prefix,
    verify_environment_sdk_contract,
)
from scripts.configure import selected_package_version
_REGISTRY_E2E = runpy.run_path(
    str(Path(__file__).resolve().parent / "e2e" / "test_registry_workspace.py")
)
verify_runtime_package = _REGISTRY_E2E["verify_runtime_package"]
verify_frontend_artifact = _REGISTRY_E2E["verify_frontend_artifact"]
FRONTEND_PACKAGE_FILES = _REGISTRY_E2E["FRONTEND_PACKAGE_FILES"]
from scripts.deps import (
    CACHE as SDK_CACHE,
    SDKBootstrapError,
    _GitHubAPIRedirectHandler,
    install_sdk_atomically,
    parse_kernel_abi,
    parse_build_info,
    download_asset,
    fetch_github_json,
    verify_release_asset_identity,
    load_pin,
)
from scripts.registry import (
    create_effective_product_definition,
    detect_target_tuple,
    registry_go_environment,
)




class KernelSDKAPIRedirectTests(unittest.TestCase):
    def test_rejects_release_identity_api_redirect_to_another_host(self) -> None:
        handler = _GitHubAPIRedirectHandler()
        request = urllib.request.Request(
            "https://api.github.com/repos/cdin-editor/kernel/releases/tags/v1.2.1"
        )
        with self.assertRaisesRegex(SDKBootstrapError, "left the trusted API origin"):
            handler.redirect_request(
                request, None, 302, "Found", {}, "https://example.invalid/redirect"
            )

    def test_rejects_malformed_api_redirect_port(self) -> None:
        handler = _GitHubAPIRedirectHandler()
        request = urllib.request.Request(
            "https://api.github.com/repos/cdin-editor/kernel/releases/tags/v1.2.1"
        )
        with self.assertRaisesRegex(SDKBootstrapError, "invalid port"):
            handler.redirect_request(
                request, None, 302, "Found", {}, "https://api.github.com:not-a-port/redirect"
            )


class KernelSDKReleasePinTests(unittest.TestCase):

    def test_repository_lock_pins_the_published_kernel_123_release_assets(self) -> None:
        pin = load_pin()
        self.assertEqual(pin["repository"], "https://github.com/cdin-editor/kernel")
        self.assertEqual(pin["tag"], "v1.2.3")
        self.assertEqual(pin["version"], "1.2.3")
        self.assertEqual(pin["revision"], "2fb09f52dc1a9963cf358ec54d584c520e174e67")
        self.assertEqual(pin["kernel_abi"], "1.1.0")
        self.assertEqual(pin["logger_version"], "0.1.0")
        expected = {
            "linux-x86_64": ("cdin-kernel-1.2.3-linux-x86_64.tar.gz", 381038, "48a82eb7f4c1fac57c7661f070c1338eb17c10d709eff0d87bb0229b87e46013"),
            "linux-arm64": ("cdin-kernel-1.2.3-linux-arm64.tar.gz", 388521, "9da597d5109e5280d78b1f9c18f68bb10db3d87d64c973bffedbceffbed52bc6"),
            "macos-x86_64": ("cdin-kernel-1.2.3-macos-x86_64.tar.gz", 346687, "e2ae0ea23e58f5a2210ad19a20ae99f2cf3febb0e8b0f714917beb7f8fa768a3"),
            "macos-arm64": ("cdin-kernel-1.2.3-macos-arm64.tar.gz", 342015, "8a4ddece6db4f0ed48657b2f7bf64edf1137fa9bb6d09b0b8f2908bb0d450fea"),
            "windows-x86_64": ("cdin-kernel-1.2.3-windows-x86_64.zip", 309735, "d0ced8272c80c1e5df886441c67493a25cca0e3a95a7c0e81be515282cb6364a"),
        }
        self.assertEqual(set(pin["assets"]), set(expected))
        for target, (filename, size, digest) in expected.items():
            with self.subTest(target=target):
                asset = pin["assets"][target]
                self.assertEqual(asset["file_name"], filename)
                self.assertEqual(asset["size_bytes"], size)
                self.assertEqual(asset["sha256"], digest)
                self.assertEqual(asset["format"], "zip" if target.startswith("windows-") else "tar.gz")

    def test_github_api_uses_the_workflow_token_when_available(self) -> None:
        requested = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return "https://api.github.com/repos/cdin-editor/kernel/releases/tags/v1.2.1"

            def read(self, _limit: int) -> bytes:
                return b'{"tag_name":"v1.2.1"}'

        class FakeOpener:
            def open(self, request, timeout: int):
                requested["authorization"] = request.get_header("Authorization")
                requested["timeout"] = timeout
                return FakeResponse()

        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghs-test-token"}, clear=True), \
             patch("scripts.deps.urllib.request.build_opener", return_value=FakeOpener()):
            payload = fetch_github_json(
                "https://api.github.com/repos/cdin-editor/kernel/releases/tags/v1.2.1"
            )

        self.assertEqual(payload["tag_name"], "v1.2.1")
        self.assertEqual(requested["authorization"], "Bearer ghs-test-token")
        self.assertEqual(requested["timeout"], 30)


    revision = "f4875b6eb59bd76878e7ff486b6114abd9bb1329"
    tag_object = "a" * 40
    asset = {
        "file_name": "cdin-kernel-1.2.1-linux-x86_64.tar.gz",
        "size_bytes": 268126,
        "sha256": "05779c5a23a24b3a5cb4e978d803f8e4bd81c73dbf5ba2b47e36b34ed0ddda21",
    }

    def setUp(self) -> None:
        self.pin = {
            "repository": "https://github.com/cdin-editor/kernel",
            "tag": "v1.2.1",
            "version": "1.2.1",
            "revision": self.revision,
        }

    def _api_responses(self, *, commit: str | None = None, digest: str | None = None):
        commit = commit or self.revision
        digest = digest or self.asset["sha256"]
        release = {
            "tag_name": "v1.2.1",
            "draft": False,
            "prerelease": False,
            "assets": [{
                "name": self.asset["file_name"],
                "size": self.asset["size_bytes"],
                "digest": "sha256:" + digest,
            }],
        }

        def fetch(url: str) -> dict:
            if url.endswith("/releases/tags/v1.2.1"):
                return release
            if url.endswith("/git/ref/tags/v1.2.1"):
                return {"object": {"type": "tag", "sha": self.tag_object}}
            if url.endswith("/git/tags/" + self.tag_object):
                return {
                    "sha": self.tag_object,
                    "object": {"type": "commit", "sha": commit},
                }
            raise AssertionError(f"unexpected GitHub API URL: {url}")

        return fetch

    def test_verifies_annotated_tag_commit_and_github_asset_digest_size(self) -> None:
        with patch(
            "scripts.deps.fetch_github_json",
            side_effect=self._api_responses(),
        ):
            verify_release_asset_identity(self.pin, self.asset)

    def test_rejects_tag_resolving_to_a_different_source_commit(self) -> None:
        with patch(
            "scripts.deps.fetch_github_json",
            side_effect=self._api_responses(commit="0" * 40),
        ):
            with self.assertRaisesRegex(SDKBootstrapError, "tag moved or mismatched"):
                verify_release_asset_identity(self.pin, self.asset)

    def test_rejects_github_asset_digest_that_differs_from_lock(self) -> None:
        with patch(
            "scripts.deps.fetch_github_json",
            side_effect=self._api_responses(digest="0" * 64),
        ):
            with self.assertRaisesRegex(SDKBootstrapError, "digest differs from deps.lock"):
                verify_release_asset_identity(self.pin, self.asset)


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
        self.assertIn('registry_command.extend(("--source-build", "--developer-source-components"))', stack_script)
        self.assertIn('for tool in ("cmake", "make", "pkg-config"):', stack_script)
        self.assertIn('if args.registry_source_build and shutil.which("git") is None:', stack_script)
        self.assertNotIn('for tool in ("git", "cmake", "make", "pkg-config"):', stack_script)
        self.assertIn("--source-build --developer-source-components", makefile)
        # CI is allowed to test the explicit source build; normal Make targets are not.
        self.assertIn('"scripts/registry.py", "--source-build", "--developer-source-components"', pipeline)
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
        self.assertEqual(development["version"], "0.2.0-dev.3")
        self.assertEqual(
            registry_pin(development=True),
            ("https://github.com/cdin-editor/registry.git", "c30ab313638a53d82b1bc63e67af90b1e111551d"),
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
            root = Path(temporary).resolve()
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
                delivery_mode="artifact-or-source",
            )

            self.assertEqual(result, generated)
            self.assertEqual(original.read_text(encoding="utf-8"), source)
            generated_text = generated.read_text(encoding="utf-8")
            self.assertIn('schema_version: "1.1.0"', generated_text)
            self.assertIn("delivery_mode: artifact-or-source", generated_text)
            self.assertIn("os: linux", generated_text)
            self.assertIn("architecture: arm64", generated_text)
            self.assertIn("abi: gnu-glibc-2.39", generated_text)


    def test_normal_product_resolution_is_artifact_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original = root / "product-definition.tui.yaml"
            generated = root / "normal" / "product-definition.yaml"
            original.write_text(
                'schema_version: "1.0.0"\ncomponents: []\n',
                encoding="utf-8",
            )
            create_effective_product_definition(
                original,
                generated,
                {"os": "linux", "architecture": "x86_64", "abi": "gnu-glibc-2.39"},
                delivery_mode="artifact",
            )
            self.assertIn("delivery_mode: artifact\n", generated.read_text(encoding="utf-8"))

    def test_rejects_existing_resolution_block_and_unknown_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
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
                    delivery_mode="artifact-or-source",
                )
            source.write_text('schema_version: "2.0.0"\ncomponents: []\n', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "unsupported Product Definition schema"):
                create_effective_product_definition(
                    source, destination,
                    {"os": "linux", "architecture": "x86_64", "abi": "gnu-glibc-2.39"},
                    delivery_mode="artifact-or-source",
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
        self.root = Path(self.temporary.name).resolve()
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

        with self.assertRaisesRegex(RuntimeError, "overwrite a different staged file"):
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
    def test_kernel_123_build_info_validates_published_target_tuple(self) -> None:
        cases = {
            "linux-x86_64": ("linux", "x86_64", "gnu-glibc-2.39"),
            "linux-arm64": ("linux", "arm64", "gnu-glibc-2.39"),
            "macos-x86_64": ("darwin", "x86_64", "macos-15"),
            "macos-arm64": ("darwin", "arm64", "macos-15"),
            "windows-x86_64": ("windows", "x86_64", "windows-ucrt64"),
        }
        pin = {"version": "1.2.3", "kernel_abi": "1.1.0"}
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            info = package / "BUILD-INFO.txt"
            for target, (target_os, architecture, abi) in cases.items():
                with self.subTest(target=target):
                    info.write_text(
                        "Package version: 1.2.3\n"
                        "C ABI version: 1.1.0\n"
                        f"Target OS: {target_os}\n"
                        f"Target architecture: {architecture}\n"
                        f"Target ABI: {abi}\n",
                        encoding="utf-8",
                    )
                    parse_build_info(package, pin, target)

    def test_kernel_123_build_info_rejects_wrong_os_architecture_or_abi(self) -> None:
        pin = {"version": "1.2.3", "kernel_abi": "1.1.0"}
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            info = package / "BUILD-INFO.txt"
            valid = (
                "Package version: 1.2.3\n"
                "C ABI version: 1.1.0\n"
                "Target OS: darwin\n"
                "Target architecture: x86_64\n"
                "Target ABI: macos-15\n"
            )
            for field, bad_value in (
                ("Target OS", "macos"),
                ("Target architecture", "arm64"),
                ("Target ABI", "macos-14"),
            ):
                with self.subTest(field=field):
                    lines = valid.splitlines()
                    index = next(i for i, line in enumerate(lines) if line.startswith(field + ":"))
                    lines[index] = f"{field}: {bad_value}"
                    info.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    with self.assertRaisesRegex(SDKBootstrapError, "BUILD-INFO"):
                        parse_build_info(package, pin, "macos-x86_64")

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


    def test_kernel_sdk_pins_must_match_manifest_environment_contracts(self) -> None:
        manifest = {
            "environment_contracts": [
                {"contract_id": "org.cdin.kernel-abi", "version": "1.1.0"},
                {"contract_id": "org.m-mdy-m.log-c-api", "version": "0.1.0"},
                {"contract_id": "org.lua.puc-lua-c-api", "version": "5.4.0"},
            ]
        }
        pin = {"version": "1.2.1", "kernel_abi": "1.1.0", "logger_version": "0.1.0"}
        verify_environment_sdk_contract(manifest, pin)

        wrong_abi = {"version": "1.2.1", "kernel_abi": "1.0.0", "logger_version": "0.1.0"}
        with self.assertRaisesRegex(RuntimeError, "environment contracts"):
            verify_environment_sdk_contract(manifest, wrong_abi)

        wrong_logger = {"version": "1.2.1", "kernel_abi": "1.1.0", "logger_version": "0.2.0"}
        with self.assertRaisesRegex(RuntimeError, "environment contracts"):
            verify_environment_sdk_contract(manifest, wrong_logger)

    def test_kernel_logger_sdk_prefix_stages_all_cmake_and_pkgconfig_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
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
            root = Path(temporary).resolve()
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




class KernelSDKOfflineCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.cache = Path(self.temporary.name).resolve() / "cache"
        self.payload = b"immutable-kernel-sdk-fixture"
        self.asset = {
            "file_name": "cdin-kernel-1.2.1-linux-x86_64.tar.gz",
            "size_bytes": len(self.payload),
            "sha256": hashlib.sha256(self.payload).hexdigest(),
        }
        self.pin = {
            "repository": "https://github.com/cdin-editor/kernel",
            "tag": "v1.2.1",
            "version": "1.2.1",
            "revision": "f4875b6eb59bd76878e7ff486b6114abd9bb1329",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()


    def test_persistent_sdk_cache_is_outside_the_cleaned_build_tree(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(
            SDK_CACHE,
            root / ".deps" / "cache" / "kernel-sdk",
        )
        self.assertNotIn("build", SDK_CACHE.relative_to(root).parts)

    def test_offline_mode_reuses_only_exact_lock_pinned_cache_bytes(self) -> None:
        self.cache.mkdir(parents=True)
        cached = self.cache / self.asset["file_name"]
        cached.write_bytes(self.payload)
        with patch("scripts.deps.CACHE", self.cache), \
             patch.dict(os.environ, {"CDIN_OFFLINE": "1"}), \
             patch(
                 "scripts.deps.verify_release_asset_identity",
                 side_effect=AssertionError("offline cache reuse must not access GitHub"),
             ):
            result = download_asset(self.pin, self.asset)
        self.assertEqual(result, cached)
        self.assertEqual(result.read_bytes(), self.payload)

    def test_offline_mode_rejects_a_cache_miss(self) -> None:
        with patch("scripts.deps.CACHE", self.cache), \
             patch.dict(os.environ, {"CDIN_OFFLINE": "true"}), \
             patch(
                 "scripts.deps.verify_release_asset_identity",
                 side_effect=AssertionError("offline cache miss must not access GitHub"),
             ):
            with self.assertRaisesRegex(SDKBootstrapError, "offline Kernel SDK installation requires"):
                download_asset(self.pin, self.asset)

    def test_offline_mode_rejects_corrupt_cached_bytes(self) -> None:
        self.cache.mkdir(parents=True)
        cached = self.cache / self.asset["file_name"]
        cached.write_bytes(b"corrupt")
        with patch("scripts.deps.CACHE", self.cache), \
             patch.dict(os.environ, {"CDIN_OFFLINE": "1"}), \
             patch(
                 "scripts.deps.verify_release_asset_identity",
                 side_effect=AssertionError("offline cache verification must not access GitHub"),
             ):
            with self.assertRaisesRegex(SDKBootstrapError, "offline Kernel SDK cache entry"):
                download_asset(self.pin, self.asset)
        self.assertTrue(cached.is_file())

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics are required for this test")
    def test_rejects_symlinked_sdk_cache_ancestor(self) -> None:
        real = Path(self.temporary.name).resolve() / "real"
        real.mkdir()
        linked = Path(self.temporary.name).resolve() / "linked"
        linked.symlink_to(real, target_is_directory=True)
        with patch("scripts.deps.CACHE", linked / "cache"), \
             patch.dict(os.environ, {"CDIN_OFFLINE": "1"}):
            with self.assertRaisesRegex(SDKBootstrapError, "symlink or non-directory ancestor"):
                download_asset(self.pin, self.asset)


class KernelSDKAtomicInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
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



class FrontendArtifactStagingTests(unittest.TestCase):
    required = {
        "core": (
            "include/cdin/frontend/core/version.h",
            "lib/libcdin_frontend_core.a",
            "lib/cmake/cdinFrontendCore/cdinFrontendCoreConfig.cmake",
            "lib/cmake/cdinFrontendCore/cdinFrontendCoreConfigVersion.cmake",
            "lib/cmake/cdinFrontendCore/cdinFrontendCoreTargets.cmake",
            "lib/pkgconfig/cdin-frontend-core.pc",
            "share/cdin-frontend/BUILD-INFO.txt",
        ),
        "tui": (
            "include/cdin/frontend/ui/tui/tui.h",
            "lib/libcdin_frontend_ui_tui.a",
            "lib/cmake/cdinFrontendTUI/cdinFrontendTUIConfig.cmake",
            "lib/cmake/cdinFrontendTUI/cdinFrontendTUIConfigVersion.cmake",
            "lib/cmake/cdinFrontendTUI/cdinFrontendTUITargets.cmake",
            "lib/pkgconfig/cdin-frontend-tui.pc",
            "share/cdin-frontend/BUILD-INFO.txt",
        ),
    }

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_core_and_tui_packages_are_staged_in_separate_prefixes(self) -> None:
        staged = {}
        for variant in ("core", "tui"):
            package = self.root / "packages" / variant
            for relative in self.required[variant]:
                path = package / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = variant if relative.endswith("BUILD-INFO.txt") else relative
                path.write_text(payload, encoding="utf-8")
            prefix = self.root / "install" / "frontend" / variant
            stage_frontend_variant_prefix(package, prefix, variant=variant)
            staged[variant] = prefix

        self.assertEqual(
            (staged["core"] / "share/cdin-frontend/BUILD-INFO.txt").read_text(encoding="utf-8"),
            "core",
        )
        self.assertEqual(
            (staged["tui"] / "share/cdin-frontend/BUILD-INFO.txt").read_text(encoding="utf-8"),
            "tui",
        )
        self.assertTrue(
            (staged["core"] / "lib/cmake/cdinFrontendCore/cdinFrontendCoreConfig.cmake").is_file()
        )
        self.assertTrue(
            (staged["tui"] / "lib/cmake/cdinFrontendTUI/cdinFrontendTUIConfig.cmake").is_file()
        )

    def test_unknown_frontend_variant_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported Frontend package variant"):
            stage_frontend_variant_prefix(
                self.root / "package", self.root / "prefix", variant="unknown"
            )


class RuntimeArtifactRootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_returns_versioned_lua_module_root_from_registry_package(self) -> None:
        root = (
            self.workspace / "components/runtime/default/package"
            / "cdin-runtime-1.0.0"
        )
        entry = root / "lua/cdin/runtime.lua"
        entry.parent.mkdir(parents=True)
        entry.write_text("return {}\n", encoding="utf-8")
        manifest = {
            "components": [{
                "component_id": "runtime",
                "variant": "default",
                "version": "1.0.0",
                "delivery": "artifact",
                "selected_artifact": {
                    "kind": "runtime-module-archive",
                    "layout": "lua-module-tree-v1",
                    "target": {"os": "any", "architecture": "any", "abi": "none"},
                    "workspace_path": "components/runtime/default/package",
                },
            }]
        }
        with patch("scripts.build_stack.WORKSPACE", self.workspace):
            self.assertEqual(runtime_module_package_root(manifest), root)

    def test_developer_registry_mode_still_uses_a_selected_runtime_artifact(self) -> None:
        root = (
            self.workspace / "components/runtime/default/package"
            / "cdin-runtime-1.0.0"
        )
        entry = root / "lua/cdin/runtime.lua"
        entry.parent.mkdir(parents=True)
        entry.write_text("return {}\n", encoding="utf-8")
        manifest = {
            "components": [{
                "component_id": "runtime",
                "variant": "default",
                "version": "1.0.0",
                "delivery": "artifact",
                "selected_artifact": {
                    "kind": "runtime-module-archive",
                    "layout": "lua-module-tree-v1",
                    "target": {"os": "any", "architecture": "any", "abi": "none"},
                    "workspace_path": "components/runtime/default/package",
                },
            }]
        }
        with patch("scripts.build_stack.WORKSPACE", self.workspace):
            with patch("scripts.build_stack.DEPS", self.workspace / "src"):
                self.assertEqual(
                    runtime_root_for_stack(manifest, developer_source_components=True),
                    root,
                )

    def test_developer_source_runtime_is_used_only_when_manifest_selects_source(self) -> None:
        source_root = self.workspace / "src/runtime"
        entry = source_root / "lua/cdin/runtime.lua"
        entry.parent.mkdir(parents=True)
        entry.write_text("return {}\n", encoding="utf-8")
        manifest = {
            "components": [{
                "component_id": "runtime",
                "variant": "default",
                "version": "1.0.0",
                "delivery": "source",
            }]
        }
        with patch("scripts.build_stack.DEPS", self.workspace / "src"):
            self.assertEqual(
                runtime_root_for_stack(manifest, developer_source_components=True),
                source_root,
            )
            with self.assertRaisesRegex(RuntimeError, "normal CDIN installation"):
                runtime_root_for_stack(manifest, developer_source_components=False)

    def test_rejects_a_non_universal_runtime_package_target(self) -> None:
        manifest = {
            "components": [{
                "component_id": "runtime",
                "variant": "default",
                "version": "1.0.0",
                "delivery": "artifact",
                "selected_artifact": {
                    "kind": "runtime-module-archive",
                    "layout": "lua-module-tree-v1",
                    "target": {"os": "linux", "architecture": "x86_64", "abi": "gnu-glibc"},
                    "workspace_path": "components/runtime/default/package",
                },
            }]
        }
        with patch("scripts.build_stack.WORKSPACE", self.workspace):
            with self.assertRaisesRegex(RuntimeError, "universal any/any/none"):
                runtime_module_package_root(manifest)


class RegistryArtifactConsumerValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_runtime_package_manifest_and_every_declared_module_are_verified(self) -> None:
        root = (
            self.workspace / "components/runtime/default/package"
            / "cdin-runtime-1.0.0"
        )
        payloads = {
            "LICENSE": b"runtime license",
            "NOTICE": b"runtime notice",
            "lua/cdin/runtime.lua": b"return {}\n",
        }
        file_records = []
        for relative, payload in payloads.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            file_records.append({
                "path": relative,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            })
        package_manifest = {
            "component_id": "runtime",
            "variant": "default",
            "version": "1.0.0",
            "layout": "lua-module-tree-v1",
            "module_root": "lua",
            "runtime_requirement": "PUC Lua >=5.4 <5.5",
            "source_revision": "a" * 40,
            "files": file_records,
        }
        (root / "package-manifest.json").write_text(
            json.dumps(package_manifest), encoding="utf-8"
        )
        component = {
            "version": "1.0.0",
            "delivery": "artifact",
            "selected_artifact": {
                "kind": "runtime-module-archive",
                "layout": "lua-module-tree-v1",
                "target": {"os": "any", "architecture": "any", "abi": "none"},
                "workspace_path": "components/runtime/default/package",
                "source_provenance": [{
                    "source_unit_id": "runtime-source",
                    "revision": "a" * 40,
                }],
            },
        }
        verify_runtime_package(self.workspace, component)

        (root / "lua/cdin/runtime.lua").write_bytes(b"modified\n")
        with self.assertRaisesRegex(SystemExit, "digest/size mismatch"):
            verify_runtime_package(self.workspace, component)

    def test_frontend_variant_package_checks_build_identity_and_public_files(self) -> None:
        variant = "tui"
        version = "1.1.1"
        revision = "b" * 40
        target = {"os": "linux", "architecture": "x86_64", "abi": "gnu-glibc-2.39"}
        package = self.workspace / "components/frontend/tui/package"
        for relative in FRONTEND_PACKAGE_FILES[variant]:
            path = package / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("package file", encoding="utf-8")
        build_info = package / "share/cdin-frontend/BUILD-INFO.txt"
        build_info.parent.mkdir(parents=True, exist_ok=True)
        build_info.write_text(
            "\n".join((
                "component=frontend",
                "variant=tui",
                f"package_version={version}",
                f"source_revision={revision}",
                "target_os=linux",
                "target_architecture=x86_64",
                "target_abi=gnu-glibc-2.39",
            )) + "\n",
            encoding="utf-8",
        )
        component = {
            "version": version,
            "delivery": "artifact",
            "selected_artifact": {
                "kind": "native-development-package",
                "layout": "cmake-prefix-v1",
                "target": target,
                "workspace_path": "components/frontend/tui/package",
                "source_provenance": [{
                    "source_unit_id": "frontend-source",
                    "revision": revision,
                }],
            },
        }
        self.assertEqual(
            verify_frontend_artifact(
                self.workspace, target, ("frontend", variant), component
            ),
            revision,
        )
        build_info.write_text("component=frontend\nvariant=wrong\n", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "BUILD-INFO does not match"):
            verify_frontend_artifact(
                self.workspace, target, ("frontend", variant), component
            )


if __name__ == "__main__":
    unittest.main()
