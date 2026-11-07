from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from check_include_graph import (  # noqa: E402
    classify_include,
    dependency_probe_command,
    traced_headers,
)


class IncludeGraphTests(unittest.TestCase):
    def test_installed_public_header_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deps = root / ".deps"
            prefix = deps / "install"
            header = prefix / "include" / "cdin" / "frontend.h"
            header.parent.mkdir(parents=True)
            header.touch()
            self.assertIsNone(classify_include(
                header,
                working_directory=root,
                dependency_root=deps,
                install_prefix=prefix,
                private_build_roots=(),
            ))

    def test_component_source_checkout_header_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            deps = root / ".deps"
            prefix = deps / "install"
            header = deps / "src" / "frontend" / "include" / "private.h"
            header.parent.mkdir(parents=True)
            header.touch()
            self.assertEqual(
                classify_include(
                    header,
                    working_directory=root,
                    dependency_root=deps,
                    install_prefix=prefix,
                    private_build_roots=(),
                ),
                "component source/build checkout (not installed public headers)",
            )

    def test_component_build_tree_header_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "build" / "stack" / "backend"
            header = build / "generated" / "private_config.h"
            header.parent.mkdir(parents=True)
            header.touch()
            self.assertEqual(
                classify_include(
                    header,
                    working_directory=root,
                    dependency_root=root / ".deps",
                    install_prefix=root / ".deps" / "install",
                    private_build_roots=(build,),
                ),
                "component build tree (not installed public headers)",
            )

    def test_system_and_project_headers_are_not_classified_as_private(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            header = root / "include" / "cdin" / "options.h"
            header.parent.mkdir(parents=True)
            header.touch()
            self.assertIsNone(classify_include(
                header,
                working_directory=root,
                dependency_root=root / ".deps",
                install_prefix=root / ".deps" / "install",
                private_build_roots=(root / "build" / "stack" / "backend",),
            ))

    def test_probe_keeps_only_allowlisted_preprocessor_options(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary).resolve()
            include = root / "include"
            source = root / "src" / "main.c"
            include.mkdir()
            source.parent.mkdir()
            source.touch()
            result = dependency_probe_command(
                [
                    "cc", "-Iinclude", "-DCDIN_TEST=1", "-std=gnu11",
                    "-Wall", "-Wextra", "-Werror", "-fplugin=untrusted.so",
                    "-c", "src/main.c", "-o", "main.o", "-MF", "main.d", "-MMD",
                ],
                translation_unit=source,
                working_directory=root,
            )
            self.assertTrue(Path(result[0]).is_absolute())
            self.assertIn("-I" + str(include), result)
            self.assertIn("-DCDIN_TEST=1", result)
            self.assertIn("-std=gnu11", result)
            self.assertNotIn("-Werror", result)
            self.assertFalse(any("fplugin" in argument for argument in result))
            self.assertEqual(result[-5:], [
                str(source), "-E", "-H", "-o", __import__("os").devnull,
            ])

    def test_probe_rejects_untrusted_include_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            include = Path(temporary) / "include"
            include.mkdir()
            source = root / "main.c"
            source.touch()
            with self.assertRaises(ValueError):
                dependency_probe_command(
                    ["cc", "-I", str(include)],
                    translation_unit=source,
                    working_directory=root,
                )

    def test_probe_rejects_unallowlisted_compiler(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary).resolve()
            source = root / "main.c"
            source.touch()
            with self.assertRaises(ValueError):
                dependency_probe_command(
                    ["/tmp/untrusted-compiler"],
                    translation_unit=source,
                    working_directory=root,
                )

    def test_compiler_trace_parser_resolves_relative_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            header = root / "include" / "cdin.h"
            header.parent.mkdir(parents=True)
            header.touch()
            result = traced_headers(
                ". include/cdin.h\n.. definitely-not-present/system/header.h\nnote: compiler warning\n",
                root,
            )
            self.assertEqual(result, [header.resolve()])


if __name__ == "__main__":
    unittest.main()
