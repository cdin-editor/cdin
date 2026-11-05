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

    def test_probe_removes_compile_outputs_and_keeps_include_flags(self) -> None:
        result = dependency_probe_command([
            "cc", "-Iinclude", "-DCDIN_TEST=1", "-openmp", "-c", "src/main.c",
            "-o", "main.o", "-MF", "main.d", "-MMD",
        ])
        self.assertEqual(
            result,
            ["cc", "-Iinclude", "-DCDIN_TEST=1", "-openmp", "src/main.c",
             "-E", "-H", "-o", __import__("os").devnull],
        )

    def test_compiler_trace_parser_resolves_relative_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            header = root / "include" / "cdin.h"
            header.parent.mkdir(parents=True)
            header.touch()
            result = traced_headers(
                ". include/cdin.h\n.. /usr/include/stdint.h\nnote: compiler warning\n",
                root,
            )
            self.assertEqual(result, [header.resolve()])


if __name__ == "__main__":
    unittest.main()
