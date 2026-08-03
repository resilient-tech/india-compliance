# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

"""Guard: no frappe imports in gst_returns. Site-less.

AST, not sys.modules (package import pulls frappe via india_compliance/__init__).
"""

import ast
import unittest
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent

FORBIDDEN_ROOTS = {"frappe", "erpnext", "india_compliance"}


def _imported_modules(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def _is_forbidden(module):
    return module.split(".")[0] in FORBIDDEN_ROOTS


class TestPackageIsFrappeFree(unittest.TestCase):
    def test_no_frappe_world_imports(self):
        offenders = [
            f"{path.relative_to(PACKAGE_DIR)}: imports {module}"
            for path in PACKAGE_DIR.rglob("*.py")
            for module in _imported_modules(ast.parse(path.read_text(), filename=str(path)))
            if _is_forbidden(module)
        ]
        self.assertEqual(offenders, [], "gst_returns must stay frappe-free:\n" + "\n".join(offenders))


class TestForbiddenPredicate(unittest.TestCase):
    def test_classification(self):
        for mod in (
            "frappe",
            "frappe.utils",
            "erpnext",
            "india_compliance",
            "india_compliance.gst_india.utils.exporter",
            "india_compliance.gst_returns.helpers",
        ):
            self.assertTrue(_is_forbidden(mod), mod)
        for mod in ("math", "openpyxl", "datetime"):
            self.assertFalse(_is_forbidden(mod), mod)


if __name__ == "__main__":
    unittest.main()
