import frappe
from frappe.exceptions import ValidationError
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.overrides.company import get_tax_defaults
from india_compliance.gst_india.overrides.transaction import get_gst_details
from india_compliance.gst_india.utils.tests import create_transaction

COMPANY = "_Test Indian Registered Company"
COMPANY_ABBR = "_TIRC"
COMPANY_GSTIN = "24AAQCA8719H1ZC"
SALES_TEMPLATE = "Sales Taxes and Charges Template"
PURCHASE_TEMPLATE = "Purchase Taxes and Charges Template"
DEFAULT_IN_STATE_TEMPLATE = f"Output GST In-state - {COMPANY_ABBR}"
# Gujarat address -> intra-state supply; Karnataka -> inter-state.
GUJARAT_CUSTOMER_ADDRESS = "_Test Registered Customer-Billing"
KARNATAKA_CUSTOMER_ADDRESS = "_Test Registered Customer-Billing-3"
GUJARAT_SUPPLIER_ADDRESS = "_Test Registered Supplier-Billing"


class TestTaxCategoryAutoSelection(IntegrationTestCase):
    # ---------- helpers ----------

    def _create_tax_category(self, title, **flags):
        return frappe.get_doc({"doctype": "Tax Category", "title": title, **flags}).insert()

    def _create_linked_template(self, title, tax_category):
        """Clone the default In-State template, point it at a different Tax Category."""
        template = frappe.copy_doc(frappe.get_doc(SALES_TEMPLATE, DEFAULT_IN_STATE_TEMPLATE))
        template.title = title
        template.tax_category = tax_category
        template.is_default = 0
        template.insert()
        return template.name

    def _gst_details(self, doctype="Sales Invoice", **party):
        party.setdefault("company_gstin", COMPANY_GSTIN)
        return get_gst_details(frappe._dict(party), doctype, COMPANY)

    def _sales_gst_details(self, **party):
        party.setdefault("customer", "_Test Registered Customer")
        party.setdefault("customer_address", GUJARAT_CUSTOMER_ADDRESS)
        return self._gst_details("Sales Invoice", **party)

    def test_shipped_tax_categories_match_default_flag(self):
        for row in get_tax_defaults()["tax_categories"]:
            expected = bool(row.get("is_india_compliance_default"))
            actual = bool(frappe.db.get_value("Tax Category", row["title"], "is_india_compliance_default"))
            self.assertEqual(actual, expected, msg=f"{row['title']} default flag mismatch")

    def test_default_scenarios_are_unique(self):
        seen = set()
        for row in get_tax_defaults()["tax_categories"]:
            if not row.get("is_india_compliance_default"):
                continue

            scenario = (row.get("is_inter_state", 0), row.get("is_reverse_charge", 0))
            self.assertNotIn(scenario, seen, msg=f"Duplicate default scenario {scenario}")
            seen.add(scenario)

    # ---------- a user category must not hijack selection ----------

    def test_user_tax_category_does_not_hijack_selection(self):
        category = self._create_tax_category("_Test Custom In-State", is_inter_state=0, is_reverse_charge=0)
        self._create_linked_template("_Test Custom In-State Template", category.name)

        gst_details = self._sales_gst_details()
        self.assertEqual(gst_details.get("taxes_and_charges"), DEFAULT_IN_STATE_TEMPLATE)

    def test_transaction_uses_default_template_despite_user_category(self):
        category = self._create_tax_category("_Test Custom In-State 2", is_inter_state=0, is_reverse_charge=0)
        self._create_linked_template("_Test Custom In-State Template 2", category.name)

        doc = create_transaction(doctype="Sales Invoice", is_in_state=True, do_not_submit=True)
        self.assertEqual(doc.taxes_and_charges, DEFAULT_IN_STATE_TEMPLATE)

    # ---------- inter-state & reverse-charge defaults still resolve ----------

    def test_in_state_default_selection(self):
        expected = frappe.db.get_value(
            SALES_TEMPLATE, {"company": COMPANY, "tax_category": "In-State", "disabled": 0}, "name"
        )
        gst_details = self._sales_gst_details()
        self.assertEqual(gst_details.get("taxes_and_charges"), expected)

    def test_out_state_default_selection(self):
        expected = frappe.db.get_value(
            SALES_TEMPLATE, {"company": COMPANY, "tax_category": "Out-State", "disabled": 0}, "name"
        )
        gst_details = self._sales_gst_details(customer_address=KARNATAKA_CUSTOMER_ADDRESS)
        self.assertEqual(gst_details.get("taxes_and_charges"), expected)

    def test_purchase_reverse_charge_default_selection(self):
        expected = frappe.db.get_value(
            PURCHASE_TEMPLATE,
            {"company": COMPANY, "tax_category": "Reverse Charge In-State", "disabled": 0},
            "name",
        )
        self.assertTrue(expected, msg="default purchase reverse-charge template missing")

        gst_details = self._gst_details(
            doctype="Purchase Invoice",
            supplier="_Test Registered Supplier",
            supplier_address=GUJARAT_SUPPLIER_ADDRESS,
            is_reverse_charge=1,
        )
        self.assertEqual(gst_details.get("taxes_and_charges"), expected)

    def test_no_template_when_company_not_registered(self):
        gst_details = get_gst_details(
            frappe._dict(customer="_Test Registered Customer", customer_address=GUJARAT_CUSTOMER_ADDRESS),
            "Sales Invoice",
            "_Test Foreign Company",
        )
        self.assertFalse(gst_details.get("taxes_and_charges"))

    # ---------- explicit tax category on the document wins ----------

    def test_explicit_tax_category_overrides_auto_selection(self):
        category = self._create_tax_category("_Test Explicit Category", is_inter_state=1, is_reverse_charge=1)
        template = self._create_linked_template("_Test Explicit Template", category.name)

        gst_details = self._sales_gst_details(tax_category=category.name)
        self.assertEqual(gst_details.get("taxes_and_charges"), template)

    def test_explicit_tax_category_without_template_falls_back(self):
        category = self._create_tax_category(
            "_Test Explicit No Template", is_inter_state=0, is_reverse_charge=0
        )

        gst_details = self._sales_gst_details(tax_category=category.name)
        self.assertEqual(gst_details.get("taxes_and_charges"), DEFAULT_IN_STATE_TEMPLATE)

    # ---------- validation ----------

    def test_duplicate_india_compliance_default_is_blocked(self):
        self.assertRaises(
            ValidationError,
            self._create_tax_category,
            "_Test Duplicate Default",
            is_inter_state=0,
            is_reverse_charge=0,
            is_india_compliance_default=1,
        )

    def test_disabled_default_does_not_conflict(self):
        # A disabled default is never selected at runtime, so it must be creatable even when an
        # active default already exists for the same Inter State / Reverse Charge combination.
        category = self._create_tax_category(
            "_Test Disabled Default",
            is_inter_state=0,
            is_reverse_charge=0,
            is_india_compliance_default=1,
            disabled=1,
        )
        self.assertTrue(frappe.db.exists("Tax Category", category.name))

    def test_active_default_allowed_when_existing_default_is_disabled(self):
        # Disabling the shipped default for a combination must let an admin create a replacement;
        # runtime selection ignores disabled categories, so the validator must too.
        frappe.db.set_value("Tax Category", "In-State", "disabled", 1)
        self.addCleanup(frappe.db.set_value, "Tax Category", "In-State", "disabled", 0)

        category = self._create_tax_category(
            "_Test Replacement Default",
            is_inter_state=0,
            is_reverse_charge=0,
            is_india_compliance_default=1,
        )
        self.addCleanup(frappe.delete_doc, "Tax Category", category.name, force=True)
        self.assertTrue(frappe.db.exists("Tax Category", category.name))

    def test_plain_user_tax_category_is_allowed(self):
        category = self._create_tax_category("_Test Plain Category", is_inter_state=0, is_reverse_charge=0)
        self.assertTrue(frappe.db.exists("Tax Category", category.name))
