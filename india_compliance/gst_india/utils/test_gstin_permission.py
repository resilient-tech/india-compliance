import frappe
from frappe.permissions import add_permission, reset_perms, update_permission_property
from frappe.tests import IntegrationTestCase, change_settings

from india_compliance.gst_india.utils import (
    validate_company_access,
    validate_company_gstin_access,
    validate_gstin_permission,
)

OWN_GSTIN = "24AAQCA8719H1ZC"  # _Test Indian Registered Company (user is permitted)
OTHER_GSTIN = "29AAQCA8719H1Z1"  # another company (user is not permitted)
TEST_USER = "gstin-perm-test@example.com"
OWNER_ONLY_USER = "gstin-owner-only-test@example.com"
OWNER_ONLY_ROLE = "_Test IC Owner Only"


class TestGstinPermission(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.other_company = "_Test IC Perm Company B"
        if not frappe.db.exists("Company", cls.other_company):
            frappe.get_doc(
                {
                    "doctype": "Company",
                    "company_name": cls.other_company,
                    "abbr": "TICPCB",
                    "default_currency": "INR",
                    "country": "India",
                }
            ).insert(ignore_permissions=True, ignore_if_duplicate=True)

        frappe.db.set_value("Company", "_Test Indian Registered Company", "gstin", OWN_GSTIN)
        frappe.db.set_value("Company", cls.other_company, "gstin", OTHER_GSTIN)

        if not frappe.db.exists("User", TEST_USER):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": TEST_USER,
                    "first_name": "Perm",
                    "roles": [{"role": "Accounts Manager"}, {"role": "Accounts User"}],
                }
            ).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.delete("User Permission", {"user": TEST_USER})
        frappe.clear_cache(user=TEST_USER)

    def restrict_user_to_own_company(self, applicable_for=None):
        permission = {
            "doctype": "User Permission",
            "user": TEST_USER,
            "allow": "Company",
            "for_value": "_Test Indian Registered Company",
        }
        if applicable_for:
            permission["applicable_for"] = applicable_for
        frappe.get_doc(permission).insert(ignore_permissions=True)
        frappe.clear_cache(user=TEST_USER)

    def test_restricted_user_scoped_to_own_company(self):
        self.restrict_user_to_own_company()
        with self.set_user(TEST_USER):
            validate_company_gstin_access(OWN_GSTIN)
            with self.assertRaises(frappe.PermissionError):
                validate_company_gstin_access(OTHER_GSTIN)

    def test_applicable_for_scopes_check_to_its_doctype(self):
        self.restrict_user_to_own_company(applicable_for="GST Inward Supply")
        with self.set_user(TEST_USER):
            with self.assertRaises(frappe.PermissionError):
                validate_company_gstin_access(OTHER_GSTIN, "GST Inward Supply")
            validate_company_gstin_access(OTHER_GSTIN, "GST Return Log")

    def test_decorator_gates_the_method(self):
        @validate_gstin_permission
        def action(company_gstin):
            return "ran"

        self.restrict_user_to_own_company()
        with self.set_user(TEST_USER):
            self.assertEqual(action(company_gstin=OWN_GSTIN), "ran")
            with self.assertRaises(frappe.PermissionError):
                action(company_gstin=OTHER_GSTIN)

    def test_decorator_honours_doctype_override(self):
        # Restriction scoped to GST Inward Supply must not gate a GST Return Log check.
        @validate_gstin_permission(doctype="GST Return Log")
        def action(company_gstin):
            return "ran"

        self.restrict_user_to_own_company(applicable_for="GST Inward Supply")
        with self.set_user(TEST_USER):
            self.assertEqual(action(company_gstin=OTHER_GSTIN), "ran")

    def test_all_sentinel_validates_company_argument(self):
        @validate_gstin_permission
        def action(company_gstin, company):
            return "ran"

        self.restrict_user_to_own_company()
        with self.set_user(TEST_USER):
            self.assertEqual(action(company_gstin="All", company="_Test Indian Registered Company"), "ran")
            with self.assertRaises(frappe.PermissionError):
                action(company_gstin="All", company=self.other_company)

    def test_all_sentinel_resolves_company_from_bound_method(self):
        class Tool:
            def __init__(self, company):
                self.company = company

            @validate_gstin_permission
            def action(self, company_gstin):
                return "ran"

        self.restrict_user_to_own_company()
        with self.set_user(TEST_USER):
            self.assertEqual(Tool("_Test Indian Registered Company").action(company_gstin="All"), "ran")
            with self.assertRaises(frappe.PermissionError):
                Tool(self.other_company).action(company_gstin="All")

    def test_all_sentinel_fails_closed_without_company(self):
        @validate_gstin_permission
        def action(company_gstin):
            return "ran"

        self.restrict_user_to_own_company()
        with self.set_user(TEST_USER):
            with self.assertRaises(frappe.PermissionError):
                action(company_gstin="All")

    def test_decorator_requires_gstin_parameter(self):
        with self.assertRaises(ValueError):

            @validate_gstin_permission
            def action(period):
                return "ran"

    def test_company_access_allows_roles_limited_to_own_documents(self):
        if not frappe.db.exists("Role", OWNER_ONLY_ROLE):
            frappe.get_doc({"doctype": "Role", "role_name": OWNER_ONLY_ROLE}).insert(ignore_permissions=True)
        if not frappe.db.exists("User", OWNER_ONLY_USER):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": OWNER_ONLY_USER,
                    "first_name": "Owner Only",
                    "roles": [{"role": OWNER_ONLY_ROLE}],
                }
            ).insert(ignore_permissions=True)

        add_permission("GST Inward Supply", OWNER_ONLY_ROLE)
        update_permission_property("GST Inward Supply", OWNER_ONLY_ROLE, 0, "if_owner", 1)
        self.addCleanup(reset_perms, "GST Inward Supply")

        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": OWNER_ONLY_USER,
                "allow": "Company",
                "for_value": "_Test Indian Registered Company",
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(frappe.clear_cache, user=OWNER_ONLY_USER)
        self.addCleanup(frappe.db.delete, "User Permission", {"user": OWNER_ONLY_USER})
        frappe.clear_cache(user=OWNER_ONLY_USER)

        with self.set_user(OWNER_ONLY_USER):
            validate_company_access("_Test Indian Registered Company")
            with self.assertRaises(frappe.PermissionError):
                validate_company_access(self.other_company)

    @change_settings("System Settings", {"apply_strict_user_permissions": 1})
    def test_company_access_under_strict_user_permissions(self):
        self.restrict_user_to_own_company()
        frappe.get_doc(
            {
                "doctype": "User Permission",
                "user": TEST_USER,
                "allow": "Cost Center",
                "for_value": "Main - _TIRC",
            }
        ).insert(ignore_permissions=True)
        frappe.clear_cache(user=TEST_USER)

        with self.set_user(TEST_USER):
            validate_company_access("_Test Indian Registered Company", "GL Entry")
            with self.assertRaises(frappe.PermissionError):
                validate_company_access(self.other_company, "GL Entry")
