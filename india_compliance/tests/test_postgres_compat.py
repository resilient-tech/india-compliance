"""Self-tests for the PostgreSQL static checker in .github/helper/postgres_compat.py.

The checker is the always-on guard for the mechanical Postgres breaks, but it lives outside the
importable package (pre-commit runs it as a script), so it is loaded here by path. Every rule
gets a case that must be flagged and a near miss that must not be, otherwise a rule can quietly
stop matching and nothing notices.
"""

import importlib.util
import textwrap
from pathlib import Path

import frappe
from frappe.tests import UnitTestCase

CHECKER_PATH = (
    Path(frappe.get_app_path("india_compliance")).parent / ".github" / "helper" / "postgres_compat.py"
)


def load_checker():
    spec = importlib.util.spec_from_file_location("postgres_compat", CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPostgresCompatChecker(UnitTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.checker = load_checker()

    def check(self, source):
        """Run the checker over `source` and return the reported messages."""
        path = Path(frappe.generate_hash(length=10) + ".py")
        full_path = Path(frappe.get_site_path()) / path
        full_path.write_text(textwrap.dedent(source))
        self.addCleanup(full_path.unlink, missing_ok=True)

        return self.checker.check_file(str(full_path))

    def assertFlagged(self, source, expected):
        violations = self.check(source)
        self.assertTrue(violations, f"expected {expected!r} to be flagged, got nothing")
        self.assertTrue(
            any(expected in violation for violation in violations),
            f"expected {expected!r} in {violations}",
        )

    def assertClean(self, source):
        self.assertEqual(self.check(source), [])

    def test_update_join_in_query_builder(self):
        """The spelling that a raw SQL scan cannot see."""
        self.assertFlagged(
            """
            frappe.qb.update(t).join(u).on(t.k == u.k).set(t.x, 1).run()
            """,
            "UPDATE..JOIN",
        )
        self.assertFlagged(
            """
            frappe.qb.update(t).set(t.x, 1).left_join(u).on(t.k == u.k).run()
            """,
            "UPDATE..JOIN",
        )

    def test_select_join_is_not_an_update_join(self):
        self.assertClean(
            """
            frappe.qb.from_(t).join(u).on(t.k == u.k).select(t.x).run()
            """
        )

    def test_join_inside_a_set_subquery_is_not_an_update_join(self):
        """The portable rewrite of UPDATE..JOIN is a subquery in SET, which may itself join.
        Matching UPDATE and JOIN anywhere in the string would flag the fix as the bug."""
        self.assertClean(
            '''
            frappe.db.sql("""
                UPDATE `tabBill of Entry Item`
                SET purchase_invoice = (
                    SELECT boe.purchase_invoice
                    FROM `tabBill of Entry` boe
                    JOIN `tabPurchase Invoice` pi ON pi.name = boe.purchase_invoice
                    WHERE boe.name = `tabBill of Entry Item`.parent
                )
            """)
            '''
        )

    def test_aliased_update_target(self):
        """An aliased target renders SET "alias"."col", which postgres rejects."""
        self.assertFlagged(
            """
            def patch():
                t = frappe.qb.DocType("Bill of Entry Item", alias="boe_item")
                frappe.qb.update(t).set(t.qty, 1).run()
            """,
            "alias",
        )

    def test_alias_only_matters_on_the_update_target(self):
        """Aliasing a table that is merely read is fine, and a name is not shared between
        functions."""
        self.assertClean(
            """
            def flagged_elsewhere():
                t = frappe.qb.DocType("Bill of Entry Item")
                u = frappe.qb.DocType("Bill of Entry", alias="boe")
                frappe.qb.update(t).set(t.qty, 1).where(
                    t.parent.isin(frappe.qb.from_(u).select(u.name))
                ).run()
            """
        )

    def test_bool_written_to_check_column_by_query_builder(self):
        self.assertFlagged(
            """
            frappe.qb.update(t).set(t.allow_on_submit, True).run()
            """,
            "bool",
        )
        self.assertFlagged(
            """
            frappe.qb.update(t).set(t.allow_on_submit, bool(allow)).run()
            """,
            "bool",
        )

    def test_cint_written_to_check_column_is_fine(self):
        self.assertClean(
            """
            frappe.qb.update(t).set(t.allow_on_submit, cint(allow)).run()
            frappe.qb.update(t).set(t.label, "Some Label").run()
            """
        )

    def test_bool_written_to_check_column_by_set_value(self):
        self.assertFlagged(
            """
            frappe.db.set_value("Scheduled Job Type", name, "stopped", True)
            """,
            "bool",
        )
        self.assertFlagged(
            """
            doc.db_set("is_nil", False)
            """,
            "bool",
        )

    def test_mysql_only_functions_in_raw_sql(self):
        self.assertFlagged(
            """
            frappe.db.sql("select group_concat(name) from `tabUser`")
            """,
            "group_concat",
        )
        self.assertFlagged(
            """
            frappe.db.sql("select if(a, b, c) from `tabUser`")
            """,
            "IF()",
        )

    def test_distinct_with_order_by(self):
        self.assertFlagged(
            """
            frappe.get_all("User", distinct=True, order_by="name asc")
            """,
            "distinct",
        )

    def test_pg_ok_suppresses_a_finding(self):
        self.assertClean(
            """
            frappe.db.sql("select group_concat(name) from `tabUser`")  # pg-ok
            """
        )

    def test_prose_in_a_docstring_is_not_flagged(self):
        self.assertClean(
            '''
            """Do not use group_concat() when you select from `tabUser`."""
            '''
        )
